from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from html.parser import HTMLParser
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build import PUBLIC_URL, build, detail_page, time_range
import check_recording_notes
from check_recording_notes import caption_url, cue_times
from import_azure_updates import IGNITE_TAG, snapshot as azure_snapshot
from import_sessions import snapshot, speaker_snapshot
from site_data import (
    DATA, FILES, NOTE_SECTIONS, NOTE_STATES, azure_status, load, load_recording_sources, load_references,
    load_session_speakers, load_update_editorial, read_session_notes,
    load_speaker_editorial, validate_catalog, validate_session_links, validate_session_notes,
    validate_speaker_editorial,
)


def catalog_row(oid, *, scope=None, hidden=False, block_video=False):
    return {
        "sessionId": oid.split("-")[0], "sessionInstanceId": oid, "sessionCode": "BRK" + oid[0],
        "title": "Agents & infrastructure", "sessionType": {"displayValue": "Breakout"},
        "sessionLevel": [], "topic": [], "restrictedScopes": scope if scope is not None else [],
        "excludeFromSessionScheduler": hidden, "startDateTime": None, "endDateTime": None,
        "deliveryTypes": [], "hasOnDemand": True, "doNotPublishVideo": block_video,
        "speakerNames": None, "speakerIds": [],
        "description": "Not part of the published schema", "downloadVideoLink": "Not a public link",
    }


class SnapshotTests(unittest.TestCase):
    def test_repeated_offerings_and_restricted_rows(self):
        data = snapshot([
            catalog_row("1-alpha"), catalog_row("1-beta", block_video=True),
            catalog_row("1-restricted", scope=["invite"]), catalog_row("2-invite", scope=["invite"]),
            catalog_row("3-hidden", hidden=True),
        ], "2026-11-27")
        validate_catalog(data)
        self.assertEqual(data["counts"], {
            "sessions": 2, "offerings": 4, "onDemandSessions": 1, "onDemandOfferings": 1,
            "restrictedSessions": 2, "restrictedOfferings": 2,
        })
        self.assertEqual(data["excludedSessions"], 1)
        self.assertEqual(data["excludedOfferings"], 1)
        self.assertEqual([s["code"] for s in data["sessions"]], ["BRK1", "BRK2"])
        self.assertTrue(data["sessions"][1]["offerings"][0]["restrictedAccess"])
        self.assertFalse(data["sessions"][1]["offerings"][0]["hasOnDemand"])
        serialized = json.dumps(data)
        for value in ("restrictedScopes", '"invite"', "description", "downloadVideoLink", "3-hidden"):
            self.assertNotIn(value, serialized)

    def test_unexpected_visibility_field_stops_import(self):
        with self.assertRaisesRegex(ValueError, "visibility"):
            snapshot([catalog_row("1-alpha", scope="")], "2026-11-27")

    def test_duplicate_offering_stops_import(self):
        with self.assertRaisesRegex(ValueError, "Duplicate catalog offering"):
            snapshot([catalog_row("1-alpha"), catalog_row("1-alpha")], "2026-11-27")

    def test_speakers_are_joined_by_unique_directory_id(self):
        row = catalog_row("1-alpha")
        row["speakerNames"] = "Mika Tanaka, Ada Example"
        row["speakerIds"] = ["speaker-1", "speaker-2", "speaker-2"]
        speaker_rows = [
            {"speakerId": "speaker-1", "displayName": "Ada Example",
             "jobTitle": "Azure Catalyst PM", "company": "Microsoft"},
            {"speakerId": "speaker-2", "displayName": "Mika Tanaka",
             "jobTitle": "Director", "company": "Microsoft"},
            {"speakerId": "speaker-2", "displayName": "Mika Tanaka",
             "jobTitle": "VP", "company": "Microsoft"},
        ]
        data = snapshot([row], "2026-11-27")
        validate_catalog(data)
        session = data["sessions"][0]
        self.assertEqual(session["speakerNames"], "Mika Tanaka, Ada Example")
        self.assertNotIn("speakers", session)
        details = speaker_snapshot([row], speaker_rows, "2026-11-27")
        self.assertEqual(details["sessions"]["BRK1"], {"speakers": [{
            "id": "speaker-1", "name": "Ada Example", "jobTitle": "Azure Catalyst PM",
            "company": "Microsoft",
            "sourceUrl": "https://ignite.microsoft.com/en-US/speakers/speaker-1",
        }], "unresolvedSpeakers": 1})

    def test_missing_speaker_ids_remain_unverified(self):
        row = catalog_row("1-alpha")
        del row["speakerIds"]
        details = speaker_snapshot([row], [{"speakerId": "speaker-1", "displayName": "Ada Example"}],
                                  "2026-11-27")
        self.assertEqual(details["sessions"]["BRK1"], {
            "speakers": [], "unresolvedSpeakers": None,
        })

    def test_published_schema_rejects_raw_content_fields(self):
        data = snapshot([catalog_row("1-alpha")], "2026-11-27")
        unexpected = deepcopy(data)
        unexpected["sessions"][0]["offerings"][0]["downloadVideoLink"] = "not allowed"
        with self.assertRaisesRegex(ValueError, "unexpected or missing fields"):
            validate_catalog(unexpected)


class RecordingEvidenceTests(unittest.TestCase):
    def test_player_caption_link_selects_language_and_drops_access_query(self):
        base = "https://mediusdl.event.microsoft.com/video-1/" + "a" * 36 + "/"
        link = base + "Caption_en-US.vtt"
        japanese = base + "Caption_ja-JP.vtt"
        player = "const captionsConfiguration = " + json.dumps({
            "languageList": [
                {"srclang": "en", "src": link + "?sig=not-public"},
                {"srclang": "ja", "src": japanese + "?sig=not-public"},
            ],
        })
        self.assertEqual(caption_url(player), link)
        self.assertEqual(caption_url(player, "ja"), japanese)

    def test_editorial_note_filename_must_match_session_code(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "BRK1.json").write_text('{"sessionCode": "BRK2"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "filename must match sessionCode"):
                read_session_notes(directory)

    def test_reject_html_and_unordered_captions(self):
        with self.assertRaisesRegex(ValueError, "Expected public WebVTT"):
            cue_times("<html>Sign in</html>")
        with self.assertRaisesRegex(ValueError, "unordered"):
            cue_times("WEBVTT\n\n00:02.000 --> 00:03.000\n\n00:01.000 --> 00:02.000\n")

    def test_mixed_sources_check_event_notes_and_report_manual_review(self):
        _, catalog, _, notes = load()
        event = next(n for n in notes["notes"] if n["basis"] == "captions")
        video = next(n for n in notes["notes"] if n["basis"] == "youtube-transcript")
        row = {**catalog_row(event["offeringId"]), "onDemand": "https://medius.microsoft.com/player"}
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.object(sys, "argv", ["check_recording_notes.py", event["sessionCode"], video["sessionCode"]]),
            patch.object(check_recording_notes, "fetch", return_value=json.dumps([row])),
            patch.object(check_recording_notes, "verify_note", return_value=(event["sessionCode"], 1)) as verify,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(check_recording_notes.main(), 1)
        self.assertEqual([call.args[0] for call in verify.call_args_list], [event])
        self.assertIn("1 sessions, 1 entries", stdout.getvalue())
        self.assertIn(f"official YouTube transcript: {video['sessionCode']}", stderr.getvalue())


class ReferenceTests(unittest.TestCase):
    def test_headline_and_feed_status_are_not_collapsed(self):
        self.assertEqual(azure_status({"title": "Generally Available: test", "sourceStatus": "In preview"}), {
            "feedStage": "preview", "headlineStage": "ga", "restrictedPreview": False, "conflict": True,
        })
        for feed in ("In development", "In preview"):
            status = azure_status({"title": "Private Preview: test", "sourceStatus": feed})
            self.assertTrue(status["restrictedPreview"])
            self.assertFalse(status["conflict"])

    def test_tagged_update_import_rejects_incomplete_page_and_wrong_tag(self):
        with self.assertRaisesRegex(ValueError, "expected records"):
            azure_snapshot(lambda _: {"@odata.count": 1, "value": []}, "2026-11-27")
        row = {"id": "100", "created": "2026-11-17T00:00:00Z", "tags": [IGNITE_TAG.lower()]}
        with self.assertRaisesRegex(ValueError, "does not match"):
            azure_snapshot(lambda _: {"@odata.count": 1, "value": [row]}, "2026-11-27")

    def test_unknown_related_update_is_rejected(self):
        _, catalog, updates, notes = load()
        _, videos, relations = load_references(catalog, updates, notes)
        relations["matches"]["BRK240"] = [{"id": "az-0", "context": "example"}]
        by_code = {s["code"]: s for s in catalog["sessions"]}
        with self.assertRaisesRegex(ValueError, "unknown or duplicate update"):
            validate_session_links(videos, relations, by_code, set())


class SpeakerEditorialTests(unittest.TestCase):
    def test_speaker_editorial_requires_a_known_id_and_matching_official_source(self):
        _, catalog, _, _ = load()
        profiles = load_session_speakers(catalog)
        editorial = load_speaker_editorial(profiles)
        self.assertIn("177730559163ignite27-1791934977759001MoV5", editorial)

        invalid = deepcopy(editorial)
        invalid["unknown-speaker"] = {
            "summaryJa": "説明", "sourceUrl": "https://ignite.microsoft.com/en-US/speakers/unknown-speaker",
        }
        with self.assertRaisesRegex(ValueError, "unknown speaker editorial ID"):
            validate_speaker_editorial({"schemaVersion": 1, "checkedOn": "2026-11-27",
                                        "speakers": invalid}, profiles)

        invalid = deepcopy(editorial)
        invalid["177730559163ignite27-1791934977759001MoV5"]["sourceUrl"] = (
            "https://ignite.microsoft.com/en-US/speakers/other-speaker")
        with self.assertRaisesRegex(ValueError, "source does not match"):
            validate_speaker_editorial({"schemaVersion": 1, "checkedOn": "2026-11-27",
                                        "speakers": invalid}, profiles)

        invalid_profiles = deepcopy(profiles)
        bas_profile = next(profile for profile in invalid_profiles["BRK233"]["speakers"]
                           if profile["id"] == "177730559163ignite27-1790281595763001bNYk")
        bas_profile["sourceUrl"] = "https://ignite.microsoft.com/en-US/speakers/other-speaker"
        with self.assertRaisesRegex(ValueError, "source does not match"):
            validate_speaker_editorial({"schemaVersion": 1, "checkedOn": "2026-11-27",
                                        "speakers": editorial}, invalid_profiles)


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.ids = []
        self.local_links = []
        self.result_ids = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-result" in attrs:
            self.result_ids.append(attrs["id"])
        url = attrs.get("href", attrs.get("src"))
        if url and not urlsplit(url).netloc:
            self.local_links.append(url)


class BuildTests(unittest.TestCase):
    def test_jst_shows_a_new_date_after_midnight(self):
        times = time_range("2026-11-17T14:30:00Z", "2026-11-17T15:30:00Z")
        self.assertIn("2026/11/17 23:30", times)
        self.assertIn("2026/11/18 00:30", times)
        self.assertIn('datetime="2026-11-17T14:30:00Z"', times)

    def test_speaker_roles_are_rendered_and_escaped(self):
        _, catalog, _, _ = load()
        session = deepcopy(catalog["sessions"][0])
        session.update({
            "speakerNames": "Example Speaker",
            "speakers": [{
                "id": "speaker-1", "name": "<Example Speaker>", "jobTitle": "Azure Catalyst PM",
                "company": "Microsoft", "sourceUrl": "https://ignite.microsoft.com/en-US/speakers/speaker-1",
            }],
            "unresolvedSpeakers": 0,
        })
        html = detail_page(session, None, None, [], [], None)
        self.assertIn("スピーカー", html)
        self.assertIn("&lt;Example Speaker&gt;", html)
        self.assertIn("Azure Catalyst PM · Microsoft", html)
        self.assertNotIn("<Example Speaker>", html)

    def test_speaker_context_is_rendered_and_escaped(self):
        _, catalog, _, _ = load()
        session = deepcopy(catalog["sessions"][0])
        session.update({
            "speakerNames": "Example Speaker",
            "speakers": [{
                "id": "speaker-1", "name": "Example Speaker", "jobTitle": "Software Engineer",
                "company": "Microsoft", "sourceUrl": "https://ignite.microsoft.com/en-US/speakers/speaker-1",
                "contextJa": "Copilot <開発>",
            }],
            "unresolvedSpeakers": 0,
        })
        html = detail_page(session, None, None, [], [], None)
        self.assertIn("公式プロフィールより：Copilot &lt;開発&gt;", html)
        self.assertNotIn("公式プロフィールより：Copilot <開発>", html)

    def test_site_matches_data_and_relative_links_resolve(self):
        _, catalog, updates, notes = load()
        azure, videos, relations = load_references(catalog, updates, notes)
        editorial = load_update_editorial(updates, azure)
        recordings = load_recording_sources(catalog)
        with TemporaryDirectory() as temp:
            out = Path(temp) / "ignite-2026-info"
            (out / "data").mkdir(parents=True)
            (out / "data" / "session-notes.json").write_text('{"notes":[]}', encoding="utf-8")
            (out / "session").mkdir()
            (out / "session" / "old-id.html").write_text("old file", encoding="utf-8")
            (out / "data" / "sessions").mkdir()
            (out / "data" / "sessions" / "old-id.json").write_text("{}", encoding="utf-8")
            build(out)
            pages = {p.name: Page(p) for p in out.glob("*.html")}
            detail_files = {p.stem: p for p in (out / "session").glob("*.html")}
            self.assertEqual(set(detail_files), {s["code"] for s in catalog["sessions"]})
            self.assertIn("BRK449", detail_files)
            self.assertIn("LAB700", detail_files)
            lab = detail_files["LAB700"].read_text(encoding="utf-8")
            self.assertIn("参加条件あり", lab)
            self.assertIn("../data/sessions/LAB700.json", lab)
            detail_data = {p.stem: p for p in (out / "data" / "sessions").glob("*.json")}
            self.assertEqual(set(detail_data), set(detail_files))
            speaker_profiles = load_session_speakers(catalog)
            speaker_editorial = load_speaker_editorial(speaker_profiles)
            speaker_session = next(s for s in catalog["sessions"]
                                   if any(profile["id"] in speaker_editorial
                                          for profile in speaker_profiles[s["code"]]["speakers"]))
            speaker_record = json.loads(detail_data[speaker_session["code"]].read_text(encoding="utf-8"))
            self.assertTrue(any("contextJa" in profile for profile in speaker_record["speakers"]))
            self.assertNotIn("speakers", speaker_record["session"])
            self.assertNotIn("unresolvedSpeakers", speaker_record["session"])
            self.assertFalse((out / "data" / "session-speakers.json").exists())
            role = next(profile["jobTitle"] for profile in speaker_profiles[speaker_session["code"]]["speakers"]
                        if profile["jobTitle"])
            self.assertIn(role,
                          detail_files[speaker_session["code"]].read_text(encoding="utf-8"))
            self.assertIn("公式プロフィールより：",
                          detail_files[speaker_session["code"]].read_text(encoding="utf-8"))
            self.assertFalse((out / "data" / "session-notes.json").exists())
            self.assertEqual(pages["sessions.html"].result_ids,
                             ["session-" + s["code"] for s in catalog["sessions"]])
            self.assertEqual(pages["updates.html"].result_ids,
                             [a["id"] for a in [*updates["announcements"], *azure["items"]]])
            self.assertIn("KEY01", pages["index.html"].ids)
            self.assertIn("KEY02", pages["index.html"].ids)
            rendered_updates = (out / "updates.html").read_text(encoding="utf-8")
            self.assertIn('id="az-581358"', rendered_updates)
            self.assertIn('data-stage="conflict"', rendered_updates)
            self.assertIn("原題 一般提供（GA） ／ フィード プレビュー", rendered_updates)
            self.assertIn('href="session/BRK240.html">BRK240</a>', rendered_updates)
            recorded = json.loads(detail_data["BRK222"].read_text(encoding="utf-8"))
            self.assertEqual(recorded["youtubeUrl"], videos["matches"]["BRK222"])
            self.assertIn('az-581358', [a["id"] for a in
                                      json.loads(detail_data["BRK240"].read_text(encoding="utf-8"))["relatedUpdates"]])
            for note in updates["notes"]:
                self.assertIn(note["text"], rendered_updates)
                self.assertIn(note["sources"][0]["url"], rendered_updates)
            for name, page in pages.items():
                with self.subTest(page=name):
                    self.assertEqual(len(page.ids), len(set(page.ids)))
                    for url in page.local_links:
                        parts = urlsplit(url)
                        self.assertFalse(parts.path.startswith("/"), url)
                        if parts.path:
                            dest = out / parts.path
                            self.assertTrue(dest.is_file(), url)
                            if parts.fragment and dest.name in pages:
                                self.assertIn(parts.fragment, pages[dest.name].ids)
                        elif parts.fragment:
                            self.assertIn(parts.fragment, page.ids)
            llms = (out / "llms.txt").read_text(encoding="utf-8")
            for filename in FILES:
                self.assertIn(f"({PUBLIC_URL}data/{filename})", llms)
                if filename != "sessions.json":
                    self.assertEqual((out / "data" / filename).read_bytes(), (DATA / filename).read_bytes())
            for filename in ("azure-updates.json", "session-videos.json", "recording-sources.json"):
                self.assertIn(f"({PUBLIC_URL}data/{filename})", llms)
            self.assertEqual((out / "data" / "session-videos.json").read_bytes(),
                             (DATA / "session-videos.json").read_bytes())
            enriched = json.loads((out / "data" / "azure-updates.json").read_text(encoding="utf-8"))
            self.assertEqual(enriched["editorialCoverage"]["summaries"], len(editorial["summaries"]))
            self.assertEqual(enriched["editorialCoverage"]["summaries"], azure["count"])
            self.assertEqual(enriched["editorialCoverage"]["statusConflicts"],
                             sum(azure_status(item)["conflict"] for item in azure["items"]))
            enrichment = {item["id"]: item for item in enriched["items"]}
            self.assertEqual(enrichment["az-574153"]["statusComparison"],
                             {"feedStage": "preview", "headlineStage": "ga",
                              "restrictedPreview": False, "conflict": True})
            self.assertIn("Private Link", enrichment["az-574153"]["summaryJa"])
            for note in notes["notes"]:
                path = detail_files[note["sessionCode"]]
                detail = path.read_text(encoding="utf-8")
                self.assertIn("録画全編を確認したことを示すものではありません", detail)
                for heading in NOTE_SECTIONS.values():
                    self.assertIn(heading, detail)
                if note["youtubeUrl"]:
                    self.assertIn(note["youtubeUrl"], detail)
                if note["basis"] == "youtube-transcript":
                    seconds = note["summary"][0]["atSeconds"]
                    self.assertIn("時刻は公式 YouTube 録画の目安", detail)
                    self.assertIn(f'href="{note["youtubeUrl"]}&amp;t={seconds}s"', detail)
                else:
                    self.assertIn("時刻は公式イベント録画の目安", detail)
                for item in note["updates"]:
                    if item["announcementId"]:
                        self.assertIn(f'../updates.html#{item["announcementId"]}', detail)
                detail_page = Page(path)
                for url in detail_page.local_links:
                    parts = urlsplit(url)
                    if parts.path:
                        dest = path.parent / parts.path
                        self.assertTrue(dest.is_file(), url)
                        self.assertTrue(dest.resolve().is_relative_to(out.resolve()), url)
            by_code = {n["sessionCode"]: n for n in notes["notes"]}
            counts = Counter()
            for s in catalog["sessions"]:
                record = json.loads(detail_data[s["code"]].read_text(encoding="utf-8"))
                self.assertEqual(record["session"], s)
                note = by_code.get(s["code"])
                state = "reviewed" if note else "pending" if any(o["hasOnDemand"] for o in s["offerings"]) else "unlisted"
                counts[state] += 1
                self.assertEqual(record["recordingReview"], {"status": state, "note": note})
                self.assertEqual(record["youtubeUrl"], videos["matches"].get(s["code"]))
                related = {r["id"] for r in relations["matches"].get(s["code"], [])}
                if note:
                    related.update(p["announcementId"] for p in note["updates"] if p["announcementId"])
                self.assertEqual({r["id"] for r in record["relatedUpdates"]}, related)
                self.assertEqual({a["url"] for a in record["technicalArticles"]},
                                 {a["url"] for identity in related for a in editorial["articles"].get(identity, [])})
                for article in record["technicalArticles"]:
                    self.assertEqual(set(article["relatedUpdateIds"]), {
                        i for i in related if any(a["url"] == article["url"] for a in editorial["articles"].get(i, []))
                    })
                source = recordings["matches"].get(s["code"])
                if source:
                    detail = record["recordingSource"]
                    self.assertEqual(detail["captionLanguages"], source["captionLanguages"])
                    self.assertEqual(detail["chapterSeconds"], source["chapterSeconds"])
                    self.assertIn(detail["sourceUrl"], [o["sourceUrl"] for o in s["offerings"]])
                else:
                    self.assertIsNone(record["recordingSource"])
            published_catalog = json.loads((out / "data" / "sessions.json").read_text(encoding="utf-8"))
            self.assertTrue(all("speakers" not in session and "unresolvedSpeakers" not in session
                                for session in published_catalog["sessions"]))
            catalog_json = json.dumps(published_catalog)
            self.assertNotIn('"jobTitle"', catalog_json)
            self.assertNotIn('"company"', catalog_json)
            self.assertEqual(published_catalog.pop("recordingReview"), {
                "counts": {status: counts[status] for status in NOTE_STATES},
                "reviewedSessionCodes": sorted(by_code),
            })
            self.assertEqual(published_catalog.pop("linkedYouTubeSessionCodes"), sorted(videos["matches"]))
            self.assertEqual(published_catalog, catalog)
            self.assertIn("/data/sessions/", llms)
            self.assertIn("まず軽量な `sessions.json` の一覧", llms)
            for available, expected in [
                (True, "内容はまだ確認していません"), (False, "公式カタログに公開録画の掲載がない"),
            ]:
                included = [s for s in catalog["sessions"] if s["code"] not in by_code and
                            any(o["hasOnDemand"] for o in s["offerings"]) == available]
                if included:
                    detail = detail_files[included[0]["code"]].read_text(encoding="utf-8")
                    self.assertIn(expected, detail)
                    self.assertNotIn("<h2>事例・デモ</h2>", detail)

    def test_session_notes_reject_mismatched_offering_and_announcement(self):
        _, catalog, updates, notes = load()
        invalid = deepcopy(notes)
        invalid["notes"][0]["offeringId"] = invalid["notes"][1]["offeringId"]
        with self.assertRaisesRegex(ValueError, "recorded offering"):
            validate_session_notes(invalid, catalog, updates)
        invalid = deepcopy(notes)
        item = next(i for n in invalid["notes"] for i in n["updates"])
        item["announcementId"] = "bon-nonexistent"
        with self.assertRaisesRegex(ValueError, "unknown announcement"):
            validate_session_notes(invalid, catalog, updates)

    def test_youtube_transcript_requires_a_video(self):
        _, catalog, updates, notes = load()
        note = deepcopy(next(n for n in notes["notes"] if n["youtubeUrl"]))
        note["basis"] = "youtube-transcript"
        data = {"schemaVersion": 1, "notes": [note]}
        validate_session_notes(data, catalog, updates)
        note["youtubeUrl"] = None
        with self.assertRaisesRegex(ValueError, "transcript evidence requires a YouTube video"):
            validate_session_notes(data, catalog, updates)

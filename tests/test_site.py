from collections import Counter
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build import PUBLIC_URL, build, time_range
from check_recording_notes import caption_url, cue_times
from import_sessions import snapshot
from site_data import DATA, FILES, NOTE_SECTIONS, load, read_session_notes, validate_catalog, validate_session_notes


def catalog_row(oid, *, scope=None, hidden=False, block_video=False):
    return {
        "sessionId": oid.split("-")[0], "sessionInstanceId": oid, "sessionCode": "BRK" + oid[0],
        "title": "Agents & infrastructure", "sessionType": {"displayValue": "Breakout"},
        "sessionLevel": [], "topic": [], "restrictedScopes": scope if scope is not None else [],
        "excludeFromSessionScheduler": hidden, "startDateTime": None, "endDateTime": None,
        "deliveryTypes": [], "hasOnDemand": True, "doNotPublishVideo": block_video,
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

    def test_site_matches_data_and_relative_links_resolve(self):
        _, catalog, updates, notes = load()
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
            self.assertFalse((out / "data" / "session-notes.json").exists())
            self.assertEqual(pages["sessions.html"].result_ids,
                             ["session-" + s["code"] for s in catalog["sessions"]])
            self.assertEqual(pages["updates.html"].result_ids,
                             [a["id"] for a in updates["announcements"]])
            self.assertIn("KEY01", pages["index.html"].ids)
            self.assertIn("KEY02", pages["index.html"].ids)
            rendered_updates = (out / "updates.html").read_text(encoding="utf-8")
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
            for note in notes["notes"]:
                path = detail_files[note["sessionCode"]]
                detail = path.read_text(encoding="utf-8")
                self.assertIn("録画全編を確認したことを示すものではありません", detail)
                for heading in NOTE_SECTIONS.values():
                    self.assertIn(heading, detail)
                if note["youtubeUrl"]:
                    self.assertIn(note["youtubeUrl"], detail)
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
            published_catalog = json.loads((out / "data" / "sessions.json").read_text(encoding="utf-8"))
            self.assertEqual(published_catalog.pop("recordingReview"), {
                "counts": counts, "reviewedSessionCodes": sorted(by_code),
            })
            self.assertEqual(published_catalog, catalog)
            self.assertIn("/data/sessions/", llms)
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

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
from import_sessions import snapshot
from site_data import DATA, FILES, load, validate_catalog


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
            "sessions": 1, "offerings": 2, "onDemandSessions": 1, "onDemandOfferings": 1,
        })
        self.assertEqual(data["excludedSessions"], 2)
        self.assertEqual(data["excludedOfferings"], 3)
        serialized = json.dumps(data)
        for value in ("restrictedScopes", "1-restricted", "description", "downloadVideoLink", "3-hidden"):
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
        _, catalog, updates = load()
        with TemporaryDirectory() as temp:
            out = Path(temp) / "ignite-2026-info"
            build(out)
            pages = {p.name: Page(p) for p in out.glob("*.html")}
            self.assertEqual(pages["sessions.html"].result_ids,
                             ["session-" + s["id"] for s in catalog["sessions"]])
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
                            self.assertTrue((out / parts.path).is_file(), url)
                        elif parts.fragment:
                            self.assertIn(parts.fragment, page.ids)
            llms = (out / "llms.txt").read_text(encoding="utf-8")
            for filename in FILES:
                self.assertIn(f"({PUBLIC_URL}data/{filename})", llms)
                self.assertEqual((out / "data" / filename).read_bytes(), (DATA / filename).read_bytes())

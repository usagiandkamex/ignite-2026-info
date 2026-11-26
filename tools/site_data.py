"""Validate the shared data contract before rendering or uploading any files."""

from datetime import date, datetime
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from import_sessions import CATALOG_URL, FEED_URL, OFFERING_ID, ON_DEMAND_URL, SESSION_ID, summarize

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FILES = ("event.json", "sessions.json", "updates.json")
BOOK_URL = "https://news.microsoft.com/events/ignite/2026/book-of-news/"

SESSION_TYPES = {
    "Keynote": "キーノート",
    "Innovation Session": "イノベーション セッション",
    "Breakout": "ブレイクアウト",
    "Theater": "シアター",
    "Lightning Talk": "ライトニングトーク",
    "Table Talk": "テーブルトーク",
    "Broadcast Stage": "配信ステージ",
    "Pre-recorded": "事前収録",
    "Digital Lab": "デジタルラボ",
}
TOPICS = {
    "Cloud & AI": "クラウドと AI",
    "Agent Platform": "エージェント基盤",
    "Security": "セキュリティ",
    "Copilot": "Copilot",
    "Agentic Business Applications": "エージェント型業務アプリ",
    "Data": "データ",
    "Frontier Transformation": "Frontier Transformation",
    "Windows": "Windows",
    "Microsoft IQ": "Microsoft IQ",
    "MAICPP": "Microsoft AI Cloud Partner Program",
    "Other": "その他",
}
LEVELS = {
    "(100) Foundational": "100 基礎",
    "(200) Intermediate": "200 中級",
    "(300) Advanced": "300 上級",
    "(400) Expert": "400 エキスパート",
}
DELIVERY = {"In-person": "現地", "Online": "オンライン"}
CATEGORIES = {name: name for name in (
    "Azure", "Microsoft Foundry", "GitHub", "Microsoft Copilot",
    "Microsoft Edge", "Microsoft IQ", "Security", "Windows",
)}
CATEGORIES["Security"] = "セキュリティ"
STAGES = {
    "ga": "一般提供（GA）",
    "preview": "プレビュー",
    "frontier": "Frontier 対象",
    "rollout": "順次展開",
    "planned": "提供予定",
    "announced": "発表",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(obj, expected, label):
    require(isinstance(obj, dict) and obj.keys() == set(expected.split()),
            f"{label}: unexpected or missing fields")


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: expected non-empty text")


def utc(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value),
            f"Expected UTC timestamp ending in Z: {value!r}")
    return datetime.fromisoformat(value)


def iso_date(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", value),
            f"Expected ISO date: {value!r}")
    return date.fromisoformat(value)


def options(values, allowed, label, *, required=False):
    require(isinstance(values, list) and (values or not required)
            and all(isinstance(v, str) and v in allowed for v in values)
            and len(values) == len(set(values)), f"{label}: unexpected or duplicate values: {values!r}")


def official_url(value):
    text(value, "URL")
    url = urlsplit(value)
    hosts = ("microsoft.com", "aka.ms", "youtube.com", "blogs.windows.com", "github.blog")
    require(url.scheme == "https" and url.netloc == url.hostname and url.hostname is not None
            and any(url.hostname == host or url.hostname.endswith("." + host) for host in hosts)
            and not any(c.isspace() for c in value), f"Not an official HTTPS URL: {value}")


def sources(records):
    require(isinstance(records, list) and records, "Expected a non-empty list of official sources")
    for source in records:
        keys(source, "label url", "source")
        text(source["label"], "source label")
        official_url(source["url"])


def validate_catalog(data):
    keys(data, "schemaVersion checkedOn catalogUrl onDemandCatalogUrl sourceDataUrl counts "
               "excludedSessions excludedOfferings sessions", "catalog")
    require((data["catalogUrl"], data["onDemandCatalogUrl"], data["sourceDataUrl"])
            == (CATALOG_URL, ON_DEMAND_URL, FEED_URL), "Unexpected catalog sources")
    require(all(type(data[k]) is int and data[k] >= 0
                for k in ("excludedSessions", "excludedOfferings"))
            and data["excludedSessions"] <= data["excludedOfferings"], "Invalid exclusion counts")
    sessions = data["sessions"]
    require(isinstance(sessions, list) and sessions, "Expected non-empty catalog")
    session_ids, offering_ids = set(), set()
    by_code = {}
    for session in sessions:
        keys(session, "id code title type levels topics offerings", "session")
        sid, code = session["id"], session["code"]
        text(code, "session code")
        text(session["title"], f"{code} title")
        require(SESSION_ID.fullmatch(sid) and sid not in session_ids, f"Invalid or duplicate session: {sid}")
        session_ids.add(sid)
        require(code not in by_code, f"Duplicate session code: {code}")
        require(session["type"] in SESSION_TYPES, f"{code}: unknown type")
        options(session["levels"], LEVELS, f"{code} levels")
        options(session["topics"], TOPICS, f"{code} topics")
        require(isinstance(session["offerings"], list) and session["offerings"], f"{code}: no offerings")
        for offering in session["offerings"]:
            keys(offering, "id startUtc endUtc delivery hasOnDemand sourceUrl", f"{code} offering")
            oid = offering["id"]
            require(OFFERING_ID.fullmatch(oid) and oid.split("-")[0] == sid and oid not in offering_ids,
                    f"Invalid or duplicate offering: {oid}")
            offering_ids.add(oid)
            start, end = offering["startUtc"], offering["endUtc"]
            require((start is None and end is None) or
                    (start is not None and end is not None and utc(start) < utc(end)), f"{oid}: invalid time range")
            options(offering["delivery"], DELIVERY, f"{oid} delivery")
            require(type(offering["hasOnDemand"]) is bool, f"{oid}: invalid recording flag")
            require(offering["sourceUrl"] == f"{CATALOG_URL}/{oid}", f"{oid}: unexpected source URL")
        by_code[code] = session
    counts = summarize(sessions)
    require(data["counts"] == counts and all(type(v) is int for v in data["counts"].values()),
            "Catalog counts must match the published rows")
    return by_code


def validate_event(event, by_code):
    keys(event, "schemaVersion checkedOn name startDate endDate timeZone venue summary keynotes sources",
         "event")
    for key in ("name", "venue", "summary"):
        text(event[key], f"event {key}")
    require(iso_date(event["startDate"]) <= iso_date(event["endDate"]), "Invalid event date range")
    require(event["timeZone"] == "America/Los_Angeles", "Event dates must be Pacific dates")
    sources(event["sources"])
    codes = []
    for keynote in event["keynotes"]:
        keys(keynote, "sessionCode title startUtc endUtc summary sourceUrl replayUrl", "keynote")
        code = keynote["sessionCode"]
        codes.append(code)
        text(keynote["title"], f"{code} title")
        text(keynote["summary"], f"{code} summary")
        require(utc(keynote["startUtc"]) < utc(keynote["endUtc"]), f"{code}: invalid time range")
        session = by_code.get(code)
        require(session is not None and session["type"] == "Keynote" and any(
            o["sourceUrl"] == keynote["sourceUrl"] and o["startUtc"] == keynote["startUtc"]
            and o["endUtc"] == keynote["endUtc"] for o in session["offerings"]
        ), f"{code}: event details do not match catalog")
        if keynote["replayUrl"] is not None:
            official_url(keynote["replayUrl"])
    require(codes == ["KEY01", "KEY02"], "Expected the opening and partner keynotes")


def validate_updates(data):
    keys(data, "schemaVersion checkedOn bookOfNewsUrl bookOfNewsLastModifiedUtc sources notes announcements",
         "updates")
    require(data["bookOfNewsUrl"] == BOOK_URL, "Unexpected Book of News URL")
    utc(data["bookOfNewsLastModifiedUtc"])
    sources(data["sources"])
    ids, categories = set(), set()
    for update in data["announcements"]:
        keys(update, "id category title stages summary sourceUrl", "announcement")
        uid, category = update["id"], update["category"]
        require(re.fullmatch(r"bon-\d+", uid) and uid not in ids, f"Invalid or duplicate announcement: {uid}")
        ids.add(uid)
        require(category in CATEGORIES, f"{uid}: unexpected category")
        categories.add(category)
        text(update["title"], f"{uid} title")
        text(update["summary"], f"{uid} summary")
        options(update["stages"], STAGES, f"{uid} stages", required=True)
        official_url(update["sourceUrl"])
    require(categories == CATEGORIES.keys(), "Expected coverage for all Book of News categories")
    require(isinstance(data["notes"], list), "Expected a list of dated updates")
    for note in data["notes"]:
        keys(note, "announcementId checkedOn text sources", "dated update")
        require(note["announcementId"] in ids, "Dated update must reference an existing announcement")
        iso_date(note["checkedOn"])
        text(note["text"], "dated update")
        sources(note["sources"])


def load():
    records = []
    for filename in FILES:
        record = json.loads((DATA / filename).read_text(encoding="utf-8"))
        require(type(record["schemaVersion"]) is int and record["schemaVersion"] == 1,
                f"{filename}: unsupported schema version")
        iso_date(record["checkedOn"])
        records.append(record)
    event, catalog, updates = records
    by_code = validate_catalog(catalog)
    validate_event(event, by_code)
    validate_updates(updates)
    return event, catalog, updates

"""Validate the shared data contract before rendering or uploading any files."""

from datetime import date, datetime
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from import_azure_updates import AZURE_FEED, AZURE_UPDATES, END, IGNITE_TAG, START, item_url
from import_sessions import (
    CATALOG_URL, FEED_URL, OFFERING_ID, ON_DEMAND_URL, SESSION_CODE, SESSION_ID, SPEAKER_FEED_URL, summarize,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FILES = ("event.json", "sessions.json", "updates.json")
REFERENCE_FILES = ("azure-updates.json", "session-videos.json", "session-updates.json")
UPDATE_EDITORIAL = DATA / "update-editorial.json"
RECORDING_SOURCES = DATA / "recording-sources.json"
SESSION_NOTES_DIR = DATA / "session-notes"
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
    "Lab": "ハンズオンラボ",
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
    "unlisted": "提供状況の記載なし",
    "restricted-preview": "限定プレビュー",
}
AZURE_STAGES = {"Launched": "ga", "In preview": "preview", "In development": "planned", None: "unlisted"}
AZURE_HEADLINE_STAGES = {
    "generally available": "ga",
    "public preview": "preview",
    "private preview": "preview",
    "limited preview": "preview",
}
YOUTUBE_WATCH = re.compile(r"https://www\.youtube\.com/watch\?v=[a-zA-Z0-9_-]{11}")
YOUTUBE_CHANNEL = "https://www.youtube.com/@events_msft/playlists"
NOTE_SECTIONS = {
    "summary": "話されたこと",
    "updates": "紹介されたアップデート",
    "cases": "事例・デモ",
    "tips": "Tips・実践のヒント",
}
NOTE_STATES = {
    "reviewed": "録画資料を確認・要約あり",
    "pending": "オンデマンドあり・内容未確認",
    "unlisted": "録画の掲載なし・内容未確認",
}
RECORDING_BASIS = {
    "captions": "公式録画の字幕",
    "captions-and-chapters": "公式録画の字幕と YouTube のチャプター",
    "captions-ja": "公式録画の日本語字幕",
    "youtube-transcript": "公式 YouTube の文字起こし",
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
    hosts = ("microsoft.com", "aka.ms", "youtube.com", "blogs.windows.com", "blogs.bing.com", "github.blog")
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
               "speakerDirectoryUrl speakerDirectoryCheckedOn excludedSessions excludedOfferings sessions", "catalog")
    require((data["catalogUrl"], data["onDemandCatalogUrl"], data["sourceDataUrl"])
            == (CATALOG_URL, ON_DEMAND_URL, FEED_URL), "Unexpected catalog sources")
    require(data["speakerDirectoryUrl"] == SPEAKER_FEED_URL, "Unexpected speaker directory source")
    if data["speakerDirectoryCheckedOn"] is not None:
        iso_date(data["speakerDirectoryCheckedOn"])
    require(all(type(data[k]) is int and data[k] >= 0
                for k in ("excludedSessions", "excludedOfferings"))
            and data["excludedSessions"] <= data["excludedOfferings"], "Invalid exclusion counts")
    sessions = data["sessions"]
    require(isinstance(sessions, list) and sessions, "Expected non-empty catalog")
    session_ids, offering_ids = set(), set()
    by_code = {}
    for session in sessions:
        keys(session, "id code title type levels topics speakerNames speakers unresolvedSpeakers offerings",
             "session")
        sid, code = session["id"], session["code"]
        require(isinstance(code, str) and SESSION_CODE.fullmatch(code), f"Invalid session code: {code!r}")
        text(session["title"], f"{code} title")
        require(SESSION_ID.fullmatch(sid) and sid not in session_ids, f"Invalid or duplicate session: {sid}")
        session_ids.add(sid)
        require(code not in by_code, f"Duplicate session code: {code}")
        require(session["type"] in SESSION_TYPES, f"{code}: unknown type")
        options(session["levels"], LEVELS, f"{code} levels")
        options(session["topics"], TOPICS, f"{code} topics")
        if session["speakerNames"] is not None:
            text(session["speakerNames"], f"{code} speaker names")
        profiles = session["speakers"]
        require(isinstance(profiles, list), f"{code}: expected speaker profiles")
        speaker_ids = set()
        for profile in profiles:
            keys(profile, "id name jobTitle company sourceUrl", f"{code} speaker")
            text(profile["id"], f"{code} speaker ID")
            require(profile["id"] not in speaker_ids, f"{code}: duplicate speaker ID")
            speaker_ids.add(profile["id"])
            text(profile["name"], f"{code} speaker name")
            for field in ("jobTitle", "company"):
                require(profile[field] is None or isinstance(profile[field], str),
                        f"{code} speaker {field}: expected text or null")
            official_url(profile["sourceUrl"])
        unresolved = session["unresolvedSpeakers"]
        require(unresolved is None or type(unresolved) is int and unresolved >= 0,
                f"{code}: invalid unresolved speaker count")
        require(isinstance(session["offerings"], list) and session["offerings"], f"{code}: no offerings")
        for offering in session["offerings"]:
            keys(offering, "id startUtc endUtc delivery hasOnDemand restrictedAccess sourceUrl", f"{code} offering")
            oid = offering["id"]
            require(OFFERING_ID.fullmatch(oid) and oid.split("-")[0] == sid and oid not in offering_ids,
                    f"Invalid or duplicate offering: {oid}")
            offering_ids.add(oid)
            start, end = offering["startUtc"], offering["endUtc"]
            require((start is None and end is None) or
                    (start is not None and end is not None and utc(start) < utc(end)), f"{oid}: invalid time range")
            options(offering["delivery"], DELIVERY, f"{oid} delivery")
            require(type(offering["hasOnDemand"]) is bool and type(offering["restrictedAccess"]) is bool
                    and not (offering["hasOnDemand"] and offering["restrictedAccess"]),
                    f"{oid}: invalid recording or access flag")
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


def validate_azure_updates(data):
    keys(data, "schemaVersion checkedOn sourceDataUrl sourceUrl tag publicationFrom publicationBefore count items",
         "Azure Updates")
    require((data["sourceDataUrl"], data["sourceUrl"], data["tag"], data["publicationFrom"],
             data["publicationBefore"]) == (AZURE_FEED, AZURE_UPDATES, IGNITE_TAG, START, END),
            "Unexpected Azure Updates scope or source")
    ids = set()
    for item in data["items"]:
        keys(item, "id title publishedOn sourceStatus products categories sourceUrl", "Azure update")
        identity = item["id"]
        require(re.fullmatch(r"az-[0-9]+", identity) and identity not in ids, f"Invalid Azure update: {identity}")
        ids.add(identity)
        iso_date(item["publishedOn"])
        require(START <= item["publishedOn"] < END, f"{identity}: outside publication window")
        text(item["title"], f"{identity} title")
        require(item["sourceStatus"] in AZURE_STAGES, f"{identity}: unknown Azure status")
        for field in ("products", "categories"):
            values = item[field]
            require(isinstance(values, list) and values == sorted(set(values)), f"{identity}: invalid {field}")
            for value in values:
                text(value, field)
        require(item["sourceUrl"] == item_url(identity[3:]), f"{identity}: unexpected official link")
    require(type(data["count"]) is int and data["count"] == len(ids) and ids, "Incorrect Azure Updates count")
    return ids


def validate_session_links(videos, updates, by_code, ids):
    keys(videos, "schemaVersion checkedOn channelUrl playlists matches", "session videos")
    require(videos["channelUrl"] == YOUTUBE_CHANNEL, "Unexpected YouTube channel")
    require(isinstance(videos["playlists"], list) and videos["playlists"], "Missing official playlists")
    for url in videos["playlists"]:
        require(re.fullmatch(r"https://www\.youtube\.com/playlist\?list=[a-zA-Z0-9_-]+", url),
                "Unexpected official playlist URL")
    assigned = set()
    for code, url in videos["matches"].items():
        require(code in by_code and isinstance(url, str) and YOUTUBE_WATCH.fullmatch(url) and url not in assigned,
                f"{code}: unknown session, duplicate video or invalid YouTube URL")
        assigned.add(url)
    keys(updates, "schemaVersion checkedOn matches", "session updates")
    for code, references in updates["matches"].items():
        require(code in by_code and isinstance(references, list) and references, f"{code}: invalid update links")
        seen = set()
        for entry in references:
            keys(entry, "id context", "session update link")
            identity = entry["id"]
            require(identity in ids and identity not in seen, f"{code}: unknown or duplicate update {identity}")
            seen.add(identity)
            text(entry["context"], f"{code} update context")


def azure_status(item):
    """Keep the provider's two status signals separate if they disagree."""
    feed = AZURE_STAGES[item["sourceStatus"]]
    prefix = item["title"].partition(":")[0].strip().casefold()
    headline = AZURE_HEADLINE_STAGES.get(prefix)
    restricted = prefix in {"private preview", "limited preview"}
    compatible = {headline, "planned"} if restricted else {headline}
    conflict = headline is not None and feed != "unlisted" and feed not in compatible
    return {"feedStage": feed, "headlineStage": headline, "restrictedPreview": restricted, "conflict": conflict}


def load_update_editorial(book, azure):
    data = json.loads(UPDATE_EDITORIAL.read_text(encoding="utf-8"))
    keys(data, "schemaVersion checkedOn articles summaries", "update editorial")
    require(type(data["schemaVersion"]) is int and data["schemaVersion"] == 1,
            "Unsupported update editorial schema version")
    iso_date(data["checkedOn"])
    all_ids = {a["id"] for a in [*book["announcements"], *azure["items"]]}
    azure_ids = {a["id"] for a in azure["items"]}
    for identity, links in data["articles"].items():
        require(identity in all_ids and isinstance(links, list) and links, f"{identity}: invalid technical articles")
        sources(links)
        for item in links:
            url = urlsplit(item["url"])
            path = url.path.casefold()
            require(url.hostname in {"devblogs.microsoft.com", "blogs.windows.com", "blogs.bing.com",
                                     "github.blog", "commandline.microsoft.com", "blog.fabric.microsoft.com"}
                    or ("/blog/" in path and url.hostname in {"azure.microsoft.com", "www.microsoft.com",
                                                              "techcommunity.microsoft.com",
                                                              "community.fabric.microsoft.com"}),
                    f"{identity}: technical article must use a direct official publisher URL")
    for identity, summary in data["summaries"].items():
        require(identity in azure_ids, f"{identity}: unknown Azure update summary ID")
        text(summary, f"{identity} Japanese summary")
    require(data["summaries"].keys() == azure_ids, "Japanese summaries must cover all tagged Azure updates")
    return data


def load_recording_sources(catalog):
    data = json.loads(RECORDING_SOURCES.read_text(encoding="utf-8"))
    keys(data, "schemaVersion checkedOn matches", "recording sources")
    require(type(data["schemaVersion"]) is int and data["schemaVersion"] == 1,
            "Unsupported recording sources schema version")
    iso_date(data["checkedOn"])
    public = {
        s["code"]: {o["id"] for o in s["offerings"] if o["hasOnDemand"]}
        for s in catalog["sessions"] if any(o["hasOnDemand"] for o in s["offerings"])
    }
    require(data["matches"].keys() == public.keys(),
            "Recording sources must cover exactly the current public on-demand sessions.")
    for code, value in data["matches"].items():
        keys(value, "offeringId captionLanguages chapterSeconds", "recording source")
        require(code in public and value["offeringId"] in public[code],
                f"{code}: invalid public recording source")
        options(value["captionLanguages"], {"en", "ja"}, f"{code} caption languages")
        times = value["chapterSeconds"]
        require(isinstance(times, list) and all(type(t) is int and t >= 0 for t in times)
                and times == sorted(set(times)), f"{code}: invalid chapter timestamps")
    return data


def validate_session_notes(data, catalog, updates):
    keys(data, "schemaVersion notes", "session notes")
    by_id = {s["id"]: s for s in catalog["sessions"]}
    announcements = {a["id"] for a in updates["announcements"]}
    seen = set()
    require(isinstance(data["notes"], list), "Expected a list of recording notes")
    for note in data["notes"]:
        keys(note, "sessionId sessionCode reviewedOn offeringId youtubeUrl basis summary updates cases tips", "session note")
        sid = note["sessionId"]
        require(sid in by_id and sid not in seen, f"Unknown or duplicate reviewed session: {sid}")
        require(note["sessionCode"] == by_id[sid]["code"], f"{sid}: session code does not match the catalog")
        seen.add(sid)
        iso_date(note["reviewedOn"])
        require(any(o["id"] == note["offeringId"] and o["hasOnDemand"] for o in by_id[sid]["offerings"]),
                f"{sid}: evidence must name the recorded offering of this session")
        require(note["basis"] in RECORDING_BASIS, f"{sid}: unsupported recording evidence")
        video = note["youtubeUrl"]
        if video is not None:
            require(isinstance(video, str) and YOUTUBE_WATCH.fullmatch(video),
                    f"{sid}: expected an official YouTube watch URL")
        require(note["basis"] != "captions-and-chapters" or video is not None,
                f"{sid}: chapter evidence requires a YouTube video")
        require(note["basis"] != "youtube-transcript" or video is not None,
                f"{sid}: transcript evidence requires a YouTube video")
        for section in NOTE_SECTIONS:
            points = note[section]
            require(isinstance(points, list) and (points or section != "summary"),
                    f"{sid}: missing or invalid {section}")
            for point in points:
                keys(point, "text atSeconds announcementId" if section == "updates" else "text atSeconds",
                     f"{sid} {section}")
                text(point["text"], f"{sid} {section}")
                require(type(point["atSeconds"]) is int and point["atSeconds"] >= 0,
                        f"{sid}: timestamps must be nonnegative seconds from the start of the recording")
                if section == "updates":
                    ref = point["announcementId"]
                    require(ref is None or ref in announcements, f"{sid}: unknown announcement {ref}")


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
    session_notes = read_session_notes(SESSION_NOTES_DIR)
    validate_session_notes(session_notes, catalog, updates)
    return event, catalog, updates, session_notes


def load_references(catalog, updates, notes):
    records = []
    for filename in REFERENCE_FILES:
        record = json.loads((DATA / filename).read_text(encoding="utf-8"))
        require(type(record["schemaVersion"]) is int and record["schemaVersion"] == 1,
                f"{filename}: unsupported schema version")
        iso_date(record["checkedOn"])
        records.append(record)
    azure, videos, links = records
    ids = validate_azure_updates(azure) | {a["id"] for a in updates["announcements"]}
    validate_session_links(videos, links, {s["code"]: s for s in catalog["sessions"]}, ids)
    for note in notes["notes"]:
        if note["youtubeUrl"]:
            require(videos["matches"].get(note["sessionCode"]) == note["youtubeUrl"],
                    f'{note["sessionCode"]}: reviewed YouTube URL does not match the session index.')
    return azure, videos, links


def read_session_notes(directory):
    require(directory.is_dir(), f"Missing session notes directory: {directory}")
    notes = []
    for path in sorted(directory.glob("*.json")):
        note = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(note, dict) and note.get("sessionCode") == path.stem,
                f"{path.name}: filename must match sessionCode")
        notes.append(note)
    return {"schemaVersion": 1, "notes": notes}

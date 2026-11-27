"""Check the public player and caption timestamps for already written session notes."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import html
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from import_sessions import FEED_URL
from site_data import NOTE_SECTIONS, load

PLAYER = re.compile(r"/Embed/video-nc/[a-f0-9-]{36}")
CUE = re.compile(r"(?m)^((?:\d+:)?\d{2}:\d{2}\.\d{3})[ \t]+-->[ \t]+((?:\d+:)?\d{2}:\d{2}\.\d{3})")


def public_url(value, host, path, *, strip_query=False):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != host or
            not path.fullmatch(parsed.path) or parsed.fragment):
        raise ValueError(f"Unexpected public {host} link")
    if strip_query:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value


def fetch(url):
    with urlopen(url, timeout=25) as response:
        if urlsplit(response.url).hostname != urlsplit(url).hostname:
            raise ValueError("Public source redirected to another host")
        return response.read().decode("utf-8-sig")


def configuration(page, name):
    start = re.search(rf"\bconst {name}\s*=\s*", page)
    if start is None:
        raise ValueError(f"No {name} in the public player")
    return json.JSONDecoder().raw_decode(page[start.end():])[0]


def title_key(value):
    value = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    return "".join(c for c in value if c.isalnum())


def caption_url(player, language="en"):
    config = configuration(player, "captionsConfiguration")
    locale = {"en": "en-US", "ja": "ja-JP"}[language]
    path = re.compile(rf"/video-[0-9]+/[a-f0-9-]{{36}}/Caption_{locale}\.vtt", re.IGNORECASE)
    found = {
        public_url(track["src"], "mediusdl.event.microsoft.com", path, strip_query=True)
        for track in config["languageList"]
        if track["srclang"] in {language, locale} and path.fullmatch(urlsplit(track["src"]).path)
    }
    if len(found) != 1:
        raise ValueError(f"Expected one distinct {locale} asset in the public player, got {len(found)}")
    return found.pop()


def seconds(timestamp):
    total = 0
    for part in timestamp.split(":"):
        total = total * 60 + float(part)
    return total


def cue_times(vtt):
    if not vtt.startswith(("WEBVTT\n", "WEBVTT\r\n", "WEBVTT ")):
        raise ValueError("Expected public WebVTT, not an HTML player or sign-in page")
    cues = [(seconds(start), seconds(end)) for start, end in CUE.findall(vtt)]
    if not cues or any(start >= end for start, end in cues) or any(
        a[0] > b[0] for a, b in zip(cues, cues[1:])
    ):
        raise ValueError("Empty or unordered WebVTT cues")
    return cues


def verify_note(note, row, asset_sessions):
    code = row["sessionCode"]
    try:
        if row["sessionId"] != note["sessionId"]:
            raise ValueError("Catalog recording belongs to another session")
        player_url = public_url(row["onDemand"], "medius.microsoft.com", PLAYER)
        if len(asset_sessions[urlsplit(player_url).path]) != 1:
            raise ValueError("One player asset is listed against multiple session IDs")
        player = fetch(player_url)
        title = re.search(r"<title>(.*?)</title>", player, re.DOTALL | re.IGNORECASE)
        if not title or title_key(title[1]) != title_key(row["title"]):
            raise ValueError("Player title does not match official catalog")
        language = "ja" if note["basis"] == "captions-ja" else "en"
        cues = cue_times(fetch(caption_url(player, language)))
        points = [point for key in NOTE_SECTIONS for point in note[key]]
        for point in points:
            timestamp = point["atSeconds"]
            if not any(start - 4 <= timestamp <= end + 4 for start, end in cues):
                raise ValueError(f"{timestamp}s does not match any caption cue")
    except (ValueError, OSError) as error:
        raise ValueError(f"{code}: {error}") from error
    return code, len(points)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_codes", nargs="+", metavar="CODE")
    args = parser.parse_args()
    _, catalog, _, notes = load()
    ids = {s["id"]: s["code"] for s in catalog["sessions"]}
    by_code = {ids[n["sessionId"]]: n for n in notes["notes"]}
    unknown = set(args.session_codes) - by_code.keys()
    if unknown:
        parser.error("No saved recording notes: " + ", ".join(sorted(unknown)))
    selected = [by_code[code] for code in dict.fromkeys(args.session_codes)]
    rows = {}
    asset_sessions = defaultdict(set)
    for row in json.loads(fetch(FEED_URL)):
        if (not row["hasOnDemand"] or row["restrictedScopes"] or
                row["excludeFromSessionScheduler"] or row["doNotPublishVideo"] or not row["onDemand"]):
            continue
        rows[row["sessionInstanceId"]] = row
        asset_sessions[urlsplit(row["onDemand"]).path].add(row["sessionId"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda n: verify_note(n, rows[n["offeringId"]], asset_sessions), selected))
    print(f"Verified public caption time references: {len(results)} sessions, "
          f"{sum(count for _, count in results)} entries.")
    print(", ".join(code for code, _ in results))


if __name__ == "__main__":
    main()

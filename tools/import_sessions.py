"""Write an allowlisted snapshot of the public Microsoft Ignite catalog."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import urlopen

CATALOG_URL = "https://ignite.microsoft.com/en-US/sessions"
ON_DEMAND_URL = CATALOG_URL + "?filter=&onDemand=1"
FEED_URL = "https://ignite.microsoft.com/api/session/all/en-US"
SPEAKER_FEED_URL = "https://ignite.microsoft.com/api/speaker/all/en-US"
JST = timezone(timedelta(hours=9), "JST")
SESSION_ID = re.compile(r"[A-Za-z0-9]+")
SESSION_CODE = re.compile(r"[A-Z]+[0-9]+[A-Z]*")
OFFERING_ID = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?")


def summarize(sessions):
    return {
        "sessions": len(sessions),
        "offerings": sum(len(s["offerings"]) for s in sessions),
        "onDemandSessions": sum(any(o["hasOnDemand"] for o in s["offerings"]) for s in sessions),
        "onDemandOfferings": sum(o["hasOnDemand"] for s in sessions for o in s["offerings"]),
        "restrictedSessions": sum(any(o["restrictedAccess"] for o in s["offerings"]) for s in sessions),
        "restrictedOfferings": sum(o["restrictedAccess"] for s in sessions for o in s["offerings"]),
    }


def speaker_directory(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a non-empty list from the public speaker directory.")

    candidates = {}
    for row in rows:
        speaker_id, name = row["speakerId"], row["displayName"]
        if not isinstance(speaker_id, str) or not speaker_id or not isinstance(name, str) or not name.strip():
            raise ValueError("Speaker directory record is missing its public ID or display name.")
        profile = {
            "id": speaker_id,
            "name": name,
            "jobTitle": row.get("jobTitle") or None,
            "company": row.get("company") or None,
            "sourceUrl": f"https://ignite.microsoft.com/en-US/speakers/{quote(speaker_id)}",
        }
        for field in ("jobTitle", "company"):
            if profile[field] is not None and not isinstance(profile[field], str):
                raise ValueError(f"Unexpected speaker {field} for {speaker_id}.")
        candidates.setdefault(speaker_id, []).append(profile)

    # The public directory can repeat an ID. Only publish records whose repeated
    # entries agree, so a conflicting profile is never selected arbitrarily.
    return {
        speaker_id: profiles[0]
        for speaker_id, profiles in candidates.items()
        if all(profile == profiles[0] for profile in profiles)
    }


def snapshot(rows, checked_on):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a non-empty list from the public catalog.")

    sessions = {}
    excluded = set()
    seen = set()
    excluded_count = 0
    for row in rows:
        session_id, offering_id = row["sessionId"], row["sessionInstanceId"]
        if not SESSION_ID.fullmatch(session_id) or not OFFERING_ID.fullmatch(offering_id):
            raise ValueError("Unexpected catalog identifier.")
        if offering_id in seen:
            raise ValueError(f"Duplicate catalog offering: {offering_id}")
        seen.add(offering_id)

        scopes = row["restrictedScopes"]
        if not isinstance(scopes, list) or type(row["excludeFromSessionScheduler"]) is not bool:
            raise ValueError("Catalog visibility fields changed; review before publishing.")
        if row["excludeFromSessionScheduler"]:
            excluded.add(session_id)
            excluded_count += 1
            continue

        info = {
            "id": session_id,
            "code": row["sessionCode"],
            "title": row["title"],
            "type": row["sessionType"]["displayValue"],
            "levels": sorted({v["displayValue"] for v in row["sessionLevel"]}),
            "topics": sorted({v["displayValue"] for v in row["topic"]}),
            "speakerNames": row.get("speakerNames") or None,
        }
        if info["speakerNames"] is not None and not isinstance(info["speakerNames"], str):
            raise ValueError(f"Unexpected speaker names for session {session_id}.")
        session = sessions.setdefault(session_id, {**info, "offerings": []})
        if any(session[key] != value for key, value in info.items()):
            raise ValueError(f"Inconsistent metadata for session {session_id}.")

        if type(row["hasOnDemand"]) is not bool or type(row["doNotPublishVideo"]) is not bool:
            raise ValueError("Catalog recording flags changed; review before publishing.")
        session["offerings"].append({
            "id": offering_id,
            "startUtc": row["startDateTime"],
            "endUtc": row["endDateTime"],
            "delivery": sorted({v["displayValue"] for v in row["deliveryTypes"]}),
            "hasOnDemand": row["hasOnDemand"] and not row["doNotPublishVideo"] and not scopes,
            "restrictedAccess": bool(scopes),
            "sourceUrl": f"{CATALOG_URL}/{offering_id}",
        })

    ordered = sorted(sessions.values(), key=lambda s: (s["code"], s["id"]))
    if not ordered:
        raise ValueError("No public sessions were found; review catalog visibility before publishing.")
    for session in ordered:
        session["offerings"].sort(key=lambda o: (o["startUtc"] is None, o["startUtc"] or "", o["id"]))
    return {
        "schemaVersion": 1,
        "checkedOn": checked_on,
        "catalogUrl": CATALOG_URL,
        "onDemandCatalogUrl": ON_DEMAND_URL,
        "sourceDataUrl": FEED_URL,
        "counts": summarize(ordered),
        "excludedSessions": len(excluded - sessions.keys()),
        "excludedOfferings": excluded_count,
        "sessions": ordered,
    }


def speaker_snapshot(rows, speaker_rows, checked_on):
    directory = speaker_directory(speaker_rows)
    sessions = {}
    for row in rows:
        if row.get("excludeFromSessionScheduler"):
            continue
        session_id, code = row["sessionId"], row["sessionCode"]
        if "speakerIds" not in row:
            record = {"speakers": [], "unresolvedSpeakers": None}
        else:
            speaker_ids = row["speakerIds"]
            if not isinstance(speaker_ids, list) or any(
                    not isinstance(value, str) or not value for value in speaker_ids):
                raise ValueError(f"Unexpected speaker IDs for session {session_id}.")
            unique_ids = list(dict.fromkeys(speaker_ids))
            record = {
                "speakers": [directory[speaker_id] for speaker_id in unique_ids if speaker_id in directory],
                "unresolvedSpeakers": sum(speaker_id not in directory for speaker_id in unique_ids),
            }
        if code in sessions and sessions[code] != record:
            raise ValueError(f"Inconsistent speaker metadata for session {session_id}.")
        sessions[code] = record
    return {
        "schemaVersion": 1,
        "checkedOn": checked_on,
        "sourceUrl": SPEAKER_FEED_URL,
        "sessions": sessions,
    }


def write_snapshot(data, output):
    document = {key: value for key, value in data.items() if key != "sessions"}
    sessions = data["sessions"]
    header = json.dumps(document, ensure_ascii=False, indent=2).removesuffix("\n}")
    records = ",\n".join("    " + json.dumps(record, ensure_ascii=False) for record in sessions)
    output.write_text(header + ',\n  "sessions": [\n' + records + "\n  ]\n}\n",
                      encoding="utf-8", newline="\n")


def write_speaker_snapshot(data, output):
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data") / "sessions.json")
    args = parser.parse_args()
    with urlopen(FEED_URL, timeout=60) as response:
        rows = json.load(response)
    with urlopen(SPEAKER_FEED_URL, timeout=60) as response:
        speaker_rows = json.load(response)
    checked_on = datetime.now(JST).date().isoformat()
    data = snapshot(rows, checked_on)
    speakers = speaker_snapshot(rows, speaker_rows, checked_on)

    # Keep one session on each line so reviews show only the records that changed.
    write_snapshot(data, args.output)
    write_speaker_snapshot(speakers, args.output.parent / "session-speakers.json")
    print(f"{args.output}: {data['counts']}; excluded offerings: {data['excludedOfferings']}")


if __name__ == "__main__":
    main()

"""Write an allowlisted snapshot of the public Microsoft Ignite catalog."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.request import urlopen

CATALOG_URL = "https://ignite.microsoft.com/en-US/sessions"
ON_DEMAND_URL = CATALOG_URL + "?filter=&onDemand=1"
FEED_URL = "https://ignite.microsoft.com/api/session/all/en-US"
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
        }
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data") / "sessions.json")
    args = parser.parse_args()
    with urlopen(FEED_URL, timeout=60) as response:
        data = snapshot(json.load(response), datetime.now(JST).date().isoformat())

    # Keep one session on each line so reviews show only the records that changed.
    sessions = data.pop("sessions")
    header = json.dumps(data, ensure_ascii=False, indent=2).removesuffix("\n}")
    records = ",\n".join("    " + json.dumps(record, ensure_ascii=False) for record in sessions)
    args.output.write_text(header + ',\n  "sessions": [\n' + records + "\n  ]\n}\n",
                           encoding="utf-8", newline="\n")
    print(f"{args.output}: {data['counts']}; excluded offerings: {data['excludedOfferings']}")


if __name__ == "__main__":
    main()

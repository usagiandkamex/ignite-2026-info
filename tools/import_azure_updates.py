"""Snapshot Azure Updates metadata with Microsoft's Ignite tag and a 2026 publication date."""

import argparse
from datetime import datetime
from html import unescape
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from import_sessions import JST

AZURE_FEED = "https://www.microsoft.com/releasecommunications/api/v2/azure"
AZURE_UPDATES = "https://azure.microsoft.com/ja-jp/updates/"
IGNITE_TAG = "Microsoft Ignite"
START = "2026-01-01"
END = "2027-01-01"
PAGE_SIZE = 50


def item_url(identity):
    return f"{AZURE_UPDATES}?id={identity}"


def fetch_page(offset):
    query = urlencode({
        "$count": "true",
        "$filter": (f"tags/any(t: t eq '{IGNITE_TAG}') and "
                    f"created ge {START}T00:00:00Z and created lt {END}T00:00:00Z"),
        "$orderby": "id asc",
        "top": PAGE_SIZE,
        "skip": offset,
    })
    with urlopen(f"{AZURE_FEED}?{query}", timeout=40) as response:
        return json.load(response)


def snapshot(read_page, checked_on):
    items = {}
    total = None
    for offset in range(0, 10000, PAGE_SIZE):
        page = read_page(offset)
        count, rows = page["@odata.count"], page["value"]
        if type(count) is not int or count < 1 or count > 10000 or total not in (None, count):
            raise ValueError("Azure Updates total changed or is invalid; rerun before publishing.")
        total = count
        if len(rows) != min(PAGE_SIZE, total - offset):
            raise ValueError(f"Azure Updates page {offset} did not return all expected records.")
        for row in rows:
            identity = row["id"]
            day = row["created"][:10]
            if not identity.isascii() or not identity.isdecimal() or identity in items:
                raise ValueError(f"Unexpected or duplicate Azure Updates ID: {identity!r}")
            if IGNITE_TAG not in row["tags"] or not START <= day < END:
                raise ValueError(f"Azure Updates row {identity} does not match the query.")
            items[identity] = {
                "id": f"az-{identity}",
                "title": " ".join(unescape(row["title"]).split()),
                "publishedOn": day,
                "sourceStatus": row["status"],
                "products": sorted({name.strip() for name in (row["products"] or []) if name.strip()}),
                "categories": sorted({name.strip() for name in (row["productCategories"] or []) if name.strip()}),
                "sourceUrl": item_url(identity),
            }
        if len(items) == total:
            break
    return {
        "schemaVersion": 1,
        "checkedOn": checked_on,
        "sourceDataUrl": AZURE_FEED,
        "sourceUrl": AZURE_UPDATES,
        "tag": IGNITE_TAG,
        "publicationFrom": START,
        "publicationBefore": END,
        "count": total,
        "items": sorted(items.values(), key=lambda a: (a["publishedOn"], a["id"]), reverse=True),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data") / "azure-updates.json")
    args = parser.parse_args()
    data = snapshot(fetch_page, datetime.now(JST).date().isoformat())
    items = data.pop("items")
    header = json.dumps(data, ensure_ascii=False, indent=2).removesuffix("\n}")
    entries = ",\n".join("    " + json.dumps(item, ensure_ascii=False) for item in items)
    args.output.write_text(header + ',\n  "items": [\n' + entries + "\n  ]\n}\n",
                           encoding="utf-8", newline="\n")
    print(f"{args.output}: {data['count']} Azure Updates posts")


if __name__ == "__main__":
    main()

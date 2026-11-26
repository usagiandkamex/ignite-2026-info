"""Generate the static Japanese guide and AI entry point from the public JSON."""

import argparse
from html import escape as h
from pathlib import Path
import shutil

from import_sessions import JST
from site_data import CATEGORIES, DATA, DELIVERY, FILES, LEVELS, ROOT, SESSION_TYPES, STAGES, TOPICS, iso_date, load, utc

WEB = ROOT / "web"
PUBLIC_URL = "https://usagiandkamex.github.io/ignite-2026-info/"
PAGES = {
    "index.html": "イベント概要",
    "sessions.html": "セッション",
    "updates.html": "製品発表",
}


def link(url, label):
    return f'<a href="{h(url)}">{h(label)}</a>'


def source_list(sources):
    return "<ul>" + "".join(f"<li>{link(s['url'], s['label'])}</li>" for s in sources) + "</ul>"


def time_range(start, end):
    first, last = (utc(v).astimezone(JST) for v in (start, end))

    def clock(dt):
        return f"{dt.hour:02}:{dt.minute:02}"

    def day(dt):
        return f"{dt.year}/{dt.month}/{dt.day}"

    date_end = "" if first.date() == last.date() else f"{day(last)} "
    return (f'<time datetime="{h(start)}">{day(first)} {clock(first)}</time>'
            f'–<time datetime="{h(end)}">{date_end}{clock(last)}</time> JST')


def event_dates(start, end):
    first, last = iso_date(start), iso_date(end)
    opening = f"{first.year} 年 {first.month} 月 {first.day} 日"
    if first == last:
        return opening
    if first.year != last.year:
        return f"{opening}〜{last.year} 年 {last.month} 月 {last.day} 日"
    if first.month != last.month:
        return f"{opening}〜{last.month} 月 {last.day} 日"
    return f"{first.year} 年 {first.month} 月 {first.day}〜{last.day} 日"


def site_page(filename, description, body, *, filters=False):
    name = PAGES[filename]
    nav = []
    for page, label in PAGES.items():
        current = ' aria-current="page"' if page == filename else ""
        nav.append(f'<a href="{page}"{current}>{label}</a>')
    theme = (WEB / "theme.css").read_text(encoding="utf-8")
    theme_script = (WEB / "theme.js").read_text(encoding="utf-8")
    scripts = '<script defer src="filter.js"></script>' if filters else ""
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(name)} | Microsoft Ignite 2026 日本語ガイド</title>
  <meta name="description" content="{h(description)}">
  <script>
{theme_script}  </script>
  <style>
{theme}  </style>
  <link rel="stylesheet" href="site.css">
  {scripts}
</head>
<body>
  <a class="skip" href="#main">本文へ移動</a>
  <header class="top"><div class="wrap top-inner">
    <a class="brand" href="index.html">Ignite 2026 日本語ガイド</a>
    <nav aria-label="メインメニュー">{"".join(nav)}</nav>
  </div></header>
  <main id="main" class="wrap" tabindex="-1">
{body}
  </main>
  <footer class="wrap">
    <p>Microsoft の公式サイトではありません。製品名・商標は各権利者に帰属します。</p>
    <p>{link("llms.txt", "AI 向けデータ案内")} · {link("https://github.com/usagiandkamex/ignite-2026-info", "GitHub リポジトリ")}</p>
  </footer>
</body>
</html>
"""


def intro(kicker, title, lead):
    return f'<header class="intro"><p class="kicker">{h(kicker)}</p><h1>{h(title)}</h1><p>{h(lead)}</p></header>'


def overview(event, catalog, updates):
    counts = catalog["counts"]
    dates = event_dates(event["startDate"], event["endDate"])
    keynotes = []
    for item in event["keynotes"]:
        replay = f' · {link(item["replayUrl"], "YouTube で録画を見る")}' if item["replayUrl"] else ""
        keynotes.append(f"""<article class="card" id="{item['sessionCode']}">
  <p class="kicker">{item['sessionCode']}</p>
  <h3>{h(item['title'])}</h3>
  <p class="meta">{time_range(item['startUtc'], item['endUtc'])}</p>
  <p>{h(item['summary'])}</p><p>{link(item['sourceUrl'], "公式セッション（録画案内）")}{replay}</p>
</article>""")
    body = f"""
{intro(f"{dates}（米国太平洋時間）", event["name"], event["summary"])}
<p class="venue">{h(event["venue"])}</p>
<div class="grid">
  <section class="card">
    <h2>{link("sessions.html", "セッションを探す")}</h2>
    <p>公式カタログの公開 {counts['sessions']:,} セッション。キーノート、技術セッション、ラボを分類・録画有無で探せます。</p>
  </section>
  <section class="card">
    <h2>{link("updates.html", "製品発表を読む")}</h2>
    <p>Book of News の {len(updates["announcements"])} 項目を日本語で要約。分野や、発表時の提供状況から探せます。</p>
  </section>
</div>
<section class="section">
  <h2>キーノート</h2>
  <div class="grid">{"".join(keynotes)}</div>
</section>
<section class="section">
  <h2>公式出典</h2>
  <p class="meta">確認日：{h(event["checkedOn"])}（日本時間） · {link("data/event.json", "イベント JSON")}</p>
  {source_list(event["sources"])}
</section>"""
    return site_page("index.html", event["summary"], body)


def select(name, label, values):
    choices = "".join(f'<option value="{h(key)}">{h(value)}</option>' for key, value in values.items())
    return (f'<label for="{name}">{h(label)}</label><select id="{name}" data-filter="{name}">'
            f'<option value="">すべて</option>{choices}</select>')


def filter_panel(*selectors):
    groups = "".join(f"<div>{item}</div>" for item in selectors)
    return f"""<section class="filters" aria-label="検索・絞り込み" data-filters hidden>
  <div class="filter-fields">
    <div class="search">
      <label for="query">キーワード</label>
      <input id="query" type="search" placeholder="製品名、タイトル、コードなど">
    </div>
    {groups}
  </div>
  <p data-count role="status" aria-live="polite"></p>
</section>
<p class="empty" data-empty hidden>条件に一致する項目がありません。</p>"""


def chips(labels):
    return " · ".join(h(label) for label in labels)


def catalog_entry(s):
    offers = s["offerings"]
    has_replay = any(o["hasOnDemand"] for o in offers)
    labels = [SESSION_TYPES[s["type"]], *[LEVELS[v] for v in s["levels"]], *[TOPICS[v] for v in s["topics"]]]
    filters = " ".join([s["code"], s["title"], s["type"], *s["levels"], *s["topics"], *labels])
    items = []
    for o in offers:
        when = "日時の掲載なし" if o["startUtc"] is None else time_range(o["startUtc"], o["endUtc"])
        delivery = [DELIVERY[v] for v in o["delivery"]]
        recorded = "オンデマンドあり" if o["hasOnDemand"] else "オンデマンドの掲載なし"
        items.append(f"<li>{when} · {chips([*delivery, recorded])} · {link(o['sourceUrl'], '公式詳細')}</li>")
    return f"""<article id="session-{s['id']}" class="card result" data-result data-text="{h(filters)}"
  data-kind="{h(s['type'])}" data-topic="{h('|'.join(s['topics']))}" data-replay="{'yes' if has_replay else 'no'}">
  <p class="kicker">{h(s['code'])}</p>
  <h2 lang="en">{link(offers[0]['sourceUrl'], s['title'])}</h2>
  <p class="meta">{chips(labels)}</p>
  <ul class="offerings">{"".join(items)}</ul>
</article>"""


def sessions_page(catalog):
    counts = catalog["counts"]
    lead = (f"公式カタログの公開 {counts['sessions']:,} セッション・{counts['offerings']:,} 開催枠。"
            f"うちオンデマンドは {counts['onDemandSessions']:,} セッション・{counts['onDemandOfferings']:,} 枠です。")
    filters = filter_panel(select("kind", "セッション種別", SESSION_TYPES),
                           select("topic", "テーマ", TOPICS),
                           select("replay", "録画", {"yes": "オンデマンドあり", "no": "オンデマンドの掲載なし"}))
    body = f"""
{intro("公式カタログの公開データ", "セッション", lead)}
<div class="note">
  <p>タイトルは公式の英語表記、開催枠の時刻は日本標準時（JST）です。アクセス制限などで除外したのは
  {catalog["excludedSessions"]:,} セッション・{catalog["excludedOfferings"]:,} 枠です。
  録画の表示は公式カタログ上の状態で、再生にはサインインが必要な場合があります。</p>
  <p class="meta">確認日：{h(catalog["checkedOn"])}（日本時間） · {link(catalog["catalogUrl"], "公式カタログ")}
  · {link(catalog["onDemandCatalogUrl"], "公式オンデマンド一覧")} · {link("data/sessions.json", "セッション JSON")}</p>
</div>
{filters}
<div class="results">{"".join(catalog_entry(s) for s in catalog["sessions"])}</div>"""
    return site_page("sessions.html", lead, body, filters=True)


def announcement_entry(a, notes):
    category = CATEGORIES[a["category"]]
    stages = [STAGES[s] for s in a["stages"]]
    search = " ".join([a["title"], a["summary"], a["category"], category, *stages, *(n["text"] for n in notes)])
    additional = "".join(
        f'<div class="followup"><p><strong>補足（{h(n["checkedOn"])} 確認）</strong>：{h(n["text"])}</p>'
        f'{source_list(n["sources"])}</div>' for n in notes
    )
    return f"""<article class="card result" id="{a['id']}" data-result data-text="{h(search)}"
  data-category="{h(a['category'])}" data-stage="{h('|'.join(a['stages']))}">
  <p class="kicker">{h(category)}</p>
  <h2>{h(a['title'])}</h2>
  <p class="meta">{chips(stages)}</p>
  <p>{h(a['summary'])}</p><p>{link(a['sourceUrl'], "公式発表・製品情報")}</p>{additional}
</article>"""


def updates_page(data):
    lead = f"Book of News の {len(data['announcements'])} 発表を、日本語の要約と公式リンクで確認できます。"
    filters = filter_panel(select("category", "分野", CATEGORIES), select("stage", "提供状況", STAGES))
    notes = {}
    for item in data["notes"]:
        notes.setdefault(item["announcementId"], []).append(item)
    body = f"""
{intro("Book of News", "新サービス・機能", lead)}
<div class="note">
  <p>提供状況は Ignite での発表時点の情報です。1 項目に複数の状態がある場合は、要約で対象の機能を区別しています。
  日本での提供、言語、契約条件、現在の状況は各公式ページをご確認ください。</p>
  <p class="meta">確認日：{h(data["checkedOn"])}（日本時間） · {link(data["bookOfNewsUrl"], "公式 Book of News")}
  · {link("data/updates.json", "製品発表 JSON")}</p>
  {source_list(data["sources"])}
</div>
{filters}
<div class="results">{"".join(announcement_entry(a, notes.get(a["id"], [])) for a in data["announcements"])}</div>"""
    return site_page("updates.html", lead, body, filters=True)


def ai_index(event, catalog, updates):
    counts = catalog["counts"]
    return f"""# Microsoft Ignite 2026 日本語ガイド

> Microsoft Ignite 2026 の非公式ガイド。日本語の静的ページと同じ情報を、公開 JSON で提供します。

イベント会期は米国太平洋時間。開催枠の JSON の時刻は UTC（末尾 Z）、HTML は日本標準時（JST）です。
提供状況は Ignite 発表時点のもので、現在または日本で利用できることは保証しません。
カタログに非公開・制限付きの枠は含まれません。録画フラグは認証なしでの視聴を保証しません。

## 公開データ

- [イベントとキーノート]({PUBLIC_URL}data/event.json): 確認日 {event['checkedOn']}。開催概要、両キーノート、公式出典。
- [セッション]({PUBLIC_URL}data/sessions.json): 確認日 {catalog['checkedOn']}。公開 {counts['sessions']} セッション、{counts['offerings']} 開催枠。`offerings` 内に公式詳細 URL と録画フラグ。
- [製品発表]({PUBLIC_URL}data/updates.json): 確認日 {updates['checkedOn']}。Book of News の全 {len(updates['announcements'])} 項目の日本語要約、提供状況、公式出典。

## 参照先

- [日本語ガイド]({PUBLIC_URL}): 概要、検索可能なセッション一覧と製品発表。
- [仕様・収録範囲](https://github.com/usagiandkamex/ignite-2026-info#ai-向け公開データ): JSON の項目、適用範囲、更新方法。
- [公式カタログ]({catalog['catalogUrl']}): 掲載情報の確認先。
- [公式 Book of News]({updates['bookOfNewsUrl']}): 発表内容の確認先。
"""


def build(output):
    event, catalog, updates = load()
    output.mkdir(parents=True, exist_ok=True)
    (output / "data").mkdir(exist_ok=True)
    files = {
        "index.html": overview(event, catalog, updates),
        "sessions.html": sessions_page(catalog),
        "updates.html": updates_page(updates),
        "llms.txt": ai_index(event, catalog, updates),
    }
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")
    for name in FILES:
        shutil.copyfile(DATA / name, output / "data" / name)
    for name in ("filter.js", "site.css"):
        shutil.copyfile(WEB / name, output / name)
    print(f"Built {output}: {catalog['counts']['sessions']} sessions, {len(updates['announcements'])} announcements")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    build(parser.parse_args().output)

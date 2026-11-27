"""Generate the static Japanese guide and AI entry point from the public JSON."""

import argparse
from collections import Counter
from html import escape as h
import json
from pathlib import Path
import shutil

from import_sessions import JST
from site_data import (
    AZURE_STAGES, CATEGORIES, DATA, DELIVERY, FILES, LEVELS, NOTE_SECTIONS, NOTE_STATES,
    RECORDING_BASIS, ROOT, SESSION_TYPES, STAGES, TOPICS, iso_date, load, load_references, utc,
)

WEB = ROOT / "web"
PUBLIC_URL = "https://usagiandkamex.github.io/ignite-2026-info/"
PAGES = {
    "index.html": "イベント概要",
    "sessions.html": "セッション",
    "updates.html": "製品発表",
}
UPDATE_SOURCES = {"book": "Book of News", "azure": "Azure Updates"}


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


def site_page(section, description, body, *, filters=False, title=None, prefix=""):
    name = title or PAGES[section]
    nav = []
    for page, label in PAGES.items():
        current = ' aria-current="page"' if page == section and title is None else ""
        nav.append(f'<a href="{prefix}{page}"{current}>{label}</a>')
    theme = (WEB / "theme.css").read_text(encoding="utf-8")
    theme_script = (WEB / "theme.js").read_text(encoding="utf-8")
    scripts = f'<script defer src="{prefix}filter.js"></script>' if filters else ""
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
  <link rel="stylesheet" href="{prefix}site.css">
  {scripts}
</head>
<body>
  <a class="skip" href="#main">本文へ移動</a>
  <header class="top"><div class="wrap top-inner">
    <a class="brand" href="{prefix}index.html">Ignite 2026 日本語ガイド</a>
    <nav aria-label="メインメニュー">{"".join(nav)}</nav>
  </div></header>
  <main id="main" class="wrap" tabindex="-1">
{body}
  </main>
  <footer class="wrap">
    <p>Microsoft の公式サイトではありません。製品名・商標は各権利者に帰属します。</p>
    <p>{link(prefix + "llms.txt", "AI 向けデータ案内")} · {link("https://github.com/usagiandkamex/ignite-2026-info", "GitHub リポジトリ")}</p>
  </footer>
</body>
</html>
"""


def intro(kicker, title, lead):
    return f'<header class="intro"><p class="kicker">{h(kicker)}</p><h1>{h(title)}</h1><p>{h(lead)}</p></header>'


def detail_path(session):
    return f"session/{session['code']}.html"


def detail_data_path(session):
    return f"data/sessions/{session['code']}.json"


def overview(event, catalog, updates, azure):
    counts = catalog["counts"]
    dates = event_dates(event["startDate"], event["endDate"])
    by_code = {s["code"]: s for s in catalog["sessions"]}
    keynotes = []
    for item in event["keynotes"]:
        replay = f' · {link(item["replayUrl"], "YouTube で録画を見る")}' if item["replayUrl"] else ""
        detail = link(detail_path(by_code[item["sessionCode"]]), "セッション詳細")
        keynotes.append(f"""<article class="card" id="{item['sessionCode']}">
  <p class="kicker">{item['sessionCode']}</p>
  <h3>{h(item['title'])}</h3>
  <p class="meta">{time_range(item['startUtc'], item['endUtc'])}</p>
  <p>{h(item['summary'])}</p><p>{detail} · {link(item['sourceUrl'], "公式セッション（録画案内）")}{replay}</p>
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
    <p>Book of News の日本語要約 {len(updates["announcements"])} 件と、Ignite タグ付き Azure Updates {azure["count"]} 件を探せます。</p>
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


def session_labels(s):
    return [SESSION_TYPES[s["type"]], *[LEVELS[v] for v in s["levels"]], *[TOPICS[v] for v in s["topics"]]]


def offerings_list(s):
    items = []
    for o in s["offerings"]:
        when = "日時の掲載なし" if o["startUtc"] is None else time_range(o["startUtc"], o["endUtc"])
        delivery = [DELIVERY[v] for v in o["delivery"]]
        recorded = "オンデマンドあり" if o["hasOnDemand"] else "オンデマンドの掲載なし"
        access = ["参加条件あり"] if o["restrictedAccess"] else []
        items.append(f"<li>{when} · {chips([*delivery, *access, recorded])} · {link(o['sourceUrl'], '公式詳細')}</li>")
    return f'<ul class="offerings">{"".join(items)}</ul>'


def note_status(s, note):
    if note is not None:
        return "reviewed"
    return "pending" if any(o["hasOnDemand"] for o in s["offerings"]) else "unlisted"


def catalog_entry(s, note, video):
    state = note_status(s, note)
    labels = session_labels(s)
    highlights = [p["text"] for key in NOTE_SECTIONS for p in note[key]] if note else []
    filters = " ".join([s["code"], s["title"], s["type"], *s["levels"], *s["topics"], *labels, *highlights])
    return f"""<article id="session-{s['code']}" class="card result" data-result data-text="{h(filters)}"
  data-kind="{h(s['type'])}" data-topic="{h('|'.join(s['topics']))}"
  data-replay="{'no' if state == 'unlisted' else 'yes'}" data-notes="{state}" data-youtube="{'yes' if video else 'no'}">
  <p class="kicker">{h(s['code'])}</p>
  <h2 lang="en">{link(detail_path(s), s['title'])}</h2>
  <p class="meta">{chips(labels)} · {h(NOTE_STATES[state])}</p>
  {f'<p>{link(video, "公式 YouTube")}</p>' if video else ''}
  {offerings_list(s)}
</article>"""


def sessions_page(catalog, notes, videos):
    counts = catalog["counts"]
    lead = (f"公式カタログの公開 {counts['sessions']:,} セッション・{counts['offerings']:,} 開催枠。"
            f"うちオンデマンドは {counts['onDemandSessions']:,} セッション・{counts['onDemandOfferings']:,} 枠です。")
    filters = filter_panel(select("kind", "セッション種別", SESSION_TYPES),
                           select("topic", "テーマ", TOPICS),
                           select("replay", "録画", {"yes": "オンデマンドあり", "no": "オンデマンドの掲載なし"}),
                           select("notes", "要約の確認状況", NOTE_STATES),
                           select("youtube", "公式 YouTube", {"yes": "紐づけ済み", "no": "未確認"}))
    body = f"""
{intro("公式カタログの公開データ", "セッション", lead)}
<div class="note">
  <p>録画の有無にかかわらず、公式カタログの掲載セッションをすべて表示します。参加条件がある
  {counts["restrictedSessions"]:,} セッション・{counts["restrictedOfferings"]:,} 枠も掲載しています。
  タイトルは公式の英語表記、開催枠の時刻は日本標準時（JST）です。
  参加条件・録画の視聴条件は公式ページをご確認ください。</p>
  <p>各セッションに詳細ページがあります。録画資料に基づく要約はオンデマンド
  {counts["onDemandSessions"]:,} 件のうち {len(notes):,} 件です。公式 YouTube との紐づけは {len(videos):,} 件です。</p>
  <p class="meta">確認日：{h(catalog["checkedOn"])}（日本時間） · {link(catalog["catalogUrl"], "公式カタログ")}
  · {link(catalog["onDemandCatalogUrl"], "公式オンデマンド一覧")} · {link("data/sessions.json", "カタログ JSON")}</p>
</div>
{filters}
<div class="results">{"".join(catalog_entry(s, notes.get(s["id"]), videos.get(s["code"])) for s in catalog["sessions"])}</div>"""
    return site_page("sessions.html", lead, body, filters=True)


def timestamp(seconds):
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return (f"{hours:d}:" if hours else "") + f"{minutes:02d}:{seconds:02d}"


def detail_page(s, note, video, update_links):
    state = note_status(s, note)
    details = {
        "pending": "公式カタログにオンデマンドの案内がありますが、内容はまだ確認していません。",
        "unlisted": "公式カタログに公開録画の掲載がないため、話された内容・アップデート・事例・Tips は未確認です。",
    }
    if note:
        source = next(o["sourceUrl"] for o in s["offerings"] if o["id"] == note["offeringId"])
        evidence = link(source, "確認した開催枠の公式録画ページ")
        sections = []
        for key, title in NOTE_SECTIONS.items():
            items = []
            for point in note[key]:
                ref = point.get("announcementId")
                related = f' · {link("../updates.html#" + ref, "関連する公式発表")}' if ref else ""
                when = timestamp(point["atSeconds"])
                items.append(f'<li><strong>{when}</strong> {h(point["text"])}{related}</li>')
            content = f'<ul>{"".join(items)}</ul>' if items else "<p>確認した範囲では掲載できる情報を確認できませんでした。</p>"
            sections.append(f'<section class="section card"><h2>{title}</h2>{content}</section>')
        review = f"""<div class="note">
  <p>{h(RECORDING_BASIS[note["basis"]])}の各時刻前後を参照した要約です。録画全編を確認したことを示すものではありません。
  時刻は公式イベント録画の目安で、YouTube 版では編集によりずれる場合があります。記載の提供状況は講演時点です。</p>
  <p class="meta">確認日：{h(note["reviewedOn"])}（日本時間） · {evidence}</p>
</div>{"".join(sections)}"""
    else:
        review = f'<div class="note"><p>{details[state]}推測による要約は掲載していません。</p></div>'
    video_html = f'<p>{link(video, "公式 YouTube 録画")}</p>' if video else "<p>対応する公式 YouTube 動画は未確認です。</p>"
    related = "".join(
        f'<li>{link("../updates.html#" + item["id"], item["title"])} — {h(item["context"])}</li>'
        for item in update_links
    )
    update_html = f'<ul>{related}</ul>' if related else "<p>個別に対応付けた製品更新はまだありません。</p>"
    body = f"""
<p class="section">{link("../sessions.html#session-" + s['code'], "セッション一覧に戻る")}</p>
<header class="intro">
  <p class="kicker">{h(s["code"])}</p><h1 lang="en">{h(s["title"])}</h1>
  <p>{chips(session_labels(s))} · {NOTE_STATES[state]}</p>
</header>
<section class="section card"><h2>録画と関連アップデート</h2>{video_html}{update_html}</section>
{review}
<section class="section card"><h2>開催枠・公式リンク</h2>{offerings_list(s)}</section>
<p class="meta">{link("../" + detail_data_path(s), "このセッションの JSON")}</p>"""
    return site_page("sessions.html", f'{s["code"]}：{NOTE_STATES[state]}',
                     body, title=s["title"], prefix="../")


def announcement_entry(a, notes, sessions):
    category = CATEGORIES[a["category"]]
    stages = [STAGES[s] for s in a["stages"]]
    search = " ".join([a["title"], a["summary"], a["category"], category, *stages, *(n["text"] for n in notes)])
    additional = "".join(
        f'<div class="followup"><p><strong>補足（{h(n["checkedOn"])} 確認）</strong>：{h(n["text"])}</p>'
        f'{source_list(n["sources"])}</div>' for n in notes
    )
    return f"""<article class="card result" id="{a['id']}" data-result data-text="{h(search)}"
  data-source="book" data-category="{h(a['category'])}" data-stage="{h('|'.join(a['stages']))}">
  <p class="kicker">{h(category)}</p>
  <h2>{h(a['title'])}</h2>
  <p class="meta">{chips(stages)}</p>
  <p>{h(a['summary'])}</p><p>{link(a['sourceUrl'], "公式発表・製品情報")}</p>{additional}{update_session_list(sessions)}
</article>"""


def update_session_list(sessions):
    return (f'<p class="meta">関連セッション：{", ".join(link(detail_path(s), s["code"]) for s in sessions)}</p>'
            if sessions else "")


def azure_update_entry(item, sessions):
    stage = AZURE_STAGES[item["sourceStatus"]]
    products = chips(item["products"])
    search = " ".join([item["title"], *item["products"], *item["categories"], STAGES[stage]])
    return f"""<article class="card result" id="{item['id']}" data-result data-text="{h(search)}"
  data-source="azure" data-category="Azure" data-stage="{stage}">
  <p class="kicker">Azure Updates · Microsoft Ignite</p>
  <h2 lang="en">{h(item["title"])}</h2>
  <p class="meta">{h(item["publishedOn"])}（公開日 UTC） · {h(STAGES[stage])}</p>
  {f'<p>{products}</p>' if products else ''}
  <p>{link(item["sourceUrl"], "Azure の公式更新情報")}</p>{update_session_list(sessions)}
</article>"""


def updates_page(data, azure, sessions_by_update):
    lead = (f"Book of News の発表 {len(data['announcements'])} 件と、"
            f"Azure Updates の「Microsoft Ignite」タグ付き投稿 {azure['count']} 件。")
    filters = filter_panel(select("source", "出典", UPDATE_SOURCES),
                           select("category", "分野", CATEGORIES), select("stage", "提供状況", STAGES))
    notes = {}
    for item in data["notes"]:
        notes.setdefault(item["announcementId"], []).append(item)
    body = f"""
{intro("Book of News / Azure Updates", "新サービス・機能", lead)}
<div class="note">
  <p>Book of News は発表時点の日本語要約です。Azure Updates は、2026 年公開で公式タグが付く投稿を原題と
  フィードの提供状況で掲載しています。同じ機能が両方に載る場合や、公開時期・提供状況の記述が異なる場合があります。
  日本での提供や契約条件は、各公式ページをご確認ください。</p>
  <p class="meta">確認日：{h(data["checkedOn"])}（日本時間） · {link(data["bookOfNewsUrl"], "公式 Book of News")}
  · {link("data/updates.json", "Book of News JSON")} · {link("data/azure-updates.json", "Azure Updates JSON")}</p>
  <p class="meta">Azure Updates 確認日：{h(azure["checkedOn"])}（日本時間）</p>
  {source_list(data["sources"])}
</div>
{filters}
<div class="results">{"".join(announcement_entry(a, notes.get(a["id"], []), sessions_by_update.get(a["id"], [])) for a in data["announcements"])}
{"".join(azure_update_entry(a, sessions_by_update.get(a["id"], [])) for a in azure["items"])}</div>"""
    return site_page("updates.html", lead, body, filters=True)


def ai_index(event, catalog, updates, notes, azure, videos):
    counts = catalog["counts"]
    opening = next(s for s in catalog["sessions"] if s["code"] == "KEY01")
    return f"""# Microsoft Ignite 2026 日本語ガイド

> Microsoft Ignite 2026 の非公式ガイド。日本語の静的ページと同じ情報を、公開 JSON で提供します。

イベント会期は米国太平洋時間。開催枠の JSON の時刻は UTC（末尾 Z）、HTML は日本標準時（JST）です。
提供状況は Ignite 発表時点のもので、現在または日本で利用できることは保証しません。
公式カタログに掲載された参加条件付きの枠も含みます。`restrictedAccess` は参加条件ありを示し、条件の詳細や制限された資料は掲載しません。
録画フラグは認証なしでの視聴を保証しません。

## 公開データ

- [イベントとキーノート]({PUBLIC_URL}data/event.json): 確認日 {event['checkedOn']}。開催概要、両キーノート、公式出典。
- [セッションカタログ]({PUBLIC_URL}data/sessions.json): 確認日 {catalog['checkedOn']}。公開 {counts['sessions']} セッション、{counts['offerings']} 開催枠。オンデマンド案内 {counts['onDemandSessions']} セッションのうち、{len(notes)} セッションに確認済みの要約があります。`recordingReview.reviewedSessionCodes` で確認済みの個別 JSON を探せます。
- [個別セッション JSON の例]({PUBLIC_URL}{detail_data_path(opening)}): 開幕キーノート。公式メタデータ、録画の確認状況、話の要点、アップデート、事例、Tips。
- [製品発表]({PUBLIC_URL}data/updates.json): 確認日 {updates['checkedOn']}。Book of News の全 {len(updates['announcements'])} 項目の日本語要約、提供状況、公式出典。
- [Azure Updates：Microsoft Ignite タグ]({PUBLIC_URL}data/azure-updates.json): 2026 年公開の公式タグ付き投稿 {azure['count']} 件。原題と公式フィードの提供状況。
- [公式 YouTube 録画の対応表]({PUBLIC_URL}data/session-videos.json): セッションコードで検索できる照合済みの {len(videos)} 動画リンク。

各セッションの詳細はカタログの `sessions[].code`（例: `BRK449`）を使い、`data/sessions/{{code}}.json` で取得できます。人向け HTML は `session/{{code}}.html` です。
個別 JSON の `recordingReview.status` は `reviewed`（要約あり）、`pending`（オンデマンド案内あり・内容未確認）、`unlisted`（録画の掲載なし）。
未確認なら `recordingReview.note` は `null` です。記入済みの場合、`offeringId` は確認した開催枠、`atSeconds` はその録画の開始からの秒数です。
個別 JSON の `relatedUpdates` には、確認した関連資料のみを記録します。`id` が `bon-` の項目は Book of News、`az-` は Azure Updates を参照します。

## 参照先

- [日本語ガイド]({PUBLIC_URL}): 概要、検索可能なセッション一覧と製品発表。
- [仕様・収録範囲](https://github.com/usagiandkamex/ignite-2026-info#ai-向け公開データ): JSON の項目、適用範囲、更新方法。
- [公式カタログ]({catalog['catalogUrl']}): 掲載情報の確認先。
- [公式 Book of News]({updates['bookOfNewsUrl']}): 発表内容の確認先。
"""


def build(output):
    event, catalog, updates, session_notes = load()
    azure, video_data, links = load_references(catalog, updates, session_notes)
    videos = video_data["matches"]
    notes = {n["sessionId"]: n for n in session_notes["notes"]}
    all_updates = {a["id"]: a for a in [*updates["announcements"], *azure["items"]]}
    session_updates = {}
    sessions_by_update = {}
    for session in catalog["sessions"]:
        code = session["code"]
        note = notes.get(session["id"])
        refs = {entry["id"]: entry["context"] for entry in links["matches"].get(code, [])}
        for point in note["updates"] if note else []:
            if point["announcementId"]:
                refs.setdefault(point["announcementId"], "録画要約に出典時刻のある関連発表です。")
        session_updates[code] = [
            {"id": identity, "title": all_updates[identity]["title"], "sourceUrl": all_updates[identity]["sourceUrl"],
             "context": context} for identity, context in refs.items()
        ]
        for identity in refs:
            sessions_by_update.setdefault(identity, []).append(session)
    output.mkdir(parents=True, exist_ok=True)
    (output / "data").mkdir(exist_ok=True)
    (output / "data" / "session-notes.json").unlink(missing_ok=True)
    details = output / "session"
    data_details = output / "data" / "sessions"
    details.mkdir(exist_ok=True)
    data_details.mkdir(exist_ok=True)
    codes = {s["code"] for s in catalog["sessions"]}
    for folder, extension in ((details, ".html"), (data_details, ".json")):
        for path in folder.glob(f"*{extension}"):
            if path.stem not in codes:
                path.unlink()
    files = {
        "index.html": overview(event, catalog, updates, azure),
        "sessions.html": sessions_page(catalog, notes, videos),
        "updates.html": updates_page(updates, azure, sessions_by_update),
        "llms.txt": ai_index(event, catalog, updates, notes, azure, videos),
    }
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")
    states = Counter()
    for s in catalog["sessions"]:
        note = notes.get(s["id"])
        state = note_status(s, note)
        states[state] += 1
        video = videos.get(s["code"])
        related = session_updates[s["code"]]
        (output / detail_path(s)).write_text(detail_page(s, note, video, related), encoding="utf-8", newline="\n")
        write_json(output / detail_data_path(s), {
            "schemaVersion": 1,
            "catalogCheckedOn": catalog["checkedOn"],
            "session": s,
            "recordingReview": {"status": state, "note": note},
            "youtubeUrl": video,
            "relatedUpdates": related,
        })
    for name in FILES:
        if name != "sessions.json":
            shutil.copyfile(DATA / name, output / "data" / name)
    for name in ("azure-updates.json", "session-videos.json"):
        shutil.copyfile(DATA / name, output / "data" / name)
    write_json(output / "data" / "sessions.json", {
        **catalog,
        "recordingReview": {
            "counts": {state: states[state] for state in NOTE_STATES},
            "reviewedSessionCodes": sorted(n["sessionCode"] for n in notes.values()),
        },
        "linkedYouTubeSessionCodes": sorted(videos),
    }, indent=None)
    for name in ("filter.js", "site.css"):
        shutil.copyfile(WEB / name, output / name)
    print(f"Built {output}: {catalog['counts']['sessions']} sessions, {len(notes)} recording notes, "
          f"{len(updates['announcements'])} announcements, {azure['count']} tagged Azure updates, "
          f"{len(videos)} YouTube links")


def write_json(path, value, *, indent=2):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    build(parser.parse_args().output)

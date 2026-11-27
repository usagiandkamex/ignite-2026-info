# Microsoft Ignite 2026 日本語ガイド

Microsoft Ignite 2026 の開催概要、キーノート、セッション、製品発表をまとめた非公式ガイドです。
日本語サイトと AI 向け JSON は同じデータから公開します。

公開先（GitHub Pages の設定・デプロイ後）：<https://usagiandkamex.github.io/ignite-2026-info/>

## AI 向け公開データ

Pages の `/ignite-2026-info/llms.txt` が入口です。次の JSON は同じサイトの `data/` に置かれます。

| データ | 内容 |
| --- | --- |
| [`event.json`](data/event.json) | 開催概要、米国太平洋時間の会期、開幕・パートナーキーノート、日本語要約、出典、確認済みの場合の公開録画 URL。 |
| [`sessions.json`](data/sessions.json) | 公開セッションのカタログ。`sessions[].id` で個別 JSON を取得できます。公開版には `recordingReview.counts` と `reviewedSessionIds` が加わり、要約閲覧・収録状況の確認に使えます。 |
| `data/sessions/{id}.json` | 個別セッションの公式メタデータ、収録状況、確認済みの場合は日本語の録画要約。 |
| [`updates.json`](data/updates.json) | Book of News 全 59 発表項目の独自の日本語要約。`id` は元の Book of News 項目 ID に対応。各項目に分野、発表時の提供区分と公式出典があります。 |

- `schemaVersion: 1`、`checkedOn` と `reviewedOn` は日本時間の出典確認日（`YYYY-MM-DD`）。`startUtc` / `endUtc` は UTC（末尾 `Z`）。本会期と個々の開催枠の時刻は別に扱います。
- セッションの英語タイトル・分類値は公式表記。HTML では分類名を日本語にし、日時を JST で表示します。`hasOnDemand` はカタログ上で録画が案内されているという意味で、認証なしの視聴可否ではありません。
- 全公開セッションの詳細ページは `session/{id}.html`、個別 JSON は `data/sessions/{id}.json` です。`id` はカタログの `sessions[].id` です。個別 JSON の `recordingReview.status` は `reviewed`、`pending`（オンデマンド案内あり・内容未確認）、`unlisted`（録画の掲載なし）です。未確認なら `recordingReview.note` は `null`。これは「紹介されたアップデート・事例・Tips が存在しなかった」という意味ではありません。
- 録画要約の `atSeconds` は `offeringId` で示す公式イベント録画の開始からの秒数です。`basis` は公式英語字幕（`captions`）、英語字幕と YouTube チャプター（`captions-and-chapters`）、公式日本語字幕（`captions-ja`）のいずれかです。各時刻の前後を参照した要約であり、全編を確認したことは示しません。`summary` / `updates` / `cases` / `tips` を分け、確認した範囲で根拠を拾えなかった欄は空配列です。`announcementId` がある更新は `updates.json` の項目に対応します。YouTube 版の編集で時刻がずれる場合があります。
- `counts` は収録件数。`excludedSessions` は全枠が除外されたセッション数、`excludedOfferings` は除外された枠数です。アクセス制限つきのラボなどは収録せず、公式カタログへ案内します。セッション本文、スライド、動画、認証情報は配布しません。
- `stages` は `ga`（一般提供）、`preview`、`frontier`（Frontier 対象）、`rollout`（順次展開）、`planned`、`announced`。複数の値がある場合は、要約でどの機能がどの状態か区別します。発表時点の情報であり、日本での提供を保証するものではありません。`notes` は地域などの追加情報で、`announcementId`、確認日、個別の出典を持ちます。

## ビルドと手動更新

Python 3.12 以上（外部パッケージ不要）で実行します。

```text
python -m unittest discover -s tests
python tools/build.py
python -m http.server 8000 --directory _site
```

ローカルでは `http://localhost:8000/` で確認できます。公開用 HTML は `_site` だけに生成され、通常はコミットしません。

1. セッションを更新する場合は `python tools/import_sessions.py` をリポジトリのルートから実行します。公式サイトがログインなしで使うカタログデータから、公開に必要なフィールドだけを抽出します。差分に加え、公開・除外の件数およびオンデマンド一覧を公式画面と照合します。
2. イベント・製品発表は対応する JSON を編集します。Book of News の本文付き発表見出しと突合し、転載ではなく独自に要約します。地域、ライセンス、予定日などを追記する場合は、公式出典を付けて発表時の状態と区別します。
3. 検証とビルドを行い、PR で出典と差分をレビューします。定期取得や自動書き換えはありません。

### 録画要約を追加する

1. セッション一覧で「オンデマンドあり・内容未確認」を選び、公式ページで対象の開催枠を確認します。別の開催枠や編集版の時刻は混ぜません。
2. 公開録画の字幕を基本とし、公式 YouTube のチャプターや利用可能な場合の [Ask YouTube](https://support.google.com/youtube/answer/14110396) は該当箇所を探す手掛かりにします。AI の回答だけを根拠にせず、録画・字幕で照合します。
3. 発言内容を独自の日本語で短く要約し、[`data/session-notes/`](data/session-notes) の `{sessionId}.json` に確認日と時刻を追加します。未確認のセッションに空ファイルは作りません。個別 JSON と HTML はビルド時に生成するので、録画要約の編集はここだけです。タイトルや概要から内容を推測したり、録画や字幕全文をコミットしたりしません。

カタログに字幕リンクがなくても、公式の公開プレーヤー内で字幕を選べることがあります。
`python tools/check_recording_notes.py BRK240 BRK223` は、記入済みの要約について公開カタログとプレーヤーの結び付き、参照した字幕の形式、時刻を確認します。字幕は保存せず、文章の意味や提供状況の正しさは別途レビューしてください。

## GitHub Pages の初回公開

リポジトリ管理者が **Settings → Pages → Build and deployment → Source** を **GitHub Actions** に設定します。
検証済みの変更を `main` にマージすると、`Ignite guide` ワークフローが HTML・JSON・`llms.txt` をデプロイします。
設定がマージ後になった場合は、Actions の同ワークフローを `main` で手動実行できます。
公開後、トップページ、`llms.txt`、各一括 JSON と個別セッションの JSON にアクセスして確認してください。

Microsoft の公式プロジェクトではありません。Microsoft や各製品の名称・商標は各権利者に帰属します。リポジトリの MIT ライセンスは、リンク先の資料や商標には適用されません。

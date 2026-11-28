# Microsoft Ignite 2026 日本語ガイド

Microsoft Ignite 2026 の開催概要、キーノート、セッション、製品発表をまとめた非公式ガイドです。
日本語サイトと AI 向け JSON は同じデータから公開します。

公開先（GitHub Pages の設定・デプロイ後）：<https://usagiandkamex.github.io/ignite-2026-info/>

## AI 向け公開データ

Pages の `/ignite-2026-info/llms.txt` が入口です。次の JSON は同じサイトの `data/` に置かれます。

| データ | 内容 |
| --- | --- |
| [`event.json`](data/event.json) | 開催概要、米国太平洋時間の会期、開幕・パートナーキーノート、日本語要約、出典、確認済みの場合の公開録画 URL。 |
| [`sessions.json`](data/sessions.json) | 一覧・検索用の軽量カタログ。タイトル、コード、開催枠、スピーカー名を収録。`sessions[].code` から対象の個別 JSON を取得できます。 |
| `data/sessions/{code}.json` | 個別セッションの公式メタデータ、スピーカーの役職・所属・プロフィール URLと、一部スピーカーの担当製品・活動内容の日本語要約、確認済みの録画要約。例: `data/sessions/BRK449.json`。 |
| [`updates.json`](data/updates.json) | Book of News 全 59 発表項目の独自の日本語要約。`id` は元の Book of News 項目 ID に対応。各項目に分野、発表時の提供区分と公式出典があります。 |
| [`azure-updates.json`](data/azure-updates.json) | 公式 Azure Updates の `Microsoft Ignite` タグ付き・2026 年公開の投稿。公開版は確認済みの日本語概要と技術記事も収録します。 |
| [`session-videos.json`](data/session-videos.json) | 公式 YouTube 動画の対応表。要約の有無にかかわらず、照合できたセッションだけを掲載します。 |
| [`recording-sources.json`](data/recording-sources.json) | 公式プレーヤーを照合したオンデマンド枠の ID、字幕言語、チャプター開始秒。録画内容の要約ではありません。 |

- `schemaVersion: 1`、`checkedOn` と `reviewedOn` は日本時間の出典確認日（`YYYY-MM-DD`）。`startUtc` / `endUtc` は UTC（末尾 `Z`）。本会期と個々の開催枠の時刻は別に扱います。
- `sessions.json` は一覧向けにスピーカー名だけを含み、役職・所属・プロフィール URL は含みません。AI はこの一覧で対象を特定してから `data/sessions/{code}.json` を取得してください。個別 JSON の `speakers` に公式プロフィールを収録し、`unresolvedSpeakers` は照合できなかった ID 数です。プロフィールの確認日は個別 JSON の元データ `data/session-speakers.json` に記録しています。スピーカー名の文字列を分割して ID と推測で結び付けません。
- `speaker-editorial.json` は、公式 Ignite スピーカープロフィールで確認した担当製品・活動内容の日本語要約です。公式プロフィール ID と URL で照合し、情報のあるスピーカーだけ個別 JSON と詳細ページに表示します。公式プロフィールへのリンクは各スピーカー名にあります。
- セッションの英語タイトル・分類値は公式表記。HTML では分類名を日本語にし、日時を JST で表示します。`hasOnDemand` はカタログ上で録画が案内されているという意味で、認証なしの視聴可否ではありません。
- 公式セッションコード（`BRK449` など）を `session/{code}.html` と `data/sessions/{code}.json` に使います。`sessions[].id` は公式の内部 ID で、開催枠との関連付け用です。個別 JSON の `recordingReview.status` は `reviewed`、`pending`（オンデマンド案内あり・内容未確認）、`unlisted`（公開録画の案内なし）です。未確認なら `recordingReview.note` は `null`。これは「紹介されたアップデート・事例・Tips が存在しなかった」という意味ではありません。
- 録画要約の `atSeconds` は録画開始からの秒数です。公式イベント録画を参照した場合、`offeringId` が開催枠を示し、`basis` は公式英語字幕（`captions`）、英語字幕と YouTube チャプター（`captions-and-chapters`）、公式日本語字幕（`captions-ja`）のいずれかです。公式 YouTube の文字起こしを参照した場合は `basis` が `youtube-transcript` になり、時刻は `youtubeUrl` の録画を指します。版によって編集が異なることがあります。各時刻の前後を参照した要約であり、全編を確認したことは示しません。`summary` / `updates` / `cases` / `tips` を分け、確認した範囲で根拠を拾えなかった欄は空配列です。`announcementId` がある更新は `updates.json` の項目に対応します。
- `counts` は収録件数。参加条件のあるラボも、公開ページで確認できるセッション情報と開催枠を収録し、`restrictedAccess` で区別します。参加資格の内部データ、制限付きの録画・資料は収録しません。`excludedSessions` と `excludedOfferings` は、公式にスケジューラー非掲載と指定された項目だけを数えます。
- `stages` は `ga`（一般提供）、`preview`、`frontier`（Frontier 対象）、`rollout`（順次展開）、`planned`、`announced`。複数の値がある場合は、要約でどの機能がどの状態か区別します。発表時点の情報であり、日本での提供を保証するものではありません。`notes` は地域などの追加情報で、`announcementId`、確認日、個別の出典を持ちます。
- 個別 JSON の `youtubeUrl` は照合済みの公式動画だけを指します。`relatedUpdates` の `bon-` は Book of News、`az-` は Azure Updates の ID です。録画内で触れた発表と、同じ製品についての参考情報を `context` で区別します。
- `technicalArticles` は関連発表を補足する公式記事で、記事自体が録画で紹介されたことは示しません。`relatedUpdateIds` で記事と関連発表をたどれます。
- `recordingSource` は、公式プレーヤーを照合した開催枠の URL、字幕の言語、チャプター開始時刻です。字幕のファイル URL や本文は配布しません。収録対象外のセッションでは `null` です。
- 公開版 Azure Updates の `summaryJa` は日本語概要です。`statusComparison` はフィードの `feedStage` と原題の `headlineStage` を分けます。原題が非公開・限定プレビューなら `restrictedPreview: true`。限定プレビューに対するフィードの「開発中」は矛盾とみなさず、一般提供とプレビューなどの矛盾は `conflict: true` とし、専用の区分に表示します。

## ビルドと手動更新

Python 3.12 以上（外部パッケージ不要）で実行します。
UI は [Fluent 2](https://fluent2.microsoft.design/) の文字組み・レイアウト・コンポーネントの考え方に沿い、ネイティブ HTML と `web/site.css` で実装しています。JavaScript が無効でも一覧と詳細を閲覧できます。

```text
python -m unittest discover -s tests
python tools/build.py
python -m http.server 8000 --directory _site
```

ローカルでは `http://localhost:8000/` で確認できます。公開用 HTML は `_site` だけに生成され、通常はコミットしません。

1. セッションを更新する場合は `python tools/import_sessions.py` をリポジトリのルートから実行します。公式サイトがログインなしで使うセッションカタログとスピーカーディレクトリから、公開に必要なフィールドだけを抽出します。差分に加え、公開・除外の件数およびオンデマンド一覧を公式画面と照合します。
2. イベント・製品発表は対応する JSON を編集します。Book of News の本文付き発表見出しと突合し、転載ではなく独自に要約します。地域、ライセンス、予定日などを追記する場合は、公式出典を付けて発表時の状態と区別します。
3. 検証とビルドを行い、PR で出典と差分をレビューします。

Azure Updates の更新は `python tools/import_azure_updates.py` で行います。公開年を 2026 年、タグを `Microsoft Ignite` に限定し、ページ件数と重複を検証します。2026 年のイベント週外にも同じタグの投稿があり、掲載はセッションでの発表を意味しません。公式動画は Microsoft Events の Ignite 2026 プレイリスト等でコードとタイトルを照合し、複数候補や未確認の動画を推測で登録しません。関連製品更新は `data/session-updates.json`、録画で確認した Book of News の関係は各要約に記録します。

日本語概要と公式技術記事は `data/update-editorial.json` に追加します。短縮 URL の場合は転送先が同じ製品・機能の記事かを確認してから、最終 URL を記録してください。

### 日次の情報更新

GitHub Agentic Workflows の [`daily-information-update.md`](.github/workflows/daily-information-update.md) は毎日 00:23 UTC（日本時間 09:23）と手動実行で公式情報を確認し、変更があれば PR を作成します。作成した PR の `Ignite guide` が成功し、main の保護条件を満たすと自動的に squash マージします。既存の更新 PR が未処理の場合は重複作成を避けます。確認日だけの変更では PR を作りません。取得失敗や不明な情報は推測で補わず、Actions の実行ログと PR の報告を確認してください。

初回実行前に、管理者は Actions のリポジトリ secrets に次を設定してください。

- `COPILOT_GITHUB_TOKEN`: Copilot を利用できる個人アカウントの fine-grained PAT（アカウント権限 **Copilot Requests: Read**）。
- `GH_AW_PR_TOKEN`: このリポジトリに限定した fine-grained PAT（リポジトリ権限 **Contents: Read and write**、**Pull requests: Read and write**、**Actions: Read**、**Administration: Read**）。PR の作成・マージ、CI 結果とブランチ保護の確認に使います。PR に対して通常の Actions チェックを起動するため、標準の `GITHUB_TOKEN` とは別に指定します。有効期限前に更新してください。

管理者は **Settings → Branches** の `main` 保護ルールで「Require status checks to pass before merging」と「Require branches to be up to date before merging」を有効にし、GitHub Actions 提供の `build` チェックを必須にしてください。「Do not allow bypassing the above settings」も有効にします。リポジトリで squash merge を許可し、トークンに保護ルールや ruleset のバイパス権限を与えないでください。これらの保護は自動マージに必須です。承認が必須の場合は、未承認の PR の自動マージは失敗し、承認後に手動でマージする必要があります。

Actions タブの **Ignite 2026 情報の日次更新** から main を選択して手動実行できます。自動マージはこの実行で作成した同一リポジトリの PR に限り、データ以外の変更、検証失敗、main や PR の更新、保護不足、30 分以内の CI 未完了などの場合は停止します。保護や承認の未充足、競合、トークン期限切れも Actions ログを確認し、必要に応じて PR を確認・修正してください。再実行時に既存 PR があれば自動マージ対象にしません。マージ後は既存の Pages ワークフローが公開します。AI による更新内容が自動公開されるため、PR と出典を定期的に確認し、誤りは PR の revert で戻してください。

ワークフローを変更するときは [gh-aw CLI](https://github.github.com/gh-aw/setup/quick-start/) v1.2.2 を使い、`gh aw compile daily-information-update --action-mode action --action-tag 53d0749e19424a918acd82b4d140264ce48f2f14` で `.lock.yml` を再生成して両方をコミットします。

### 録画要約を追加する

1. セッション一覧で「オンデマンドあり・内容未確認」を選び、公式ページで対象の開催枠を確認します。別の開催枠や編集版の時刻は混ぜません。
2. 公開録画の字幕を基本とします。イベント版の字幕が取得できない場合は、コード・タイトル・公式チャンネルを照合した YouTube 録画の公開文字起こしを使えます。チャプターや利用可能な場合の [Ask YouTube](https://support.google.com/youtube/answer/14110396) は該当箇所を探す手掛かりにし、AI の回答だけを根拠にしません。
3. 発言内容を独自の日本語で短く要約し、[`data/session-notes/`](data/session-notes) の `{code}.json`（例: `BRK449.json`）に確認日と時刻を追加します。ファイル名と `sessionCode` を一致させます。未確認のセッションに空ファイルは作りません。個別 JSON と HTML はビルド時に生成するので、録画要約の編集はここだけです。タイトルや概要から内容を推測したり、録画や字幕全文をコミットしたりしません。

カタログに字幕リンクがなくても、公式の公開プレーヤー内で字幕を選べることがあります。
`python tools/check_recording_notes.py BRK240 BRK223` は、イベント版を参照した要約について公開カタログとプレーヤーの結び付き、参照した字幕の形式、時刻を確認します。`youtube-transcript` の時刻は公式 YouTube の文字起こしで確認します。字幕は保存せず、文章の意味や提供状況の正しさは別途レビューしてください。

## GitHub Pages の初回公開

リポジトリ管理者が **Settings → Pages → Build and deployment → Source** を **GitHub Actions** に設定します。
検証済みの変更を `main` にマージすると、`Ignite guide` ワークフローが HTML・JSON・`llms.txt` をデプロイします。
設定がマージ後になった場合は、Actions の同ワークフローを `main` で手動実行できます。
公開後、トップページ、`llms.txt`、各一括 JSON と個別セッションの JSON にアクセスして確認してください。

Microsoft の公式プロジェクトではありません。Microsoft や各製品の名称・商標は各権利者に帰属します。リポジトリの MIT ライセンスは、リンク先の資料や商標には適用されません。

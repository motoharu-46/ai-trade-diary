# blog_claude — AIトレード検証日記（自動投稿ブログ）

[money_claude](../money_claude)（kabuステーションAPI + Claude APIによる日本株の
**ペーパートレード＝仮想シミュレーション、実発注なし**）の結果から、毎営業日
17時頃に自動で記事を生成し、GitHub Pagesへ公開するブログです。

- **money_claudeとはコード非結合**: `data/paper_trades.db` を読み取り専用で
  参照するのみで、`money_claude`パッケージはimportしない（本リポジトリは
  publicになる想定のため）。
- **完全自動投稿**: 公開前の人間によるレビューは無し。記事本文はClaude API
  （`messages.parse`構造化出力）で生成し、数値は必ずPython側で確定済みの
  ものだけを渡す（LLMに数字を創作させない）。API失敗時・出力バリデーション
  失敗時は固定テンプレートへ自動フォールバックし、投稿を欠かさない。
- **記録の保存**: `records/YYYY-MM-DD.json` に、統計値・LLMの生レスポンス・
  `used_fallback`フラグを含む構造化記録を残す（HTMLとは独立した監査証跡かつ、
  トップページ/アーカイブ/RSS/サイトマップ再構築の唯一の情報源）。

## セットアップ

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`.env` を編集し、`ANTHROPIC_API_KEY`・`MONEY_CLAUDE_DB_PATH`・
`ACCOUNT_EQUITY_JPY`・`PAPER_STOP_LOSS_PCT`・`PAPER_TAKE_PROFIT_PCT`・
`SITE_BASE_URL`・`OPERATOR_NAME` を設定してください
（`ACCOUNT_EQUITY_JPY`等はmoney_claudeの`.env`と同じ値にしておくと、
運用枠・損益分岐勝率の計算がmoney_claude側のダッシュボードと一致します）。

## 実行方法

```powershell
python -m scripts.generate_daily_post --dry-run   # ローカル生成のみ（git操作なし）
python -m scripts.generate_daily_post              # 生成 + git commit/push
python -m scripts.generate_daily_post --force       # 当日分の記録が既にあっても再生成
```

非営業日（土日・日本の祝日・年末年始）は`generator/trading_calendar.py`の
`is_trading_day`判定により即終了する（money_claude側と同一ロジックを複製、
理由はコード内コメント参照）。同日の記録（`records/YYYY-MM-DD.json`）が既に
存在する場合も、`--force`を付けない限り再生成をスキップする（LLM再呼び出し・
重複コミットを防ぐため）。

## タスクスケジューラへの登録（⚠️ ご自身で実行してください）

`scripts/register_task_scheduler.ps1` を用意していますが、money_claude側の
既存方針と同様に**OSのタスクスケジューラ設定を変更する操作のため、Claudeからは
実行しません**。内容を確認した上で、ご自身の判断でPowerShellから実行してください。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
```

毎日17:00（ローカル時刻）に`scripts\run_daily_post.bat`を起動します。
`MultipleInstances=IgnoreNew`のため、前回の実行が終わっていなければ新しい
実行は開始されません。登録内容は`taskschd.msc`で確認・変更・削除できます。

## GitHub Pages

- 公開元: `main`ブランチの`/docs`フォルダ（リポジトリのSettings → Pages で設定）。
- `docs/.nojekyll`を同梱しJekyllのビルド処理を無効化している（生成済みの
  素のHTMLをそのまま配信するため）。
- プロジェクトページ（`https://<user>.github.io/<repo>/`）はドメイン直下では
  ないため、テンプレート内のリンク/CSSはすべて相対パス。`feed.xml`/
  `sitemap.xml`/canonicalタグにのみ`.env`の`SITE_BASE_URL`で絶対URLを使う。

## ディレクトリ構成

```
generator/       生成ロジック（config/trading_calendar/data_source/charts/
                  article_writer/records/site_builder/publisher）
templates/        Jinja2テンプレート（post/index/archive/disclaimer/privacy/about）
docs/             GitHub Pages公開元（生成物 + 静的CSS/robots.txt/.nojekyll）
records/          日次記録（構造化データ、公開リポジトリにコミットする）
scripts/          エントリポイント・.bat・タスクスケジューラ登録スクリプト
tests/            pytest
```

## 未検証・既知の限定事項

- **SQLite同時読み取り**: `sqlite3.connect(..., mode=ro)` + 簡易リトライ
  （3回）で対応。money_claude側は書き込み即commitのためロック窓は短いが、
  理論上は競合しうる（実運用で問題が出た場合はSQLiteのbackup APIによる
  一時ファイルへのスナップショット方式へ切り替えを検討）。
- **シグナル0件の日と、money_claude側の異常（ログイン失敗等）で取引が
  発生しなかった日を区別できない**: DB上はどちらも「新規行なし」で同じに
  見えるため、両方とも「本日はシグナルなし」の投稿になる。money_claudeの
  ログファイルとの突合は追加の結合を生むため、意図的に対応していない。
- **アフィリエイト**: `templates/post.html`内の`<!-- AFFILIATE_SLOT -->`
  部分にASPの広告タグを差し込む想定（現時点では空枠）。
- **運営者表示名**: `.env`の`OPERATOR_NAME`は仮の値。`about.html`/
  `disclaimer.html`に反映されるため、公開前に実際の表示名へ変更すること。
- 初回ロールアウト時は、`--dry-run`での確認後、タスクスケジューラ登録前に
  一度だけ`--dry-run`なしの本番パイプライン（実際のgit push）を手動実行し、
  無人実行前に通しの動作を確認する運用とした。

# プロジェクトルール（blog_claude）

## レイヤー①: 内容に関する絶対ルール（金融コンテンツのため）

- 本サイトが扱うのはmoney_claudeの**ペーパートレード（帳簿上の仮想シミュレーション、
  実発注なし）**結果である。記事・テンプレート・コミットメッセージのいずれにおいても、
  これを実際の運用成績であるかのように表現しないこと。
- 投資助言と誤解されうる表現（「買うべき」「儲かる」「必ず上がる」等の断定的・
  煽情的な表現）を記事に含めないこと。`generator/article_writer.py`の
  `_SYSTEM_PROMPT`と`_validate()`がこれを防ぐガードレールなので、変更する際は
  このルールを弱めないこと。
- 記事中の数値（損益・勝率・件数など）はPython側（`data_source.DailyStats`）で
  確定した値のみを使用する。Claudeに数値を計算・創作させる実装を追加しないこと。
- Claude API呼び出しが失敗した場合、または出力バリデーションに失敗した場合は、
  必ず`build_fallback_article()`の固定テンプレートへフォールバックし、投稿を
  欠かさないこと（無投稿よりも、簡素でも事実のみの投稿を優先する設計判断）。

## レイヤー②: money_claudeとの関係

- 本リポジトリはpublicになる想定のため、**money_claudeのPythonコードを
  importしない**（`generator/trading_calendar.py`の`is_trading_day`は
  money_claude側の同名関数を意図的に複製したもの）。money_claudeとの
  やり取りは`data/paper_trades.db`への読み取り専用SQLアクセスのみに限定する。
- money_claude側の`is_trading_day`ロジックが変更された場合は、こちらにも
  手動で反映すること（自動追従の仕組みは無い）。

## レイヤー③: 作業フロー制御

- タスクスケジューラ（`scripts/register_task_scheduler.ps1`）はOSレベルの
  設定変更のため、**Claudeからは実行しない**。ユーザー自身が内容を確認の上で
  実行する（money_claudeの既存方針を踏襲）。
- `git push`を伴う本番実行（`--dry-run`無し）は、無人スケジュール実行の前に
  少なくとも一度は人の目で結果を確認してから行うこと。

## レイヤー④: コスト・セキュリティ

- 認証情報（`ANTHROPIC_API_KEY`等）は`.env`からのみ読み込み、コード内に
  ハードコードしないこと。
- `generator/publisher.py`の`git commit`成否判定は、標準出力の文字列比較では
  なく`git diff --cached --quiet`の終了コードで行う方針を維持すること。

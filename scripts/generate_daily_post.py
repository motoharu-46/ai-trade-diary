"""日次記事の生成〜公開を行うエントリポイント。

実行方法:
    python -m scripts.generate_daily_post [--dry-run] [--force] [--date YYYY-MM-DD]

--dry-run: docs/・records/をローカルに生成するが、git commit/pushは行わない。
--force:   その日のrecords/*.jsonが既に存在していても再生成する
           （通常は同日の重複実行によるLLM再呼び出し・重複コミットを防ぐため
           自動的にスキップする）。
--date:    対象日を指定する（省略時は本日、JST）。タスクスケジューラの登録が
           遅れた等の理由で投稿が漏れた過去の営業日をバックフィルする用途。
           `open_positions`（保有中件数）は「実行時点で現在オープン中の
           ポジション」であり、厳密には「指定日の引け時点のオープン
           ポジション」ではない点に注意（その日以降に新たな
           オープン/クローズが発生していれば実行時点の状態とずれる）。

`money_claude/core/trading_calendar.py`の`is_trading_day`と同じロジック
（`generator/trading_calendar.py`に複製）で非営業日は即終了する。money_claude
の`.bat`/タスクスケジューラの運用パターンを踏襲し、標準出力へのログは
呼び出し元の`.bat`が`logs\\*.log`へリダイレクトする想定（Python側ではファイル
へは直接書き込まない）。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from generator.article_writer import generate_article
from generator.config import get_settings
from generator.data_source import build_daily_stats
from generator.publisher import PublishError, publish
from generator.records import build_record, load_all_records, record_exists, write_record
from generator.site_builder import rebuild_site
from generator.trading_calendar import is_trading_day

JST = timezone(timedelta(hours=9))

# Windowsのコンソール/リダイレクト先が既定でcp932等になり、ログの日本語が
# 文字化けする（あるいはログファイルとしてUTF-8以外で書かれてしまう）のを
# 避けるため、明示的にUTF-8へ統一する。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_daily_post")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="git commit/pushを行わずローカル生成のみ行う"
    )
    parser.add_argument(
        "--force", action="store_true", help="既存の当日記録があっても再生成する"
    )
    parser.add_argument(
        "--date", type=str, default=None, help="対象日をYYYY-MM-DD形式で指定する（過去日のバックフィル用、省略時は本日）"
    )
    args = parser.parse_args()

    settings = get_settings()
    target_date = date_cls.fromisoformat(args.date) if args.date else datetime.now(JST).date()

    if not is_trading_day(target_date):
        logger.info("%s は非営業日のため投稿をスキップします。", target_date)
        return 0

    if record_exists(target_date) and not args.force:
        logger.info(
            "%s の記録は既に存在します（--forceで再生成できます）。スキップします。",
            target_date,
        )
        return 0

    try:
        stats = build_daily_stats(
            db_path=settings.money_claude_db_path,
            target_date=target_date,
            account_equity_jpy=settings.account_equity_jpy,
            stop_loss_pct=settings.paper_stop_loss_pct,
            take_profit_pct=settings.paper_take_profit_pct,
        )
    except Exception:
        logger.exception("money_claudeのDB読み取りに失敗しました。")
        return 1

    article_result = generate_article(settings, stats)
    if article_result.used_fallback:
        logger.warning(
            "記事生成はフォールバックテンプレートを使用しました: %s", article_result.error
        )

    record = build_record(target_date, stats, article_result)
    write_record(record)
    logger.info("記録を保存しました: records/%s.json", record.date)

    all_records = load_all_records()
    rebuild_site(all_records, settings)
    logger.info("サイトを再生成しました（docs/）。")

    if args.dry_run:
        logger.info("--dry-run のため git への反映は行いません。")
        return 0

    try:
        published = publish(commit_message=f"Daily report {record.date}")
    except PublishError:
        logger.exception("公開（git push）に失敗しました。")
        return 1

    if published:
        logger.info("公開しました: %s", record.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())

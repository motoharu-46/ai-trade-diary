"""日次記録（records/YYYY-MM-DD.json）の読み書き。

「記録を残しておきたい」という要望に対応する構造化データの保存先であり、
同時にトップページ/アーカイブ/RSS/サイトマップを再構築するための唯一の
情報源（source of truth）としても使う（HTMLをパースし直す必要をなくすため）。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from .article_writer import ArticleResult
from .config import REPO_ROOT
from .data_source import DailyStats

RECORDS_DIR = REPO_ROOT / "records"


class TradeRecord(BaseModel):
    symbol: str
    symbol_name: str | None
    entry_time_jst: str
    entry_price: float
    quantity: int
    claude_reason: str
    exit_time_jst: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    realized_pnl_jpy: float | None = None
    realized_pnl_pct: float | None = None


class StatsSummary(BaseModel):
    closed_today_count: int
    today_realized_pnl_jpy: float
    today_win_rate_pct: float | None
    open_positions_count: int
    cumulative_closed_count: int
    cumulative_realized_pnl_jpy: float
    cumulative_win_rate_pct: float | None
    current_equity_jpy: float
    base_equity_jpy: float
    breakeven_win_rate_pct: float


class DailyRecord(BaseModel):
    date: str  # YYYY-MM-DD
    title: str
    meta_description: str
    lead: str
    commentary: str
    used_fallback: bool
    article_error: str | None = None
    raw_response_text: str | None = None
    stats: StatsSummary
    closed_today: list[TradeRecord]
    opened_today_still_open: list[TradeRecord]
    generated_at_jst: str


def build_record(target_date: date, stats: DailyStats, article_result: ArticleResult) -> DailyRecord:
    from datetime import timezone, timedelta

    jst = timezone(timedelta(hours=9))
    return DailyRecord(
        date=target_date.isoformat(),
        title=article_result.article.title,
        meta_description=article_result.article.meta_description,
        lead=article_result.article.lead,
        commentary=article_result.article.commentary,
        used_fallback=article_result.used_fallback,
        article_error=article_result.error,
        raw_response_text=article_result.raw_response_text,
        stats=StatsSummary(
            closed_today_count=len(stats.closed_today),
            today_realized_pnl_jpy=stats.today_realized_pnl_jpy,
            today_win_rate_pct=stats.today_win_rate_pct,
            open_positions_count=len(stats.open_positions),
            cumulative_closed_count=len(stats.all_time_closed),
            cumulative_realized_pnl_jpy=stats.cumulative_realized_pnl_jpy,
            cumulative_win_rate_pct=stats.cumulative_win_rate_pct,
            current_equity_jpy=stats.current_equity_jpy,
            base_equity_jpy=stats.base_equity_jpy,
            breakeven_win_rate_pct=stats.breakeven_win_rate_pct,
        ),
        closed_today=[
            TradeRecord(
                symbol=t.symbol,
                symbol_name=t.symbol_name,
                entry_time_jst=t.entry_time.isoformat(),
                entry_price=t.entry_price,
                quantity=t.quantity,
                claude_reason=t.claude_reason,
                exit_time_jst=t.exit_time.isoformat(),
                exit_price=t.exit_price,
                exit_reason=t.exit_reason,
                realized_pnl_jpy=t.realized_pnl_jpy,
                realized_pnl_pct=t.realized_pnl_pct,
            )
            for t in stats.closed_today
        ],
        opened_today_still_open=[
            TradeRecord(
                symbol=p.symbol,
                symbol_name=p.symbol_name,
                entry_time_jst=p.entry_time.isoformat(),
                entry_price=p.entry_price,
                quantity=p.quantity,
                claude_reason=p.claude_reason,
            )
            for p in stats.opened_today_still_open
        ],
        generated_at_jst=datetime.now(jst).isoformat(),
    )


def record_path(target_date: date) -> Path:
    return RECORDS_DIR / f"{target_date.isoformat()}.json"


def record_exists(target_date: date) -> bool:
    return record_path(target_date).exists()


def write_record(record: DailyRecord) -> Path:
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    path = record_path(date.fromisoformat(record.date))
    path.write_text(record.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")
    return path


def load_all_records() -> list[DailyRecord]:
    """全ての日次記録を日付昇順で読み込む。"""
    if not RECORDS_DIR.exists():
        return []
    records = []
    for path in sorted(RECORDS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        records.append(DailyRecord.model_validate(data))
    records.sort(key=lambda r: r.date)
    return records

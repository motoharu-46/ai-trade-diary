"""money_claudeのペーパートレードDB（data/paper_trades.db）を読み取り専用で
集計する。

money_claudeとはコードを一切importしない完全分離方針のため、SQLクエリは
このモジュール内で完結させる（money_claude/core/paper_trading_dashboard.py
と同種の集計だが、あちらの非公開関数は呼び出さずここで独立に実装している）。

`entry_time`/`exit_time`はmoney_claude側でUTC（`datetime.now(timezone.utc)`）
として保存されているため、「本日」の判定は必ずJSTへ変換してから行う。UTC文字列
の日付部分を直接比較すると、JST 0:00〜8:59に発生したイベントがUTC上は前日
扱いになり日付がずれるバグになるため注意。
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 0.5


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    symbol_name: str | None
    entry_time: datetime  # JST
    entry_price: float
    quantity: int
    claude_reason: str
    exit_time: datetime  # JST
    exit_price: float
    exit_reason: str
    realized_pnl_jpy: float
    realized_pnl_pct: float


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    symbol_name: str | None
    entry_time: datetime  # JST
    entry_price: float
    quantity: int
    claude_reason: str


@dataclass(frozen=True)
class DailyStats:
    target_date: date
    closed_today: list[ClosedTrade]
    opened_today_still_open: list[OpenPosition]
    open_positions: list[OpenPosition]
    all_time_closed: list[ClosedTrade]  # 時系列昇順（累積損益推移チャート用）

    today_realized_pnl_jpy: float
    today_win_rate_pct: float | None
    cumulative_realized_pnl_jpy: float
    cumulative_win_rate_pct: float | None
    current_equity_jpy: float
    base_equity_jpy: float
    breakeven_win_rate_pct: float

    @property
    def had_any_activity_today(self) -> bool:
        return bool(self.closed_today or self.opened_today_still_open)


def _parse_jst(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(JST)


def _fetch_rows(db_path: str) -> tuple[list[tuple], list[tuple]]:
    """DBロック（"database is locked"）に対して簡易リトライしつつ全行を読む。

    money_claudeは書き込み即commitのためロック窓は短いが、念のため
    3回・バックオフ付きで再試行する。読み取り専用モード（mode=ro）で
    接続するため、このプロセスがDBを書き換えることは構造的にない。
    """
    last_error: sqlite3.OperationalError | None = None
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    for attempt in range(_MAX_RETRIES):
        try:
            conn = sqlite3.connect(uri, uri=True)
            try:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
                symbol_name_expr = "symbol_name" if "symbol_name" in columns else "NULL"

                open_rows = conn.execute(
                    f"SELECT symbol, {symbol_name_expr} AS symbol_name, entry_time, "
                    "entry_price, quantity, claude_reason "
                    "FROM trades WHERE exit_time IS NULL"
                ).fetchall()
                closed_rows = conn.execute(
                    f"SELECT symbol, {symbol_name_expr} AS symbol_name, entry_time, "
                    "entry_price, quantity, claude_reason, exit_time, exit_price, "
                    "exit_reason, realized_pnl_jpy, realized_pnl_pct "
                    "FROM trades WHERE exit_time IS NOT NULL ORDER BY exit_time ASC"
                ).fetchall()
            finally:
                conn.close()
            return open_rows, closed_rows
        except sqlite3.OperationalError as exc:
            last_error = exc
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
    assert last_error is not None
    raise last_error


def breakeven_win_rate_pct(stop_loss_pct: float, take_profit_pct: float) -> float:
    """損切/利確設定から、期待値0円となる損益分岐勝率(%)を算出する。

    money_claude/core/paper_trading_dashboard.pyと同じ式
    （win_rate = stop_loss / (stop_loss + take_profit)）。
    """
    return stop_loss_pct / (stop_loss_pct + take_profit_pct) * 100


def build_daily_stats(
    db_path: str,
    target_date: date,
    account_equity_jpy: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> DailyStats:
    """指定日(JST)のペーパートレード統計を算出する。DB接続不可時は
    sqlite3.Errorをそのまま送出する（エラー時のフォールバックは呼び出し元の
    責務とする）。
    """
    open_rows, closed_rows = _fetch_rows(db_path)

    all_time_closed = [
        ClosedTrade(
            symbol=symbol,
            symbol_name=symbol_name,
            entry_time=_parse_jst(entry_time),
            entry_price=entry_price,
            quantity=quantity,
            claude_reason=claude_reason,
            exit_time=_parse_jst(exit_time),
            exit_price=exit_price,
            exit_reason=exit_reason,
            realized_pnl_jpy=realized_pnl_jpy,
            realized_pnl_pct=realized_pnl_pct,
        )
        for (
            symbol,
            symbol_name,
            entry_time,
            entry_price,
            quantity,
            claude_reason,
            exit_time,
            exit_price,
            exit_reason,
            realized_pnl_jpy,
            realized_pnl_pct,
        ) in closed_rows
    ]

    open_positions = [
        OpenPosition(
            symbol=symbol,
            symbol_name=symbol_name,
            entry_time=_parse_jst(entry_time),
            entry_price=entry_price,
            quantity=quantity,
            claude_reason=claude_reason,
        )
        for symbol, symbol_name, entry_time, entry_price, quantity, claude_reason in open_rows
    ]

    closed_today = [t for t in all_time_closed if t.exit_time.date() == target_date]
    opened_today_still_open = [
        p for p in open_positions if p.entry_time.date() == target_date
    ]

    today_pnl = sum(t.realized_pnl_jpy for t in closed_today)
    today_wins = [t for t in closed_today if t.realized_pnl_jpy > 0]
    today_win_rate = (
        len(today_wins) / len(closed_today) * 100 if closed_today else None
    )

    cumulative_pnl = sum(t.realized_pnl_jpy for t in all_time_closed)
    all_wins = [t for t in all_time_closed if t.realized_pnl_jpy > 0]
    cumulative_win_rate = (
        len(all_wins) / len(all_time_closed) * 100 if all_time_closed else None
    )

    return DailyStats(
        target_date=target_date,
        closed_today=closed_today,
        opened_today_still_open=opened_today_still_open,
        open_positions=open_positions,
        all_time_closed=all_time_closed,
        today_realized_pnl_jpy=today_pnl,
        today_win_rate_pct=today_win_rate,
        cumulative_realized_pnl_jpy=cumulative_pnl,
        cumulative_win_rate_pct=cumulative_win_rate,
        current_equity_jpy=account_equity_jpy + cumulative_pnl,
        base_equity_jpy=account_equity_jpy,
        breakeven_win_rate_pct=breakeven_win_rate_pct(stop_loss_pct, take_profit_pct),
    )

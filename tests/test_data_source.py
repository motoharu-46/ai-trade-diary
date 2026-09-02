import sqlite3
from datetime import date
from pathlib import Path

import pytest

from generator.data_source import build_daily_stats

_CREATE_TABLE_SQL = """
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    symbol_name TEXT,
    entry_time TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    claude_reason TEXT NOT NULL,
    exit_time TEXT,
    exit_price REAL,
    exit_reason TEXT,
    realized_pnl_jpy REAL,
    realized_pnl_pct REAL
)
"""


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "paper_trades.db"
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_TABLE_SQL)

    # This row's exit_time is 23:30 UTC on 2026-09-02, which is 08:30 JST on
    # 2026-09-03 — the classic UTC/JST date-boundary bug this test guards
    # against (must be attributed to 2026-09-03, not 2026-09-02).
    conn.execute(
        "INSERT INTO trades (symbol, symbol_name, entry_time, entry_price, "
        "quantity, claude_reason, exit_time, exit_price, exit_reason, "
        "realized_pnl_jpy, realized_pnl_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "1234",
            "テスト株式",
            "2026-09-02T22:00:00+00:00",
            1000.0,
            100,
            "出来高急増を検知",
            "2026-09-02T23:30:00+00:00",
            1050.0,
            "TAKE_PROFIT",
            5000.0,
            5.0,
        ),
    )
    # A currently-open position (no exit_time).
    conn.execute(
        "INSERT INTO trades (symbol, symbol_name, entry_time, entry_price, "
        "quantity, claude_reason) VALUES (?,?,?,?,?,?)",
        ("5678", None, "2026-09-03T01:00:00+00:00", 500.0, 200, "株価急騰を検知"),
    )
    conn.commit()
    conn.close()
    return str(path)


def test_jst_boundary_attributes_trade_to_correct_day(db_path: str):
    stats_sep3 = build_daily_stats(
        db_path, date(2026, 9, 3), account_equity_jpy=1_000_000,
        stop_loss_pct=2.0, take_profit_pct=5.0,
    )
    assert len(stats_sep3.closed_today) == 1
    assert stats_sep3.closed_today[0].symbol == "1234"

    stats_sep2 = build_daily_stats(
        db_path, date(2026, 9, 2), account_equity_jpy=1_000_000,
        stop_loss_pct=2.0, take_profit_pct=5.0,
    )
    assert len(stats_sep2.closed_today) == 0


def test_open_position_counted_and_opened_today(db_path: str):
    stats = build_daily_stats(
        db_path, date(2026, 9, 3), account_equity_jpy=1_000_000,
        stop_loss_pct=2.0, take_profit_pct=5.0,
    )
    assert len(stats.open_positions) == 1
    assert stats.open_positions[0].symbol == "5678"
    assert len(stats.opened_today_still_open) == 1


def test_stats_math(db_path: str):
    stats = build_daily_stats(
        db_path, date(2026, 9, 3), account_equity_jpy=1_000_000,
        stop_loss_pct=2.0, take_profit_pct=5.0,
    )
    assert stats.today_realized_pnl_jpy == 5000.0
    assert stats.today_win_rate_pct == 100.0
    assert stats.cumulative_realized_pnl_jpy == 5000.0
    assert stats.current_equity_jpy == 1_005_000.0
    assert stats.breakeven_win_rate_pct == pytest.approx(2.0 / 7.0 * 100)


def test_had_any_activity_today_false_on_quiet_day(db_path: str):
    stats = build_daily_stats(
        db_path, date(2026, 9, 5), account_equity_jpy=1_000_000,
        stop_loss_pct=2.0, take_profit_pct=5.0,
    )
    assert stats.had_any_activity_today is False

from datetime import datetime, timezone

from generator.charts import build_equity_curve_svg, build_symbol_bar_chart_svg
from generator.data_source import ClosedTrade


def _trade(symbol: str, pnl: float, exit_hour: int = 10) -> ClosedTrade:
    return ClosedTrade(
        symbol=symbol,
        symbol_name=None,
        entry_time=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
        entry_price=1000.0,
        quantity=100,
        claude_reason="test",
        exit_time=datetime(2026, 9, 3, exit_hour, 0, tzinfo=timezone.utc),
        exit_price=1000.0 + pnl / 100,
        exit_reason="TAKE_PROFIT" if pnl >= 0 else "STOP_LOSS",
        realized_pnl_jpy=pnl,
        realized_pnl_pct=pnl / 1000.0,
    )


def test_equity_curve_svg_empty():
    result = build_equity_curve_svg([], base_equity_jpy=1_000_000)
    assert "svg" not in result
    assert "データがありません" in result


def test_equity_curve_svg_with_data():
    trades = [_trade("1234", 5000), _trade("5678", -2000, exit_hour=11)]
    result = build_equity_curve_svg(trades, base_equity_jpy=1_000_000)
    assert result.startswith("<svg")
    assert "</svg>" in result


def test_symbol_bar_chart_svg_with_data():
    trades = [_trade("1234", 5000), _trade("1234", -1000, exit_hour=11)]
    result = build_symbol_bar_chart_svg(trades)
    assert result.startswith("<svg")
    assert "1234" in result


def test_symbol_bar_chart_svg_empty():
    result = build_symbol_bar_chart_svg([])
    assert "データがありません" in result

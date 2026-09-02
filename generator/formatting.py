"""表示用の整形ヘルパー。article_writer（Claudeへのプロンプト文言）と
site_builder（HTML描画）の両方から使う共通ロジック。
"""

from __future__ import annotations

from .data_source import ClosedTrade, OpenPosition


def display_symbol(symbol: str, symbol_name: str | None) -> str:
    """銘柄名が分かっていれば「会社名 (コード)」、無ければコードのみ。"""
    return f"{symbol_name} ({symbol})" if symbol_name else symbol


def format_exit_reason(reason: str, stop_loss_pct: float, take_profit_pct: float) -> str:
    """決済理由コードを、実際に使われた設定値を添えた日本語表記に変換する。"""
    if reason == "STOP_LOSS":
        return f"損切（設定: -{stop_loss_pct:.1f}%到達）"
    if reason == "TAKE_PROFIT":
        return f"利確（設定: +{take_profit_pct:.1f}%到達）"
    return reason


_WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


def format_date_ja(value) -> str:
    return f"{value.year}年{value.month}月{value.day}日（{_WEEKDAY_JA[value.weekday()]}）"


def format_trade_line(
    trade: ClosedTrade, stop_loss_pct: float, take_profit_pct: float
) -> str:
    reason = format_exit_reason(trade.exit_reason, stop_loss_pct, take_profit_pct)
    return (
        f"{display_symbol(trade.symbol, trade.symbol_name)}: "
        f"{trade.entry_time.strftime('%H:%M')}に{trade.entry_price:,.1f}円でエントリー、"
        f"{trade.exit_time.strftime('%H:%M')}に{trade.exit_price:,.1f}円で{reason}、"
        f"実現損益{trade.realized_pnl_jpy:+,.0f}円（{trade.realized_pnl_pct:+.2f}%）。"
        f"エントリー判断理由: {trade.claude_reason}"
    )


def format_open_position_line(position: OpenPosition) -> str:
    return (
        f"{display_symbol(position.symbol, position.symbol_name)}: "
        f"{position.entry_time.strftime('%Y-%m-%d %H:%M')}に{position.entry_price:,.1f}円で"
        f"エントリーし保有継続中。エントリー判断理由: {position.claude_reason}"
    )

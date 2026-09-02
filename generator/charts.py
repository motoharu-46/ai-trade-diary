"""依存ライブラリ無しのインラインSVGチャート生成。

money_claude/core/paper_trading_dashboard.pyのSVG生成ロジックを、こちらの
`generator.data_source.ClosedTrade`データクラス向けに移植したもの
（money_claudeはコードをimportしない完全分離方針のため、コピー＋型を
合わせる形での移植としている）。
"""

from __future__ import annotations

import html

from .data_source import ClosedTrade


def _esc(value: object) -> str:
    return html.escape(str(value))


def build_equity_curve_svg(
    all_time_closed_asc: list[ClosedTrade], base_equity_jpy: float
) -> str:
    """決済順（古い順）の運用枠（当初資金+累計実現損益）を折れ線で描く。

    `all_time_closed_asc`は決済日時の昇順（時系列順）であること。
    """
    if not all_time_closed_asc:
        return '<p class="empty">データがありません</p>'

    cumulative = 0.0
    points: list[float] = []
    date_labels: list[str] = []
    for trade in all_time_closed_asc:
        cumulative += trade.realized_pnl_jpy
        points.append(base_equity_jpy + cumulative)
        date_labels.append(trade.exit_time.strftime("%m/%d"))

    width, height = 600, 200
    padding_top, padding_bottom, padding_x = 20, 36, 30
    plot_height = height - padding_top - padding_bottom
    n = len(points)
    min_v = min(base_equity_jpy, min(points))
    max_v = max(base_equity_jpy, max(points))
    span = (max_v - min_v) or 1.0

    def x_for(i: int) -> float:
        return padding_x + (i / max(n - 1, 1)) * (width - 2 * padding_x)

    def y_for(v: float) -> float:
        return padding_top + plot_height - ((v - min_v) / span) * plot_height

    coords = " ".join(f"{x_for(i):.1f},{y_for(v):.1f}" for i, v in enumerate(points))
    base_y = y_for(base_equity_jpy)
    line_color = "#0a7d2c" if points[-1] >= base_equity_jpy else "#c0392b"

    axis_y = height - padding_bottom
    tick_count = min(n, 6)
    tick_indices = sorted(
        {round(i * (n - 1) / max(tick_count - 1, 1)) for i in range(tick_count)}
    )
    ticks = "".join(
        f'<line x1="{x_for(i):.1f}" y1="{axis_y}" x2="{x_for(i):.1f}" y2="{axis_y + 4}" stroke="#999" />'
        f'<text x="{x_for(i):.1f}" y="{axis_y + 16}" font-size="10" text-anchor="middle" fill="#666">'
        f"{_esc(date_labels[i])}</text>"
        for i in tick_indices
    )

    return f"""<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" class="chart" role="img" aria-label="累積損益推移">
  <line x1="{padding_x}" y1="{base_y:.1f}" x2="{width - padding_x}" y2="{base_y:.1f}" stroke="#ccc" stroke-dasharray="4" />
  <text x="{width - padding_x}" y="{base_y - 4:.1f}" font-size="10" text-anchor="end" fill="#888">元本 {base_equity_jpy:,.0f}円</text>
  <line x1="{padding_x}" y1="{axis_y}" x2="{width - padding_x}" y2="{axis_y}" stroke="#ccc" />
  <polyline points="{coords}" fill="none" stroke="{line_color}" stroke-width="2" />
  {ticks}
</svg>"""


def build_symbol_bar_chart_svg(trades: list[ClosedTrade]) -> str:
    """銘柄別の合計実現損益を横棒グラフで描く。"""
    by_symbol: dict[str, float] = {}
    for trade in trades:
        by_symbol[trade.symbol] = by_symbol.get(trade.symbol, 0.0) + trade.realized_pnl_jpy

    if not by_symbol:
        return '<p class="empty">データがありません</p>'

    items = sorted(by_symbol.items(), key=lambda pair: -pair[1])
    width = 600
    bar_height, gap = 24, 8
    height = len(items) * (bar_height + gap) + gap
    max_abs = max(abs(v) for _, v in items) or 1.0
    mid_x = width / 2
    half_track = width / 2 - 90

    bars = []
    for i, (symbol, pnl) in enumerate(items):
        y = gap + i * (bar_height + gap)
        bar_width = abs(pnl) / max_abs * half_track
        color = "#0a7d2c" if pnl >= 0 else "#c0392b"
        bar_x = mid_x if pnl >= 0 else mid_x - bar_width
        label_x = mid_x + 6 if pnl >= 0 else mid_x - 6
        anchor = "start" if pnl >= 0 else "end"
        bars.append(
            f'<rect x="{bar_x:.1f}" y="{y}" width="{bar_width:.1f}" '
            f'height="{bar_height}" fill="{color}" />'
            f'<text x="{label_x:.1f}" y="{y + bar_height / 2 + 4:.1f}" '
            f'font-size="11" text-anchor="{anchor}" fill="#222">'
            f"{_esc(symbol)} {pnl:,.0f}円</text>"
        )

    return f"""<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" class="chart" role="img" aria-label="銘柄別実現損益">
  <line x1="{mid_x}" y1="0" x2="{mid_x}" y2="{height}" stroke="#ccc" />
  {"".join(bars)}
</svg>"""

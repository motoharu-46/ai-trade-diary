"""Jinja2でdocs/以下の静的HTML（投稿ページ・トップページ・アーカイブ・
RSS・サイトマップ）を再生成する。

`records/`配下の全日次記録（`generator.records.load_all_records`）を唯一の
情報源とし、HTMLを読み返す必要がないようにしている。
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import charts
from .config import REPO_ROOT, Settings
from .data_source import DailyStats
from .formatting import format_date_ja
from .records import DailyRecord

DOCS_DIR = REPO_ROOT / "docs"
POSTS_DIR = DOCS_DIR / "posts"
TEMPLATES_DIR = REPO_ROOT / "templates"

SITE_DESCRIPTION = (
    "kabuステーションAPIとClaude APIを組み合わせた自動売買システムの"
    "ペーパートレード（仮想シミュレーション）検証記録を毎営業日更新しています。"
)


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _base_context(settings: Settings, asset_prefix: str) -> dict:
    return {
        "site_title": settings.site_title,
        "site_description": SITE_DESCRIPTION,
        "site_base_url": settings.site_base_url,
        "operator_name": settings.operator_name,
        "current_year": datetime.now(timezone.utc).year,
        "asset_prefix": asset_prefix,
    }


def render_post(
    record: DailyRecord,
    stats: DailyStats,
    settings: Settings,
    all_records: list[DailyRecord],
) -> None:
    env = _env()
    template = env.get_template("post.html")

    sorted_records = sorted(all_records, key=lambda r: r.date)
    dates = [r.date for r in sorted_records]
    idx = dates.index(record.date)
    prev_post = sorted_records[idx - 1] if idx > 0 else None
    next_post = sorted_records[idx + 1] if idx < len(sorted_records) - 1 else None

    context = _base_context(settings, asset_prefix="../")
    context.update(
        record=record,
        date_ja=format_date_ja(stats.target_date),
        equity_curve_svg=charts.build_equity_curve_svg(
            stats.all_time_closed, stats.base_equity_jpy
        ),
        symbol_bar_svg=charts.build_symbol_bar_chart_svg(stats.closed_today),
        prev_post=prev_post,
        next_post=next_post,
    )

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = POSTS_DIR / f"{record.date}.html"
    output_path.write_text(template.render(**context), encoding="utf-8")


def render_index(all_records: list[DailyRecord], settings: Settings, recent_count: int = 20) -> None:
    env = _env()
    template = env.get_template("index.html")

    sorted_desc = sorted(all_records, key=lambda r: r.date, reverse=True)
    latest = sorted_desc[0] if sorted_desc else None

    context = _base_context(settings, asset_prefix="")
    context.update(posts=sorted_desc[:recent_count], latest=latest)

    (DOCS_DIR / "index.html").write_text(template.render(**context), encoding="utf-8")


def render_archive(all_records: list[DailyRecord], settings: Settings) -> None:
    env = _env()
    template = env.get_template("archive.html")

    sorted_desc = sorted(all_records, key=lambda r: r.date, reverse=True)
    months: dict[str, list[DailyRecord]] = {}
    for record in sorted_desc:
        year, month, _day = record.date.split("-")
        label = f"{year}年{int(month)}月"
        months.setdefault(label, []).append(record)

    context = _base_context(settings, asset_prefix="")
    context.update(months=list(months.items()))

    (DOCS_DIR / "archive.html").write_text(template.render(**context), encoding="utf-8")


def render_static_pages(settings: Settings) -> None:
    env = _env()
    for name in ("disclaimer.html", "privacy.html", "about.html"):
        context = _base_context(settings, asset_prefix="")
        (DOCS_DIR / name).write_text(
            env.get_template(name).render(**context), encoding="utf-8"
        )


def render_feed(all_records: list[DailyRecord], settings: Settings, item_count: int = 20) -> None:
    sorted_desc = sorted(all_records, key=lambda r: r.date, reverse=True)[:item_count]
    base_url = settings.site_base_url.rstrip("/")

    items = []
    for record in sorted_desc:
        post_url = f"{base_url}/posts/{record.date}.html"
        pub_date = datetime.fromisoformat(record.generated_at_jst).strftime(
            "%a, %d %b %Y %H:%M:%S %z"
        )
        items.append(
            "<item>"
            f"<title>{html.escape(record.title)}</title>"
            f"<link>{html.escape(post_url)}</link>"
            f"<guid>{html.escape(post_url)}</guid>"
            f"<pubDate>{pub_date}</pubDate>"
            f"<description>{html.escape(record.meta_description)}</description>"
            "</item>"
        )

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>{html.escape(settings.site_title)}</title>
<link>{html.escape(settings.site_base_url)}</link>
<description>{html.escape(SITE_DESCRIPTION)}</description>
<language>ja</language>
{''.join(items)}
</channel></rss>
"""
    (DOCS_DIR / "feed.xml").write_text(feed, encoding="utf-8")


def render_sitemap(all_records: list[DailyRecord], settings: Settings) -> None:
    base_url = settings.site_base_url.rstrip("/")
    static_urls = [
        f"{base_url}/",
        f"{base_url}/archive.html",
        f"{base_url}/about.html",
        f"{base_url}/disclaimer.html",
        f"{base_url}/privacy.html",
    ]
    post_urls = [f"{base_url}/posts/{record.date}.html" for record in all_records]

    urls = "".join(f"<url><loc>{html.escape(u)}</loc></url>" for u in static_urls + post_urls)
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )
    (DOCS_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")


def rebuild_site(all_records: list[DailyRecord], settings: Settings) -> None:
    """投稿一覧に依存するページ群（トップ/アーカイブ/RSS/サイトマップ/静的ページ）を
    まとめて再生成する。個別の投稿ページ（posts/*.html）は`render_post`で別途生成する。
    """
    render_index(all_records, settings)
    render_archive(all_records, settings)
    render_static_pages(settings)
    render_feed(all_records, settings)
    render_sitemap(all_records, settings)

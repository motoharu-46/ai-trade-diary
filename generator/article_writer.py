"""Claude APIで日次記事の文章部分を生成する。

money_claude/core/claude_analyzer.pyと同じ`messages.parse(output_format=...)`
（構造化出力）パターンを踏襲する。ただし本用途は一言のBUY/SKIP判定ではなく
長文の記事執筆のため、スキーマは意図的に浅く（title/meta_description/lead/
commentaryの4フィールド）し、`commentary`は「\n\n」区切りの複数段落を許す
1つの文字列として扱う（段落ごとに配列化すると、モデルが長文プローズを
書きにくくなる傾向を避けるため）。

**数値はすべてPython側（data_source.DailyStats）で確定済みのものだけを
プロンプトに渡し、Claudeに数字を創作させない。** これによって金融数値の
ハルシネーションリスクを入力側で断つ。

失敗時（API例外・タイムアウト・出力バリデーション失敗のいずれか）は必ず
`build_fallback_article()`による固定テンプレートにフォールバックし、
記事が生成されないままスケジュールをスキップすることは無い。
"""

from __future__ import annotations

import logging

import anthropic
from pydantic import BaseModel, Field

from .config import Settings
from .data_source import DailyStats
from .formatting import format_date_ja, format_open_position_line, format_trade_line

logger = logging.getLogger(__name__)

_MAX_TOKENS = 4096
_MIN_COMMENTARY_LENGTH = 60
_MAX_COMMENTARY_LENGTH = 4000
_FORBIDDEN_SNIPPETS = ("{{", "}}", "{%", "%}", "```")

_SYSTEM_PROMPT = """\
あなたは日本株の自動売買システム検証ブログの執筆者です。以下のルールを厳守して\
日本語の記事を書いてください。

- これはkabuステーションAPIとClaude APIを使ったペーパートレード（帳簿上の仮想\
シミュレーション、実際の発注は一切行っていない）の結果です。本文中で必ず\
「仮想シミュレーションである」「実際の資金は投じていない」ことが伝わる表現を\
1箇所以上含めてください。
- これは投資助言ではありません。「買うべき」「儲かる」「必ず上がる」のような\
断定的・煽情的な表現、特定銘柄の売買を推奨する表現は禁止です。あくまで\
システムの検証ログとして、何が起きたかを客観的に記述してください。
- 数値（損益・勝率・件数など）は、ユーザーメッセージで与えられた値のみを\
使用してください。自分で数値を計算したり、与えられていない数値を書いては\
いけません。
- 文体は「です・ます調」、落ち着いた解説トーン。煽り見出しは避けてください。
- titleには日付を含め、SEOを意識した具体的な見出しにしてください（例:\
「【システム検証ログ】2026年9月3日の自動売買結果まとめ」のような形式）。
- meta_descriptionは120文字程度で記事内容を要約してください。
- leadは記事冒頭の導入文（2〜3文）です。
- commentaryは記事の本文解説です。与えられたトレード内容（エントリー理由・\
決済理由・損益）に触れながら、読み物として自然な複数段落の文章にしてください。\
段落の区切りは空行（\\n\\n）にしてください。箇条書きの多用は避け、文章として\
書いてください。300〜800文字程度を目安にしてください。
"""


class DailyArticle(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    meta_description: str = Field(min_length=1, max_length=300)
    lead: str = Field(min_length=1, max_length=500)
    commentary: str = Field(min_length=1, max_length=_MAX_COMMENTARY_LENGTH)


class ArticleResult(BaseModel):
    article: DailyArticle
    used_fallback: bool
    raw_response_text: str | None = None
    error: str | None = None


def _build_user_prompt(stats: DailyStats, settings: Settings) -> str:
    date_ja = format_date_ja(stats.target_date)

    lines: list[str] = [f"対象日: {date_ja}", ""]
    lines.append("【本日の統計（この数値のみを使用すること）】")
    lines.append(f"本日の決済件数: {len(stats.closed_today)}件")
    lines.append(f"本日の実現損益: {stats.today_realized_pnl_jpy:+,.0f}円")
    if stats.today_win_rate_pct is not None:
        lines.append(f"本日の勝率: {stats.today_win_rate_pct:.1f}%")
    lines.append(f"保有中のポジション数: {len(stats.open_positions)}件")
    lines.append(f"累計決済件数（全期間）: {len(stats.all_time_closed)}件")
    lines.append(f"累計実現損益（全期間）: {stats.cumulative_realized_pnl_jpy:+,.0f}円")
    if stats.cumulative_win_rate_pct is not None:
        lines.append(f"累計勝率（全期間）: {stats.cumulative_win_rate_pct:.1f}%")
    lines.append(f"現在の運用枠: {stats.current_equity_jpy:,.0f}円（当初{stats.base_equity_jpy:,.0f}円）")
    lines.append("")

    if stats.closed_today:
        lines.append("【本日決済したトレード】")
        for trade in stats.closed_today:
            lines.append(
                "- "
                + format_trade_line(
                    trade, settings.paper_stop_loss_pct, settings.paper_take_profit_pct
                )
            )
        lines.append("")
    else:
        lines.append("【本日決済したトレード】\nありません。\n")

    if stats.opened_today_still_open:
        lines.append("【本日新規エントリーし、まだ保有中のトレード】")
        for position in stats.opened_today_still_open:
            lines.append("- " + format_open_position_line(position))
        lines.append("")

    if not stats.had_any_activity_today:
        lines.append(
            "本日はエントリー・決済とも発生しませんでした（シグナル検知なし、"
            "または休場ではないが取引が発生しなかった日です）。その旨を淡々と"
            "伝え、無理に内容を水増ししないでください。"
        )

    return "\n".join(lines)


def _validate(article: DailyArticle) -> str | None:
    """バリデーション失敗時は理由の文字列を返す（成功時はNone）。"""
    for field_name, value in (
        ("title", article.title),
        ("meta_description", article.meta_description),
        ("lead", article.lead),
        ("commentary", article.commentary),
    ):
        stripped = value.strip()
        if not stripped:
            return f"{field_name}が空です"
        for snippet in _FORBIDDEN_SNIPPETS:
            if snippet in value:
                return f"{field_name}にテンプレート残骸/コードブロックらしき文字列（{snippet}）が含まれています"
    if len(article.commentary.strip()) < _MIN_COMMENTARY_LENGTH:
        return f"commentaryが短すぎます（{len(article.commentary)}文字）"
    return None


def build_fallback_article(stats: DailyStats) -> DailyArticle:
    """LLM呼び出しが失敗した場合の、数値のみで組み立てる固定テンプレート記事。

    投稿を欠かさないための最終防衛ライン。文章としての質は簡素だが、
    虚偽・誇張のない事実の列挙のみで構成する。
    """
    date_ja = format_date_ja(stats.target_date)
    title = f"【システム検証ログ】{date_ja}の自動売買結果まとめ"
    meta_description = (
        f"{date_ja}のペーパートレード（仮想シミュレーション）結果。"
        f"本日の実現損益{stats.today_realized_pnl_jpy:+,.0f}円、"
        f"決済{len(stats.closed_today)}件。"
    )
    lead = (
        f"{date_ja}のAI自動売買システム（ペーパートレード＝仮想シミュレーション、"
        "実発注なし）の検証結果をまとめます。"
    )

    if stats.had_any_activity_today:
        parts = [f"本日の決済件数は{len(stats.closed_today)}件、"
                 f"実現損益は{stats.today_realized_pnl_jpy:+,.0f}円でした。"]
        if stats.today_win_rate_pct is not None:
            parts.append(f"本日の勝率は{stats.today_win_rate_pct:.1f}%です。")
        if stats.opened_today_still_open:
            parts.append(
                f"本日新規にエントリーし、記事執筆時点で保有継続中のポジションが"
                f"{len(stats.opened_today_still_open)}件あります。"
            )
        commentary = " ".join(parts)
    else:
        commentary = (
            "本日はエントリー・決済とも発生しませんでした。"
            "システムが監視を継続する中でシグナル条件に合致する銘柄がなかった、"
            "またはシステム側の要因で取引が発生しなかった可能性があります。"
        )

    commentary += (
        f"\n\n累計では{len(stats.all_time_closed)}件を決済し、"
        f"累計実現損益は{stats.cumulative_realized_pnl_jpy:+,.0f}円です。"
        "この結果はkabuステーションAPIとClaude APIを用いたペーパートレード"
        "（帳簿上の仮想シミュレーション）であり、実際の資金は投じていません。"
        "投資助言ではなく、将来の運用成績を保証するものでもありません。"
    )

    return DailyArticle(
        title=title,
        meta_description=meta_description,
        lead=lead,
        commentary=commentary,
    )


def generate_article(settings: Settings, stats: DailyStats) -> ArticleResult:
    """Claude APIで記事本文を生成する。失敗時は固定テンプレートにフォールバックする。"""
    user_prompt = _build_user_prompt(stats, settings)

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
        response = client.with_options(timeout=settings.claude_timeout_seconds).messages.parse(
            model=settings.claude_model,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": user_prompt}],
            output_format=DailyArticle,
        )
    except (anthropic.APIError, anthropic.APIConnectionError, TimeoutError) as exc:
        logger.warning("Claude API呼び出しに失敗したためフォールバック記事を使用します: %s", exc)
        return ArticleResult(
            article=build_fallback_article(stats), used_fallback=True, error=str(exc)
        )
    except Exception as exc:  # noqa: BLE001 - 予期せぬ失敗も必ずフォールバックさせる
        logger.warning("記事生成中に予期しないエラーが発生しました: %s", exc)
        return ArticleResult(
            article=build_fallback_article(stats), used_fallback=True, error=str(exc)
        )

    article = response.parsed_output
    if article is None:
        logger.warning("Claude APIが構造化出力を返しませんでした（拒否/パース失敗の可能性）")
        return ArticleResult(
            article=build_fallback_article(stats),
            used_fallback=True,
            error="parsed_output is None",
        )

    validation_error = _validate(article)
    if validation_error:
        logger.warning("Claude出力のバリデーションに失敗しました: %s", validation_error)
        return ArticleResult(
            article=build_fallback_article(stats),
            used_fallback=True,
            raw_response_text=article.model_dump_json(),
            error=validation_error,
        )

    return ArticleResult(
        article=article, used_fallback=False, raw_response_text=article.model_dump_json()
    )

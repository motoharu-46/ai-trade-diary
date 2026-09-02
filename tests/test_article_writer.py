from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from generator import article_writer
from generator.article_writer import (
    DailyArticle,
    build_fallback_article,
    generate_article,
    _validate,
)
from generator.config import Settings
from generator.data_source import ClosedTrade, DailyStats


def _settings() -> Settings:
    return Settings(
        anthropic_api_key="sk-test-dummy",
        money_claude_db_path="unused.db",
        account_equity_jpy=1_000_000,
    )


def _stats(with_trade: bool) -> DailyStats:
    closed_today = []
    all_time_closed = []
    if with_trade:
        trade = ClosedTrade(
            symbol="1234",
            symbol_name="テスト株式",
            entry_time=datetime(2026, 9, 3, 9, 30, tzinfo=timezone.utc),
            entry_price=1000.0,
            quantity=100,
            claude_reason="出来高急増を検知しBUY判定",
            exit_time=datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
            exit_price=1050.0,
            exit_reason="TAKE_PROFIT",
            realized_pnl_jpy=5000.0,
            realized_pnl_pct=5.0,
        )
        closed_today = [trade]
        all_time_closed = [trade]

    return DailyStats(
        target_date=date(2026, 9, 3),
        closed_today=closed_today,
        opened_today_still_open=[],
        open_positions=[],
        all_time_closed=all_time_closed,
        today_realized_pnl_jpy=5000.0 if with_trade else 0.0,
        today_win_rate_pct=100.0 if with_trade else None,
        cumulative_realized_pnl_jpy=5000.0 if with_trade else 0.0,
        cumulative_win_rate_pct=100.0 if with_trade else None,
        current_equity_jpy=1_005_000.0 if with_trade else 1_000_000.0,
        base_equity_jpy=1_000_000.0,
        breakeven_win_rate_pct=2.0 / 7.0 * 100,
    )


def test_fallback_article_passes_validation_and_mentions_simulation():
    article = build_fallback_article(_stats(with_trade=True))
    assert _validate(article) is None
    assert "仮想" in article.commentary or "シミュレーション" in article.commentary


def test_fallback_article_on_quiet_day():
    article = build_fallback_article(_stats(with_trade=False))
    assert _validate(article) is None
    assert "発生しませんでした" in article.commentary


def test_validate_rejects_empty_field():
    article = DailyArticle(title="t", meta_description="d", lead="l", commentary=" " * 100)
    assert _validate(article) is not None


def test_validate_rejects_forbidden_snippet():
    article = DailyArticle(
        title="{{ leaked_template_var }}",
        meta_description="d",
        lead="l",
        commentary="x" * 100,
    )
    assert _validate(article) is not None


def test_generate_article_falls_back_on_api_exception():
    with patch.object(article_writer, "anthropic") as mock_anthropic:
        mock_anthropic.APIError = Exception
        mock_anthropic.APIConnectionError = Exception
        mock_anthropic.Anthropic.side_effect = RuntimeError("network down")

        result = generate_article(_settings(), _stats(with_trade=True))

    assert result.used_fallback is True
    assert result.error is not None
    assert _validate(result.article) is None


def test_generate_article_falls_back_on_invalid_output():
    bad_article = DailyArticle(
        title="{{ oops }}", meta_description="d", lead="l", commentary="x" * 100
    )
    mock_response = MagicMock()
    mock_response.parsed_output = bad_article

    with patch.object(article_writer, "anthropic") as mock_anthropic:
        mock_anthropic.APIError = Exception
        mock_anthropic.APIConnectionError = Exception
        mock_client = MagicMock()
        mock_client.with_options.return_value.messages.parse.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        result = generate_article(_settings(), _stats(with_trade=True))

    assert result.used_fallback is True


def test_generate_article_uses_llm_output_when_valid():
    good_article = DailyArticle(
        title="良いタイトル", meta_description="説明", lead="リード文",
        commentary="本日は仮想シミュレーションとして1件のトレードがありました。" * 2,
    )
    mock_response = MagicMock()
    mock_response.parsed_output = good_article

    with patch.object(article_writer, "anthropic") as mock_anthropic:
        mock_anthropic.APIError = Exception
        mock_anthropic.APIConnectionError = Exception
        mock_client = MagicMock()
        mock_client.with_options.return_value.messages.parse.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        result = generate_article(_settings(), _stats(with_trade=True))

    assert result.used_fallback is False
    assert result.article.title == "良いタイトル"

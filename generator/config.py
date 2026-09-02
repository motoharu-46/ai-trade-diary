"""blog_claudeの設定値。money_claudeのconfig/settings.py（pydantic-settings +
get_settings()の@lru_cacheシングルトン）パターンを踏襲する。

money_claudeとはコードを一切importしない完全分離のため、本プロジェクト専用の
.envを持つ（値は初回セットアップ時にmoney_claudeの.envから手動でコピーした
ものであり、以後は独立して管理する）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    anthropic_api_key: SecretStr
    claude_model: str = "claude-sonnet-5"
    claude_timeout_seconds: float = 60.0

    money_claude_db_path: str
    account_equity_jpy: float
    paper_stop_loss_pct: float = 2.0
    paper_take_profit_pct: float = 5.0

    site_title: str = "AIトレード検証日記"
    site_base_url: str = "https://example.github.io/blog_claude/"
    operator_name: str = "ブログ運営者"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()

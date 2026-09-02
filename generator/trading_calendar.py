"""東証の営業日判定（外部I/Oなし、純粋ロジック）。

money_claude/core/trading_calendar.py の`is_trading_day`と同一ロジックを
ここに複製している。money_claudeはこのリポジトリが将来publicになるため
コードをimportしない方針（詳細はREADME.md）とした結果の意図的な重複で、
10行程度の小さな純粋関数のため許容している。money_claude側の判定ロジックを
変更した場合は、こちらにも手動で反映すること。
"""

from __future__ import annotations

from datetime import date

import jpholiday

# jpholiday は国民の祝日のみを対象とし、年末年始（JPX独自の休業日）は
# 対象外のため個別に判定する。
_YEAR_END_NEW_YEAR_MONTH_DAYS = {(12, 31), (1, 1), (1, 2), (1, 3)}


def is_trading_day(target_date: date) -> bool:
    """土日・日本の祝日・年末年始(12/31〜1/3)を除く営業日かどうかを判定する。"""
    if target_date.weekday() >= 5:  # 5=土曜, 6=日曜
        return False
    if jpholiday.is_holiday(target_date):
        return False
    if (target_date.month, target_date.day) in _YEAR_END_NEW_YEAR_MONTH_DAYS:
        return False
    return True

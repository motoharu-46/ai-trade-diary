from datetime import date

from generator.trading_calendar import is_trading_day


def test_weekday_is_trading_day():
    # 2026-09-03 is a Thursday
    assert is_trading_day(date(2026, 9, 3)) is True


def test_saturday_is_not_trading_day():
    assert is_trading_day(date(2026, 9, 5)) is False


def test_sunday_is_not_trading_day():
    assert is_trading_day(date(2026, 9, 6)) is False


def test_national_holiday_is_not_trading_day():
    # 2026-01-01 New Year's Day (also year-end/new-year range)
    assert is_trading_day(date(2026, 1, 1)) is False


def test_year_end_new_year_is_not_trading_day():
    assert is_trading_day(date(2025, 12, 31)) is False
    assert is_trading_day(date(2026, 1, 3)) is False

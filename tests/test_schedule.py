from datetime import date, datetime

from nodes.schedule import DateRange, get_date_range


def test_label_within_one_month():
    assert DateRange(date(2026, 9, 1), date(2026, 9, 16)).label == "1–16 Sep 2026"


def test_label_single_day():
    assert DateRange(date(2026, 9, 1), date(2026, 9, 1)).label == "1 Sep 2026"


def test_label_across_months():
    assert DateRange(date(2026, 8, 31), date(2026, 9, 1)).label == "31 Aug – 1 Sep 2026"


def test_short_label_has_no_year():
    assert DateRange(date(2026, 9, 1), date(2026, 9, 16)).short_label == "1–16 Sep"


def test_date_range_is_month_start_through_yesterday():
    r = get_date_range(datetime(2026, 9, 17, 6, 0))
    assert (r.date_from, r.date_to) == (date(2026, 9, 1), date(2026, 9, 16))


def test_date_range_on_the_first_is_the_whole_previous_month():
    r = get_date_range(datetime(2026, 10, 1, 6, 0))
    assert (r.date_from, r.date_to) == (date(2026, 9, 1), date(2026, 9, 30))


def test_date_range_on_the_second_is_just_the_first():
    r = get_date_range(datetime(2026, 10, 2, 6, 0))
    assert (r.date_from, r.date_to) == (date(2026, 10, 1), date(2026, 10, 1))

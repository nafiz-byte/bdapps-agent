from nodes.filter import filter_positive_revenue, parse_revenue


def test_filter_keeps_only_positive_revenue():
    apps = [
        {"app_name": "A", "revenue": 100},
        {"app_name": "B", "revenue": 0},
        {"app_name": "C", "revenue": -5},
        {"app_name": "D", "revenue": "1,200.50"},
    ]
    result = filter_positive_revenue(apps)
    assert [a["app_name"] for a in result] == ["A", "D"]


def test_filter_empty_list():
    assert filter_positive_revenue([]) == []


def test_filter_drops_missing_revenue():
    apps = [{"app_name": "A"}, {"app_name": "B", "revenue": None}]
    assert filter_positive_revenue(apps) == []


def test_parse_revenue_handles_strings_and_missing_values():
    assert parse_revenue("1,234.50") == 1234.5
    assert parse_revenue("৳500") == 500.0
    assert parse_revenue(None) == 0.0
    assert parse_revenue("") == 0.0
    assert parse_revenue("garbage") == 0.0
    assert parse_revenue(42) == 42.0

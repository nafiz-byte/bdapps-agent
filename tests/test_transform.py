from nodes.transform import format_bdt, transform_apps


def test_transform_adds_revenue_bdt_and_date_range():
    apps = [{"app_name": "A", "revenue": 12345.0}]
    result = transform_apps(apps, "1–16 Sep 2026")
    assert result[0]["revenue_bdt"] == "BDT 12,345"
    assert result[0]["date_range"] == "1–16 Sep 2026"
    assert result[0]["revenue"] == 12345.0


def test_transform_preserves_extra_fields():
    apps = [{"app_name": "A", "revenue": "100", "extra": "keep-me"}]
    result = transform_apps(apps, "label")
    assert result[0]["extra"] == "keep-me"
    assert result[0]["revenue"] == 100.0


def test_transform_empty_list():
    assert transform_apps([], "label") == []


def test_format_bdt():
    assert format_bdt(1000) == "BDT 1,000"
    assert format_bdt(0) == "BDT 0"
    assert format_bdt(1234567.891) == "BDT 1,234,568"

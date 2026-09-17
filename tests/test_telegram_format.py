import re
from datetime import date

from nodes.schedule import DateRange
from nodes.telegram import AccountReport, build_sections, format_messages

SEPT = DateRange(date(2026, 9, 1), date(2026, 9, 16))
HEADER = "📊 <b>BDApps Revenue Report</b>\n📅 16 September 2026"


def _app(name, revenue):
    return {"app_name": name, "revenue": revenue}


def test_header_shows_last_counted_day():
    header = build_sections([AccountReport(name="a", username="u", apps=[_app("One", 10.0)])], SEPT)[0]
    assert header == HEADER


def test_account_section_lists_total_share_and_apps_by_revenue():
    reports = [
        AccountReport(name="a", username="u1", apps=[_app("One", 30.0), _app("Two", 45.0)]),
        AccountReport(name="b", username="u2", apps=[_app("Three", 25.0)]),
    ]
    lines = build_sections(reports, SEPT)[1].splitlines()
    assert lines[0] == "Monthly:"
    assert lines[1] == "🔹<b>Acc- u1</b>"
    assert lines[2] == "💰Total: <b>BDT 75</b> (75%)"
    assert lines[3] == "▫️Two: <b>BDT 45</b>"
    assert lines[4] == "▫️One: <b>BDT 30</b>"


def test_only_first_account_gets_monthly_label():
    reports = [
        AccountReport(name="a", username="u1", apps=[_app("One", 30.0)]),
        AccountReport(name="b", username="u2", apps=[_app("Two", 25.0)]),
    ]
    sections = build_sections(reports, SEPT)
    assert sections[1].startswith("Monthly:\n")
    assert sections[2].startswith("🔹<b>Acc- u2</b>")


def test_combined_total_follows_last_account_and_failures_come_last():
    reports = [
        AccountReport(name="a", username="u1", apps=[_app("One", 1000.0)]),
        AccountReport(name="b", username="u2", apps=[_app("Two", 500.0)]),
        AccountReport(name="broken", username="u3", error="login failed"),
    ]
    sections = build_sections(reports, SEPT)
    assert len(sections) == 4  # header, u1, u2 + combined total, failures
    assert sections[2].endswith(
        "▫️Two: <b>BDT 500</b>\n━━━━━━━━━━━━\n🧮<b>All accounts</b> (2/3):\n💰Total: <b>BDT 1,500</b> (approx)"
    )
    assert sections[3] == "⚠️<b>Acc- u3</b>: login failed"


def test_single_account_has_no_combined_total():
    sections = build_sections([AccountReport(name="a", username="u", apps=[_app("One", 10.0)])], SEPT)
    assert len(sections) == 2
    assert "All accounts" not in sections[1]


def test_all_accounts_failed_shows_only_header_and_failures():
    reports = [AccountReport(name="a", username="u1", error="login failed")]
    assert build_sections(reports, SEPT) == [HEADER, "⚠️<b>Acc- u1</b>: login failed"]


def test_account_without_revenue_shows_zero_total():
    reports = [
        AccountReport(name="a", username="u1", apps=[_app("One", 10.0)]),
        AccountReport(name="empty", username="u2", apps=[]),
    ]
    assert build_sections(reports, SEPT)[2].startswith("🔹<b>Acc- u2</b>\n💰Total: <b>BDT 0</b> (0%)")


def test_report_text_is_english_only():
    reports = [
        AccountReport(name="ok", username="a", apps=[_app("App One", 500.0)]),
        AccountReport(name="empty", username="b", apps=[]),
        AccountReport(name="broken", username="c", error="login failed"),
    ]
    for message in format_messages(reports, SEPT):
        assert not re.search("[ঀ-৿]", message)


def test_dynamic_text_is_escaped_everywhere():
    reports = [
        AccountReport(name="n", username="<script>", apps=[_app("R&D <beta>", 10.0)]),
        AccountReport(name="x", username="a&b", error="<boom> & bust"),
    ]
    for message in format_messages(reports, SEPT):
        without_tags = re.sub(r"</?b>", "", message)
        assert "<" not in without_tags and ">" not in without_tags
        assert not re.search(r"&(?!amp;|lt;|gt;|quot;)", without_tags)


def test_share_percent_adds_net_line_under_each_total():
    reports = [
        AccountReport(name="a", username="u1", apps=[_app("One", 30.0), _app("Two", 45.0)]),
        AccountReport(name="b", username="u2", apps=[_app("Three", 25.0)]),
    ]
    sections = build_sections(reports, SEPT, share_percent=40.0)
    lines = sections[1].splitlines()
    # Gross total and per-app lines stay as the portal reports them; Net is the 40% share.
    assert lines[2] == "💰Total: <b>BDT 75</b> (75%)"
    assert lines[3] == "💵Net: <b>BDT 30</b>"
    assert lines[4] == "▫️Two: <b>BDT 45</b>"
    assert lines[5] == "▫️One: <b>BDT 30</b>"
    assert sections[2].endswith("💰Total: <b>BDT 100</b> (approx)\n💵Net: <b>BDT 40</b>")


def test_share_percent_defaults_to_no_net_line():
    reports = [
        AccountReport(name="a", username="u1", apps=[_app("One", 100.0)]),
        AccountReport(name="b", username="u2", apps=[_app("Two", 50.0)]),
    ]
    with_default = build_sections(reports, SEPT)
    assert with_default == build_sections(reports, SEPT, share_percent=100.0)
    assert not any("Net" in section for section in with_default)


def test_format_messages_splits_when_too_long():
    many_reports = [AccountReport(name=f"a{i}", username=f"user{i}", error="x" * 200) for i in range(40)]
    many_reports.append(AccountReport(name="ok", username="u", apps=[_app(f"App {i}", 10.0) for i in range(200)]))
    messages = format_messages(many_reports, SEPT)
    assert len(messages) > 1
    for message in messages:
        assert len(message) <= 4096

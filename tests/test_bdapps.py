from nodes.bdapps import (
    extract_hidden_fields,
    extract_login_error,
    extract_login_form_action,
    extract_operators,
    parse_daily_app_rows,
    parse_number,
    parse_report_date,
    strip_tags,
    ticket_follow_url,
)


def test_ticket_follow_url_forwards_ticket_to_local_service():
    landing = (
        "https://user.bdapps.com/registration-v3/auth/redirect"
        "?local_service=https%3A%2F%2Fuser.bdapps.com%2Fviewer%2Fj_spring_cas_security_check"
        "&provider=internal&ticket=ST-123-abc&user_id=42"
    )
    assert ticket_follow_url(landing) == (
        "https://user.bdapps.com/viewer/j_spring_cas_security_check?ticket=ST-123-abc"
    )


def test_ticket_follow_url_appends_to_existing_query():
    landing = (
        "https://user.bdapps.com/registration-v3/auth/redirect"
        "?local_service=https%3A%2F%2Fuser.bdapps.com%2Fviewer%2Fcheck%3Fa%3D1&ticket=ST-1"
    )
    assert ticket_follow_url(landing) == "https://user.bdapps.com/viewer/check?a=1&ticket=ST-1"


def test_ticket_follow_url_refuses_other_hosts():
    landing = (
        "https://user.bdapps.com/registration-v3/auth/redirect"
        "?local_service=https%3A%2F%2Fevil.example.com%2Fsteal&ticket=ST-1"
    )
    assert ticket_follow_url(landing) is None


def test_ticket_follow_url_ignores_normal_pages():
    assert ticket_follow_url("https://user.bdapps.com/viewer/spring/sdpDailyAppRevenue.jsp") is None
    assert ticket_follow_url("https://user.bdapps.com/registration-v3/auth/redirect?provider=internal") is None


def test_extract_hidden_fields_ignores_non_hidden_inputs():
    page = """
    <form>
        <input type="hidden" name="lt" value="LT-123-abc">
        <input type='hidden' name='_eventId' value=''>
        <input type="text" name="visible" value="ignored">
    </form>
    """
    fields = extract_hidden_fields(page)
    assert fields == {"lt": "LT-123-abc", "_eventId": ""}


def test_extract_login_form_action_finds_form_with_password_field():
    page = """
    <form id="other"><input name="q"></form>
    <form action="/cas/login?service=x" method="post">
        <input type="hidden" name="lt" value="LT-1">
        <input name="username">
        <input type="password" name="password">
    </form>
    """
    assert extract_login_form_action(page) == "/cas/login?service=x"


def test_extract_operators_splits_id_and_name_on_plus():
    page = """
    <select name="operators">
        <option value="1+Grameenphone">GP</option>
        <option value="2+Robi">Robi</option>
    </select>
    """
    ids, names = extract_operators(page)
    assert ids == ["1", "2"]
    assert names == ["Grameenphone", "Robi"]


def test_extract_login_error_reads_msg_element():
    page = '<div id="msg">Invalid credentials.</div>'
    assert extract_login_error(page) == "Invalid credentials."


def test_extract_login_error_falls_back_when_nothing_found():
    assert extract_login_error("<html><body>nothing here</body></html>") == "check the username and password"


def test_strip_tags_collapses_whitespace_and_decodes_entities():
    assert strip_tags("<b>Hello&nbsp;\n\n World</b>") == "Hello World"


def test_parse_report_date_strips_ordinal_suffix():
    assert parse_report_date("September 16th, 2026") == "2026-09-16"
    assert parse_report_date("March 1st, 2026") == "2026-03-01"
    assert parse_report_date("not a date") is None


def test_parse_number_strips_currency_and_commas():
    assert parse_number("1,586.00 BDT") == 1586.0
    assert parse_number("-42") == -42.0
    assert parse_number("") == 0.0


def test_parse_daily_app_rows_reads_expected_columns():
    # 13 columns: Application, Type, Date, SP share%, Operator, Robi Earnings,
    # SP Earnings, App Total Revenue, Charged Msg Count, Traffic,
    # New Registrations, New DeRegs, Total Subscribers.
    row_html = (
        "<tr>"
        "<td>My App</td><td>Sub</td><td>September 16th, 2026</td><td>70%</td><td>Robi</td>"
        "<td>100</td><td>397.00</td><td>567.00</td><td>12</td><td>300</td>"
        "<td>5</td><td>2</td><td>1234</td>"
        "</tr>"
    )
    rows = parse_daily_app_rows(f"<table>{row_html}</table>")
    assert len(rows) == 1
    row = rows[0]
    assert row["app"] == "My App"
    assert row["date"] == "2026-09-16"
    assert row["sp_earnings"] == 397.0
    assert row["revenue"] == 567.0
    assert row["charged"] == 12
    assert row["new_subscribers"] == 5
    assert row["unsubscribed"] == 2
    assert row["total_subscribers"] == 1234


def test_parse_daily_app_rows_skips_header_and_short_rows():
    header_html = "<tr><th>Application</th><th>Type</th></tr>"
    assert parse_daily_app_rows(f"<table>{header_html}</table>") == []

"""bdapps developer-portal login and revenue scraping (plain HTTP, no browser).

bdapps has no revenue API, so figures come from the developer portal's own
"App Based Daily Revenue/Traffic" report after a normal CAS login. This is a
Python port of the working PHP implementation in
../bdapps-revenue-bot/src/BdappsPortal.php (see that project's git-free
history of trial and error against the real portal) -- same URLs, same
form fields, same malformed-HTML row parsing. Only the reporting shape
differs: this module returns one total-revenue-per-app number for the
whole date range, for the simpler filter/transform/telegram pipeline this
project uses.

Since the PHP version was written, bdapps routes CAS tickets through a
JavaScript-only "registration-v3/auth/redirect" page; ticket_follow_url()
does that hop over plain HTTP.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests

from config import Account

logger = logging.getLogger(__name__)


class BdappsError(RuntimeError):
    """Raised for any bdapps portal login/scrape failure."""


@dataclass
class DailyRow:
    """One app's figures for one day, as read from the daily app report."""

    app: str
    date: str
    sp_earnings: float
    revenue: float
    charged: int
    new_subscribers: int
    unsubscribed: int
    total_subscribers: int


@dataclass
class ScrapeResult:
    """One account's scrape outcome: either apps with revenue, or an error."""

    account_name: str
    username: str
    apps: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# HTML parsing helpers (regex-based, mirroring the PHP port -- the portal's
# report HTML is malformed enough, per the PHP code's own notes, that a
# strict parser is more trouble than it's worth for the daily-report rows).
# ---------------------------------------------------------------------------

_ATTR_RE = re.compile(r'([a-zA-Z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'>]+))')
_INPUT_TAG_RE = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
_FORM_RE = re.compile(r"<form\b([^>]*)>(.*?)</form>", re.IGNORECASE | re.DOTALL)
_PASSWORD_INPUT_RE = re.compile(r"<input\b[^>]*\bname\s*=\s*([\"']?)password\1", re.IGNORECASE)
_ERROR_ID_RE = re.compile(r'<[^>]+\bid\s*=\s*["\']?msg["\']?[^>]*>(.*?)</\w+>', re.IGNORECASE | re.DOTALL)
_ERROR_CLASS_RE = re.compile(
    r'<[^>]+\bclass\s*=\s*"[^"]*(?:error|alert)[^"]*"[^>]*>(.*?)</\w+>', re.IGNORECASE | re.DOTALL
)
_SELECT_OPERATORS_RE = re.compile(
    r'<select\b[^>]*\bname\s*=\s*["\']?operators["\']?[^>]*>(.*?)</select>', re.IGNORECASE | re.DOTALL
)
_OPTION_VALUE_RE = re.compile(r"<option\b[^>]*\bvalue\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", re.IGNORECASE)
_CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+", re.UNICODE)
_ORDINAL_RE = re.compile(r"(\d)(st|nd|rd|th)\b")
_NUMBER_RE = re.compile(r"[^0-9.\-]")
_TOTAL_PAGES_RE = re.compile(r"Total Pages:\s*(\d+)")


def _parse_attrs(tag_html: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for match in _ATTR_RE.finditer(tag_html):
        value = match.group(2) if match.group(2) is not None else match.group(3)
        if value is None:
            value = match.group(4)
        attrs[match.group(1).lower()] = html.unescape(value or "")
    return attrs


def extract_hidden_fields(page_html: str) -> Dict[str, str]:
    """Collect name/value pairs from every <input type="hidden"> on the page."""
    fields: Dict[str, str] = {}
    for tag in _INPUT_TAG_RE.findall(page_html):
        attrs = _parse_attrs(tag)
        if attrs.get("type", "").lower() == "hidden" and "name" in attrs:
            fields[attrs["name"]] = attrs.get("value", "")
    return fields


def extract_login_form_action(page_html: str) -> str:
    """Find the <form> containing an input named 'password' and return its action attribute."""
    for attrs_str, body in _FORM_RE.findall(page_html):
        if _PASSWORD_INPUT_RE.search(body):
            return _parse_attrs(attrs_str).get("action", "")
    raise BdappsError("bdapps login form not found; the login page may have changed")


def extract_login_error(page_html: str) -> str:
    """Best-effort extraction of the CAS error message from a failed-login page."""
    match = _ERROR_ID_RE.search(page_html) or _ERROR_CLASS_RE.search(page_html)
    if not match:
        return "check the username and password"
    text = strip_tags(match.group(1))
    return text or "check the username and password"


def extract_operators(page_html: str) -> Tuple[List[str], List[str]]:
    """Read the report form's operator <select> into (ids, names) from its 'id+name' option values."""
    match = _SELECT_OPERATORS_RE.search(page_html)
    if not match:
        return [], []
    ids: List[str] = []
    names: List[str] = []
    for dq, sq in _OPTION_VALUE_RE.findall(match.group(1)):
        value = html.unescape(dq or sq)
        operator_id, _, operator_name = value.partition("+")
        ids.append(operator_id)
        names.append(operator_name)
    return ids, names


def strip_tags(cell_html: str) -> str:
    """Strip tags, decode entities, and collapse whitespace -- for one <td> cell's contents."""
    text = _TAG_RE.sub("", cell_html)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def parse_report_date(text: str) -> Optional[str]:
    """'September 16th, 2026' -> '2026-09-16'; None for anything else."""
    cleaned = _ORDINAL_RE.sub(r"\1", text)
    try:
        return datetime.strptime(cleaned, "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_number(text: str) -> float:
    """'1,586.00 BDT' -> 1586.0"""
    cleaned = _NUMBER_RE.sub("", text)
    if cleaned in ("", "-", "."):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_daily_app_rows(page_html: str) -> List[Dict[str, Any]]:
    """Parse the daily-app-report HTML into rows.

    The report's rows have no closing </tr> and some cells hold broken
    attribute quoting, so rows are cut on "<tr" and read cell by cell
    rather than through a DOM parser (matches the proven PHP approach).
    """
    rows: List[Dict[str, Any]] = []
    for segment in re.split(r"<tr\b", page_html, flags=re.IGNORECASE):
        cells_raw = _CELL_RE.findall(segment)
        if len(cells_raw) < 13:
            continue
        cells = [strip_tags(c) for c in cells_raw]

        row_date = parse_report_date(cells[2])
        if row_date is None:
            continue

        rows.append({
            "app": cells[0],
            "date": row_date,
            "sp_earnings": parse_number(cells[6]),
            "revenue": parse_number(cells[7]),
            "charged": int(parse_number(cells[8])),
            "new_subscribers": int(parse_number(cells[10])),
            "unsubscribed": int(parse_number(cells[11])),
            "total_subscribers": int(parse_number(cells[12])),
        })
    return rows


PORTAL_HOST = "user.bdapps.com"
_TICKET_REDIRECT_PATH = "/registration-v3/auth/redirect"


def ticket_follow_url(landing_url: str) -> Optional[str]:
    """Where bdapps' JavaScript ticket page would send the browser next, or None.

    That page (…/registration-v3/auth/redirect?local_service=…&ticket=…) just
    forwards the CAS ticket to local_service. Only same-portal targets are
    followed, so a ticket is never handed to another host.
    """
    parts = urlsplit(landing_url)
    if parts.netloc != PORTAL_HOST or not parts.path.startswith(_TICKET_REDIRECT_PATH):
        return None
    query = parse_qs(parts.query)
    local_service = (query.get("local_service") or [""])[0]
    ticket = (query.get("ticket") or [""])[0]
    target = urlsplit(local_service)
    if not ticket or target.scheme != "https" or target.netloc != PORTAL_HOST:
        return None
    separator = "&" if target.query else "?"
    return f"{local_service}{separator}{urlencode({'ticket': ticket})}"


# ---------------------------------------------------------------------------
# Portal session
# ---------------------------------------------------------------------------


class BdappsPortal:
    """One logged-in session on the bdapps developer portal (user.bdapps.com)."""

    LOGIN_URL = (
        "https://user.bdapps.com/cas/login?service="
        "https%3A%2F%2Fuser.bdapps.com%2Fregistration%2Fj_spring_cas_security_check"
    )
    DAILY_APP_FORM_URL = "https://user.bdapps.com/viewer/spring/sdpDailyAppRevenue.jsp"
    DAILY_APP_REPORT_URL = "https://user.bdapps.com/viewer/spring/dailyAppReport.jsp"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    )

    def __init__(self, username: str, password: str, timeout: int = 30) -> None:
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def login(self) -> str:
        """Log in through bdapps' CAS login form; returns the URL the portal redirected to."""
        page = self.session.get(self.LOGIN_URL, timeout=self.timeout)
        if page.status_code >= 400:
            raise BdappsError(f"bdapps login page returned HTTP {page.status_code}")

        action = extract_login_form_action(page.text)
        fields = extract_hidden_fields(page.text)
        if fields.get("_eventId", None) == "":
            fields["_eventId"] = "submit"
        fields["username"] = self.username
        fields["password"] = self.password

        post_url = urljoin(page.url, action) if action else page.url
        result = self.session.post(post_url, data=fields, timeout=self.timeout)

        if "/cas/login" in result.url:
            raise BdappsError(f"login failed: {extract_login_error(result.text)}")

        return result.url

    def daily_app_report(self, date_from: date, date_to: date) -> List[DailyRow]:
        """Every app's numbers for every day from date_from to date_to (inclusive), all operators."""
        form_html = self._daily_app_form_html()
        fields = extract_hidden_fields(form_html)
        operator_ids, operator_names = extract_operators(form_html)

        fields.update({
            "RP_app_daily_start_date": date_from.strftime("%Y-%m-%d"),
            "RP_app_daily_end_date": date_to.strftime("%Y-%m-%d"),
            "fromDate": date_from.strftime("%Y-%m-%d"),
            "toDate": date_to.strftime("%Y-%m-%d"),
            "pageSize": "500",
            "RP_select_all_apps": "true",
            "selectAll": "on",
            "RP_show_graphs": "false",
            "daily_rp_operator_ids": ",".join(operator_ids),
            "daily_rp_operator_names": ",".join(operator_names),
            "select_all_operators": "true",
            "selectAl": "on",  # matches the portal's own form field name (not a typo)
        })

        rows: List[DailyRow] = []
        page_no = 1
        total_pages = 1
        while page_no <= total_pages:
            fields["pageNo"] = str(page_no)
            response = self._get(self.DAILY_APP_REPORT_URL, params=fields)
            self._assert_report_page(response)
            if "SP Earnings" not in response.text or "New Registration Count" not in response.text:
                self._save_debug(response.text, "report_unexpected")
                raise BdappsError("bdapps daily app report looks different than expected; the portal may have changed")

            rows.extend(DailyRow(**row) for row in parse_daily_app_rows(response.text))

            match = _TOTAL_PAGES_RE.search(response.text)
            if match:
                total_pages = min(int(match.group(1)), 50)
            page_no += 1

        return rows

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        """GET that also completes bdapps' JavaScript ticket hop when the portal lands on it."""
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        follow = ticket_follow_url(response.url)
        if follow:
            response = self.session.get(follow, timeout=self.timeout)
        return response

    def _daily_app_form_html(self) -> str:
        # The first request to the report module goes through a single-sign-on
        # hop that lands on the module's home page instead, so retry.
        for _ in range(3):
            response = self._get(self.DAILY_APP_FORM_URL)
            self._assert_report_page(response)
            if extract_hidden_fields(response.text).get("rptSpId", ""):
                return response.text
        self._save_debug(response.text, "form_no_sp_id")
        raise BdappsError("SP ID not found on the bdapps report form; the portal may have changed")

    def _assert_report_page(self, response: requests.Response) -> None:
        if "/cas/login" in response.url:
            raise BdappsError("bdapps report module sent us back to the login page")
        if response.status_code >= 400:
            raise BdappsError(f"bdapps report module returned HTTP {response.status_code}")

    def _save_debug(self, page_html: str, label: str) -> None:
        """Save page source for inspection when parsing doesn't find what it expects."""
        try:
            debug_dir = Path(__file__).resolve().parent.parent / "debug"
            debug_dir.mkdir(exist_ok=True)
            path = debug_dir / f"{self.username}_{label}_{datetime.now():%Y%m%d_%H%M%S}.html"
            path.write_text(page_html, encoding="utf-8")
            logger.warning("Saved debug page source to %s", path)
        except OSError:
            logger.exception("Could not save debug page source")


def scrape_account_revenue(account: Account, date_from: date, date_to: date) -> ScrapeResult:
    """Log in to one bdapps account and return each app's total revenue for the date range."""
    portal = BdappsPortal(account.username, account.password)
    try:
        portal.login()
        rows = portal.daily_app_report(date_from, date_to)
    except BdappsError as exc:
        logger.warning("Account %s: %s", account.name, exc)
        return ScrapeResult(account_name=account.name, username=account.username, error=str(exc))
    except requests.RequestException as exc:
        logger.warning("Account %s: network error: %s", account.name, exc)
        return ScrapeResult(account_name=account.name, username=account.username, error=f"network error: {exc}")

    totals: Dict[str, float] = {}
    for row in rows:
        totals[row.app] = totals.get(row.app, 0.0) + row.revenue

    apps = [{"app_name": app_name, "revenue": revenue} for app_name, revenue in totals.items()]
    apps.sort(key=lambda a: a["revenue"], reverse=True)
    return ScrapeResult(account_name=account.name, username=account.username, apps=apps)

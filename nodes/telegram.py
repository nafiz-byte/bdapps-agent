"""Telegram HTML report formatting and delivery for the bdapps revenue agent.

Layout follows the user's own sample: one fact per line, an emoji label with
no space after it, bold values. Per account ("Acc- <username>"): its total
with share of the grand total, then each app's revenue. A combined total
follows the last account (only when more than one account has data), and
any failed accounts are listed last.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

from nodes.schedule import DateRange
from nodes.transform import format_bdt

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096
_SECTION_SEP = "\n\n"
_DIVIDER = "━" * 12


@dataclass
class AccountReport:
    """Revenue-scrape outcome for one bdapps account, ready for reporting."""

    name: str
    username: str
    apps: List[Dict[str, object]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def total_revenue(self) -> float:
        return sum(float(app.get("revenue", 0.0)) for app in self.apps)


def _esc(value: object) -> str:
    """HTML-escape a value for safe embedding in a Telegram HTML message."""
    return html.escape(str(value), quote=False)


def _account_label(acc: AccountReport) -> str:
    return f"<b>Acc- {_esc(acc.username)}</b>"


def _net_line(total: float, share_percent: float) -> List[str]:
    """The "Net" line for a total, or nothing when the full amount is kept.

    At share_percent 100 a Net line would just repeat the Total above it.
    """
    if share_percent >= 100:
        return []
    return [f"💵Net: <b>{format_bdt(total * share_percent / 100)}</b>"]


def _account_section(acc: AccountReport, grand_total: float, share_percent: float) -> str:
    """One account: label, total, net, then each app, highest revenue first.

    Total and the per-app lines are the portal's own (gross) figures, so the
    report can be checked against the portal; the Net line below Total is the
    share actually earned (share_percent, e.g. 40 for a 60% cut). The
    percentage-of-grand-total is computed from the gross totals.
    """
    total = acc.total_revenue
    total_line = f"💰Total: <b>{format_bdt(total)}</b>"
    if grand_total > 0:
        total_line += f" ({round(total / grand_total * 100)}%)"

    lines = [f"🔹{_account_label(acc)}", total_line, *_net_line(total, share_percent)]
    for app in sorted(acc.apps, key=lambda a: float(a.get("revenue", 0.0)), reverse=True):
        lines.append(f"▫️{_esc(app.get('app_name', '-'))}: <b>{format_bdt(float(app.get('revenue', 0.0)))}</b>")
    return "\n".join(lines)


def build_sections(
    account_reports: List[AccountReport], date_range: DateRange, share_percent: float = 100.0
) -> List[str]:
    """Return the report as HTML sections: [header, account..., failures?].

    share_percent (default 100, i.e. no Net lines at all) adds the earned
    share under each "Total" -- see _account_section.
    """
    ok = [acc for acc in account_reports if not acc.error]
    failed = [acc for acc in account_reports if acc.error]
    grand_total = sum(acc.total_revenue for acc in ok)

    accounts = [_account_section(acc, grand_total, share_percent) for acc in ok]
    if accounts:
        accounts[0] = "Monthly:\n" + accounts[0]
        # With a single account the combined total would just repeat it.
        if len(ok) > 1:
            accounts[-1] += "\n" + "\n".join([
                _DIVIDER,
                f"🧮<b>All accounts</b> ({len(ok)}/{len(account_reports)}):",
                f"💰Total: <b>{format_bdt(grand_total)}</b> (approx)",
                *_net_line(grand_total, share_percent),
            ])

    header = f"📊 <b>BDApps Revenue Report</b>\n📅 {date_range.date_to.day} {date_range.date_to:%B %Y}"
    sections = [header, *accounts]
    if failed:
        sections.append("\n".join(f"⚠️{_account_label(acc)}: {_esc(acc.error)}" for acc in failed))
    return sections


def _fit(section: str) -> List[str]:
    """Split a section on line boundaries if it alone exceeds Telegram's message limit."""
    if len(section) <= MAX_MESSAGE_LENGTH:
        return [section]
    pieces: List[str] = []
    current = ""
    for line in section.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if current and len(candidate) > MAX_MESSAGE_LENGTH:
            pieces.append(current)
            candidate = line
        current = candidate
    pieces.append(current)
    return pieces


def format_messages(
    account_reports: List[AccountReport], date_range: DateRange, share_percent: float = 100.0
) -> List[str]:
    """Pack report sections into one or more Telegram HTML messages (<=4096 chars each)."""
    sections = [
        piece for section in build_sections(account_reports, date_range, share_percent) for piece in _fit(section)
    ]
    messages: List[str] = []
    current: List[str] = []
    current_len = 0
    for section in sections:
        add_len = len(section) + (len(_SECTION_SEP) if current else 0)
        if current and current_len + add_len > MAX_MESSAGE_LENGTH:
            messages.append(_SECTION_SEP.join(current))
            current, current_len = [], 0
            add_len = len(section)
        current.append(section)
        current_len += add_len
    if current:
        messages.append(_SECTION_SEP.join(current))
    return messages


def send_report(
    token: str,
    chat_id: str,
    account_reports: List[AccountReport],
    date_range: DateRange,
    share_percent: float = 100.0,
) -> None:
    """Format and send the full report to a Telegram chat, splitting into multiple messages if needed."""
    for message in format_messages(account_reports, date_range, share_percent):
        _send_message(token, chat_id, message)


def _send_message(token: str, chat_id: str, html_text: str) -> None:
    response = requests.post(
        f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"},
        timeout=15,
    )
    payload = response.json()
    if not payload.get("ok"):
        logger.error("Telegram sendMessage failed: %s", payload)
        raise RuntimeError(f"Telegram rejected the message: {payload.get('description', 'unknown error')}")
    logger.info("Telegram report chunk sent (%d chars)", len(html_text))

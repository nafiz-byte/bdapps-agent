"""Date-range calculation and optional continuous scheduling for the workflow."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DateRange:
    """Inclusive revenue reporting window."""

    date_from: date
    date_to: date

    @property
    def short_label(self) -> str:
        """English label without the year, e.g. '1–16 Sep' (or '1 Sep' for a single day)."""
        end = f"{self.date_to.day} {self.date_to:%b}"
        if self.date_from == self.date_to:
            return end
        if (self.date_from.year, self.date_from.month) == (self.date_to.year, self.date_to.month):
            return f"{self.date_from.day}–{end}"
        return f"{self.date_from.day} {self.date_from:%b} – {end}"

    @property
    def label(self) -> str:
        """English label with the year, e.g. '1–16 Sep 2026'."""
        return f"{self.short_label} {self.date_to.year}"


def get_date_range(now: datetime) -> DateRange:
    """Reporting window: yesterday's month from its 1st through yesterday.

    On the 1st of a month that is the whole previous month, since today has
    no data yet.
    """
    date_to = now.date() - timedelta(days=1)
    return DateRange(date_from=date_to.replace(day=1), date_to=date_to)


def now_in_timezone(tz_name: str) -> datetime:
    """Current datetime in the given IANA timezone (e.g. 'Asia/Dhaka')."""
    return datetime.now(ZoneInfo(tz_name))


def run_forever(job: Callable[[], None], report_time: str, tz_name: str, poll_seconds: int = 30) -> None:
    """Block forever, invoking `job` once per day at `report_time` (HH:MM) in `tz_name`.

    Intended for a self-hosted/VPS/always-on deployment. On GitHub Actions,
    PythonAnywhere or cPanel, prefer their own cron/scheduled-task feature
    and run workflow.py once per invocation instead.
    """
    target_hour, target_minute = (int(part) for part in report_time.split(":"))
    last_run_date: Optional[date] = None
    logger.info("Scheduler started: daily run at %s (%s)", report_time, tz_name)
    while True:
        now = now_in_timezone(tz_name)
        if (now.hour, now.minute) >= (target_hour, target_minute) and now.date() != last_run_date:
            logger.info("Scheduled time reached (%s), running job", now.isoformat())
            try:
                job()
            except Exception:
                logger.exception("Scheduled job raised an unhandled exception")
            last_run_date = now.date()
        time.sleep(poll_seconds)

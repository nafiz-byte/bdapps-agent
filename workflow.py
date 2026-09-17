#!/usr/bin/env python3
"""Daily bdapps multi-account revenue report -> Telegram.

Usage:
    python workflow.py                run once now and send to Telegram
    python workflow.py --preview      build the report and print it, without sending
    python workflow.py --loop         run forever, firing once a day at REPORT_TIME

--loop is for a self-hosted/always-on machine (e.g. Windows Task Scheduler
running this in the background, or a VPS). On GitHub Actions, PythonAnywhere
or cPanel, their own scheduler should call this once with no flags.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Tuple

from config import Account, Config, ConfigError, load_config
from nodes.bdapps import scrape_account_revenue
from nodes.filter import filter_positive_revenue
from nodes.schedule import DateRange, get_date_range, now_in_timezone, run_forever
from nodes.telegram import AccountReport, format_messages, send_report
from nodes.transform import transform_apps

logger = logging.getLogger(__name__)


def configure_logging(log_file: Path) -> None:
    """Log to both workflow.log and stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def process_account(account: Account, date_range: DateRange) -> AccountReport:
    """Scrape, filter, and transform one account's revenue. Never raises."""
    try:
        result = scrape_account_revenue(account, date_range.date_from, date_range.date_to)
    except Exception as exc:  # noqa: BLE001 - a failing account must not stop the others
        logger.exception("Account %s: unexpected error", account.name)
        return AccountReport(name=account.name, username=account.username, error=str(exc))

    if result.error:
        return AccountReport(name=account.name, username=account.username, error=result.error)

    positive = filter_positive_revenue(result.apps)
    transformed = transform_apps(positive, date_range.label)
    return AccountReport(name=account.name, username=account.username, apps=transformed)


def run(config: Config, send: bool = True) -> Tuple[List[AccountReport], DateRange]:
    """Run the workflow once: scrape every account, then send one combined Telegram report."""
    date_range = get_date_range(now_in_timezone(config.timezone))
    logger.info(
        "Running for %s..%s (%s), %d account(s)",
        date_range.date_from, date_range.date_to, date_range.label, len(config.accounts),
    )

    reports = [process_account(account, date_range) for account in config.accounts]

    if send:
        send_report(config.telegram_token, config.telegram_chat_id, reports, date_range)
        logger.info("Report sent to Telegram for %d account(s)", len(reports))
    return reports, date_range


def main() -> int:
    parser = argparse.ArgumentParser(description="bdapps multi-account revenue agent")
    parser.add_argument("--loop", action="store_true", help="run forever, once a day at REPORT_TIME")
    parser.add_argument("--preview", action="store_true", help="print the report instead of sending it")
    args = parser.parse_args()

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"কনফিগারেশন ভুল: {exc}", file=sys.stderr)
        return 1

    configure_logging(config.log_file)

    if args.preview:
        reports, date_range = run(config, send=False)
        for message in format_messages(reports, date_range):
            print(message)
        return 0

    if args.loop:
        run_forever(lambda: run(config), config.report_time, config.timezone)
        return 0

    run(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())

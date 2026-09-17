"""Multi-account configuration loader for the bdapps revenue agent.

Accounts are auto-detected from ACCOUNT_<n>_USERNAME / ACCOUNT_<n>_PASSWORD
pairs in the environment, so adding account 4, 5, ... needs no code change.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ACCOUNT_USERNAME_RE = re.compile(r"^ACCOUNT_(\d+)_USERNAME$")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Account:
    """One bdapps developer-portal account credential set."""

    index: int
    name: str
    username: str
    password: str


@dataclass(frozen=True)
class Config:
    """Fully resolved runtime configuration for one workflow run."""

    telegram_token: str
    telegram_chat_id: str
    report_time: str
    timezone: str
    revenue_share_percent: float
    accounts: List[Account]
    debug_dir: Path
    log_file: Path


def discover_accounts(env: Dict[str, str]) -> List[Account]:
    """Auto-detect ACCOUNT_<n>_USERNAME / ACCOUNT_<n>_PASSWORD / ACCOUNT_<n>_NAME triples.

    An index is skipped if its USERNAME or PASSWORD is missing. NAME is
    optional and defaults to "account<n>".
    """
    indices = sorted({int(m.group(1)) for key in env if (m := ACCOUNT_USERNAME_RE.match(key))})

    accounts: List[Account] = []
    for idx in indices:
        username = env.get(f"ACCOUNT_{idx}_USERNAME", "").strip()
        password = env.get(f"ACCOUNT_{idx}_PASSWORD", "")
        if not username or not password:
            continue
        name = env.get(f"ACCOUNT_{idx}_NAME", "").strip() or f"account{idx}"
        accounts.append(Account(index=idx, name=name, username=username, password=password))
    return accounts


def load_config(env_file: Optional[str] = None) -> Config:
    """Load and validate configuration from environment variables / a .env file.

    Raises ConfigError with a Bengali message describing exactly what's
    missing, since this is what a scheduled run's log/stderr will show.
    """
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=False)

    accounts = discover_accounts(dict(os.environ))
    if not accounts:
        raise ConfigError(
            ".env-এ কোনো account পাওয়া যায়নি। অন্তত ACCOUNT_1_USERNAME ও ACCOUNT_1_PASSWORD সেট করুন।"
        )

    telegram_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not telegram_token or not telegram_chat_id:
        raise ConfigError("TELEGRAM_TOKEN এবং TELEGRAM_CHAT_ID .env-এ সেট করা আবশ্যক।")

    revenue_share_raw = os.environ.get("REVENUE_SHARE_PERCENT", "100").strip() or "100"
    try:
        revenue_share_percent = float(revenue_share_raw)
    except ValueError as exc:
        raise ConfigError(
            f"REVENUE_SHARE_PERCENT-এর মান সংখ্যা হতে হবে, পাওয়া গেছে: {revenue_share_raw!r}"
        ) from exc
    if not (0 <= revenue_share_percent <= 100):
        raise ConfigError("REVENUE_SHARE_PERCENT-এর মান ০ থেকে ১০০-এর মধ্যে হতে হবে।")

    debug_dir = BASE_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)

    return Config(
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        report_time=os.environ.get("REPORT_TIME", "06:00").strip(),
        timezone=os.environ.get("TIMEZONE", "Asia/Dhaka").strip(),
        revenue_share_percent=revenue_share_percent,
        accounts=accounts,
        debug_dir=debug_dir,
        log_file=BASE_DIR / "workflow.log",
    )

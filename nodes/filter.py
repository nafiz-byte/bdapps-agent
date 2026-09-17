"""Keep only apps whose revenue is greater than zero."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def parse_revenue(value: Any) -> float:
    """Best-effort numeric coercion; missing or unparseable values become 0."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace("৳", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        logger.warning("Could not parse revenue value %r; treating as 0", value)
        return 0.0


def filter_positive_revenue(apps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only the app records whose revenue is strictly greater than 0."""
    filtered = [app for app in apps if parse_revenue(app.get("revenue")) > 0]
    logger.info("Filtered %d/%d apps with revenue > 0", len(filtered), len(apps))
    return filtered

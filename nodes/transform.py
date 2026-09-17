"""Add derived fields (revenue_bdt, date_range) to filtered app records."""
from __future__ import annotations

from typing import Any, Dict, List

from nodes.filter import parse_revenue


def format_bdt(amount: float) -> str:
    """Format a number as a whole-taka string, e.g. 'BDT 12,345'."""
    return f"BDT {amount:,.0f}"


def transform_apps(apps: List[Dict[str, Any]], date_range_label: str) -> List[Dict[str, Any]]:
    """Attach 'revenue_bdt' and 'date_range' to each app record; normalizes 'revenue' to float."""
    transformed = []
    for app in apps:
        revenue = parse_revenue(app.get("revenue"))
        enriched = dict(app)
        enriched["revenue"] = revenue
        enriched["revenue_bdt"] = format_bdt(revenue)
        enriched["date_range"] = date_range_label
        transformed.append(enriched)
    return transformed

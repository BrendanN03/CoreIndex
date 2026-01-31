"""
Business logic for feasibility calculations.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from app.schemas.models import PackageDescriptor, Window
from app.repositories.memory.storage import storage


def calculate_ngh_required(packages: List[PackageDescriptor]) -> float:
    """Calculate total NGH required as sum of package size estimates."""
    return sum(pkg.size_estimate_ngh for pkg in packages)


def calculate_earliest_start(packages: List[PackageDescriptor], requested_window: Window) -> str:
    """
    Calculate the earliest start time given artifact sizes and Standard prepare rules.

    For Standard prepare rules, we assume:
    - Minimum 1 hour preparation time
    - Next available window that matches the requested window specification
    """
    now = datetime.utcnow()

    # Find next hour that matches the requested ISO hour
    target_hour = requested_window.iso_hour

    # Start from current hour
    candidate = now.replace(minute=0, second=0, microsecond=0)

    # If current hour is past the target hour today, start from tomorrow
    if candidate.hour >= target_hour:
        candidate += timedelta(days=1)

    # Set to target hour
    candidate = candidate.replace(hour=target_hour)

    # Add minimum preparation time (1 hour for Standard)
    if requested_window.sla.value == "standard":
        candidate += timedelta(hours=1)

    # Ensure we're at least 1 hour in the future
    if candidate <= now + timedelta(hours=1):
        candidate += timedelta(hours=1)

    return candidate.isoformat() + "Z"


def calculate_voucher_gap(ngh_required: float, key: str) -> float:
    """Calculate voucher gap: NGH required minus vouchers already deposited."""
    voucher_balance = storage.get_voucher_balance(key)
    gap = ngh_required - voucher_balance
    return max(0.0, gap)  # Gap cannot be negative


def check_milestone_sanity(packages: List[PackageDescriptor]) -> dict:
    """
    Check milestone sanity:
    - first_output_ok: All packages have first_output <= 2 minutes (120 seconds)
    - size_band_ok: All packages are within size band [5, 15] NGH
    """
    first_output_ok = True
    size_band_ok = True

    for pkg in packages:
        # Check first output timing
        if pkg.first_output_estimate_seconds is not None:
            if pkg.first_output_estimate_seconds > 120:  # 2 minutes
                first_output_ok = False

        # Check size band [5, 15] NGH
        if pkg.size_estimate_ngh < 5.0 or pkg.size_estimate_ngh > 15.0:
            size_band_ok = False

    return {"first_output_ok": first_output_ok, "size_band_ok": size_band_ok}


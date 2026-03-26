"""
Risk and margin helpers for demo market controls.
"""

from __future__ import annotations

from app.schemas.models import OptionContractResponse


MAX_NOTIONAL_LIMIT = 25000.0
MAX_MARGIN_LIMIT = 5000.0


def compute_option_initial_margin(contract: OptionContractResponse) -> float:
    """
    Demo initial margin model for listed options.

    Margin = 20% of premium notional + 10% of underlying notional.
    """
    underlying_notional = contract.forward_price_per_ngh * contract.quantity_ngh
    return 0.2 * contract.premium_notional + 0.1 * underlying_notional


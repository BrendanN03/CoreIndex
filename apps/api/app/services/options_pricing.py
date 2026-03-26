"""
Black-76 option pricing helpers for compute futures contracts.
"""

from __future__ import annotations

import math

from app.schemas.models import OptionGreeks, OptionQuoteRequest, OptionQuoteResponse, OptionType


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _black76_price(
    option_type: OptionType,
    forward: float,
    strike: float,
    t: float,
    vol: float,
    rate: float,
) -> float:
    sigma_sqrt_t = vol * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * t) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    discount = math.exp(-rate * t)

    if option_type == OptionType.CALL:
        return discount * (forward * _normal_cdf(d1) - strike * _normal_cdf(d2))
    return discount * (strike * _normal_cdf(-d2) - forward * _normal_cdf(-d1))


def quote_option(request: OptionQuoteRequest) -> OptionQuoteResponse:
    forward = request.forward_price_per_ngh
    strike = request.strike_price_per_ngh
    t = request.time_to_expiry_years
    vol = request.implied_volatility
    rate = request.risk_free_rate
    quantity = request.quantity_ngh

    sigma_sqrt_t = vol * math.sqrt(t)
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * t) / sigma_sqrt_t
    discount = math.exp(-rate * t)
    nd1 = _normal_pdf(d1)

    premium = _black76_price(request.option_type, forward, strike, t, vol, rate)
    intrinsic = (
        max(0.0, forward - strike)
        if request.option_type == OptionType.CALL
        else max(0.0, strike - forward)
    )
    time_value = max(0.0, premium - intrinsic)

    if request.option_type == OptionType.CALL:
        delta = discount * _normal_cdf(d1)
    else:
        delta = -discount * _normal_cdf(-d1)

    gamma = discount * nd1 / (forward * sigma_sqrt_t)
    vega = discount * forward * nd1 * math.sqrt(t)

    # Use finite-difference bumps for stable demo theta and rho values.
    day = 1.0 / 365.0
    t_down = max(1e-6, t - day)
    price_t_down = _black76_price(request.option_type, forward, strike, t_down, vol, rate)
    theta = (price_t_down - premium) / day

    rate_bump = 1e-4
    price_r_up = _black76_price(request.option_type, forward, strike, t, vol, rate + rate_bump)
    rho = (price_r_up - premium) / rate_bump

    return OptionQuoteResponse(
        option_type=request.option_type,
        premium_per_ngh=premium,
        premium_notional=premium * quantity,
        intrinsic_value_per_ngh=intrinsic,
        time_value_per_ngh=time_value,
        greeks=OptionGreeks(
            delta=delta,
            gamma=gamma,
            vega=vega,
            theta=theta,
            rho=rho,
        ),
    )

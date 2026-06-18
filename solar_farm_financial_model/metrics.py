"""Financial metrics utilities."""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np


def npv(rate: float, cash_flows: Iterable[float]) -> float:
    """Compute the net present value of a cash flow stream."""

    cash_flows = list(cash_flows)
    periods = np.arange(len(cash_flows))
    discount_factors = 1 / (1 + rate) ** periods
    return float(np.dot(cash_flows, discount_factors))


def discount_factors_from_periodic_rates(periodic_rates: Iterable[float]) -> np.ndarray:
    """Return period-by-period discount factors starting at 1.0 for period 0."""

    rates = np.asarray(list(periodic_rates), dtype=float)
    if rates.size == 0:
        return np.asarray([], dtype=float)
    factors = np.ones(rates.size, dtype=float)
    if rates.size > 1:
        factors[1:] = np.cumprod(1.0 + rates[1:])
    return factors


def npv_variable(periodic_rates: Iterable[float], cash_flows: Iterable[float]) -> float:
    """Compute NPV using a per-period discount-rate series."""

    cash_flows = np.asarray(list(cash_flows), dtype=float)
    discount_factors = discount_factors_from_periodic_rates(periodic_rates)
    if cash_flows.size == 0:
        return 0.0
    if discount_factors.size != cash_flows.size:
        raise ValueError("periodic_rates and cash_flows must have the same length")
    return float(np.dot(cash_flows, 1.0 / discount_factors))


def irr(cash_flows: Iterable[float], guess: float = 0.1) -> Optional[float]:
    """Return the internal rate of return for the given cash flows."""

    cash_flows = list(cash_flows)
    if len(cash_flows) < 2:
        return None

    def _npv(rate: float) -> float:
        return npv(rate, cash_flows)

    rate = guess
    try:
        for _ in range(100):
            derivative = sum(-period * cf / (1 + rate) ** (period + 1) for period, cf in enumerate(cash_flows))
            if derivative == 0:
                break
            value = _npv(rate)
            new_rate = rate - value / derivative
            if abs(new_rate - rate) < 1e-6:
                return new_rate
            rate = new_rate
    except (FloatingPointError, ValueError, OverflowError):
        return None
    return None


def payback_period(cash_flows: Iterable[float]) -> Optional[int]:
    """Calculate the payback period in periods (months) if possible."""

    cumulative = 0.0
    for idx, cf in enumerate(cash_flows):
        cumulative += cf
        if cumulative >= 0:
            return idx
    return None

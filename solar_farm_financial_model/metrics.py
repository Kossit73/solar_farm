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


def irr(cash_flows: Iterable[float], guess: float = 0.1) -> Optional[float]:
    """Return the internal rate of return for the given cash flows."""

    cash_flows = list(cash_flows)
    if len(cash_flows) < 2:
        return None

    try:
        return float(np.irr(cash_flows))  # type: ignore[attr-defined]
    except AttributeError:
        # numpy >= 1.20 removed np.irr; implement a simple solver instead.
        def _npv(rate: float) -> float:
            return npv(rate, cash_flows)

        rate = guess
        for _ in range(100):
            derivative = sum(-period * cf / (1 + rate) ** (period + 1) for period, cf in enumerate(cash_flows))
            if derivative == 0:
                break
            value = _npv(rate)
            new_rate = rate - value / derivative
            if abs(new_rate - rate) < 1e-6:
                return new_rate
            rate = new_rate
        return None
    except (FloatingPointError, ValueError):
        return None


def payback_period(cash_flows: Iterable[float]) -> Optional[int]:
    """Calculate the payback period in periods (months) if possible."""

    cumulative = 0.0
    for idx, cf in enumerate(cash_flows):
        cumulative += cf
        if cumulative >= 0:
            return idx
    return None

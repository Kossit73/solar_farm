"""Scenario and sensitivity helpers for the Solar Farm model."""

from __future__ import annotations

import copy
from typing import Callable, Dict, Tuple

from .model import ModelOutputs, SolarFarmFinancialModel
from .schemas import Assumptions


def apply_sensitivity_ppa_rate(assumptions: Assumptions, multiplier: float) -> None:
    assumptions.revenue.ppa.rate_curve.initial = max(
        0.0,
        assumptions.revenue.ppa.rate_curve.initial * multiplier,
    )


def apply_sensitivity_merchant_rate(assumptions: Assumptions, multiplier: float) -> None:
    assumptions.revenue.merchant.rate_curve.initial = max(
        0.0,
        assumptions.revenue.merchant.rate_curve.initial * multiplier,
    )


def apply_sensitivity_rec_rate(assumptions: Assumptions, multiplier: float) -> None:
    assumptions.revenue.rec.initial = max(0.0, assumptions.revenue.rec.initial * multiplier)


def apply_sensitivity_capacity_factor(assumptions: Assumptions, multiplier: float) -> None:
    new_factor = assumptions.energy.capacity_factor * multiplier
    assumptions.energy.capacity_factor = max(0.01, min(1.0, new_factor))


def apply_sensitivity_capex(assumptions: Assumptions, multiplier: float) -> None:
    for item in assumptions.capex_items:
        item.amount = max(0.0, item.amount * multiplier)


def apply_sensitivity_fixed_opex(assumptions: Assumptions, multiplier: float) -> None:
    for item in assumptions.fixed_opex:
        item.annual_cost = max(0.0, item.annual_cost * multiplier)
        if hasattr(item, "cost_per_mwh"):
            item.cost_per_mwh = max(0.0, item.cost_per_mwh * multiplier)


def apply_sensitivity_variable_opex(assumptions: Assumptions, multiplier: float) -> None:
    for item in assumptions.variable_opex:
        item.cost_per_mwh = max(0.0, item.cost_per_mwh * multiplier)


def apply_sensitivity_discount_rate(assumptions: Assumptions, multiplier: float) -> None:
    updated = assumptions.global_assumptions.discount_rate * multiplier
    assumptions.global_assumptions.discount_rate = max(0.0, min(0.99, updated))


SENSITIVITY_OPTIONS: Dict[str, Tuple[str, Callable[[Assumptions, float], None]]] = {
    "ppa_rate": ("PPA Rate", apply_sensitivity_ppa_rate),
    "merchant_rate": ("Merchant Rate", apply_sensitivity_merchant_rate),
    "rec_rate": ("REC Price", apply_sensitivity_rec_rate),
    "capacity_factor": ("Capacity Factor", apply_sensitivity_capacity_factor),
    "capex_total": ("Total Capex", apply_sensitivity_capex),
    "fixed_opex": ("Fixed Opex", apply_sensitivity_fixed_opex),
    "variable_opex": ("Variable Opex", apply_sensitivity_variable_opex),
    "discount_rate": ("Discount Rate", apply_sensitivity_discount_rate),
}


def simulate_outputs(base: Assumptions, modifier: Callable[[Assumptions], None]) -> ModelOutputs:
    """Clone assumptions, apply a modifier, and return the resulting model outputs."""

    scenario = copy.deepcopy(base)
    modifier(scenario)
    scenario_model = SolarFarmFinancialModel(scenario)
    return scenario_model.run()


def simulate_metrics(base: Assumptions, modifier: Callable[[Assumptions], None]) -> Dict[str, float]:
    """Clone assumptions, apply a modifier, and return the resulting metrics."""

    return simulate_outputs(base, modifier).metrics

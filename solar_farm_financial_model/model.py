"""Core simulation logic for the Solar Farm Financial Model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .metrics import irr, npv, payback_period
from .schemas import Assumptions, DebtFacility


@dataclass
class ModelOutputs:
    """Container for the model outputs."""

    monthly_results: pd.DataFrame
    annual_summary: pd.DataFrame
    metrics: Dict[str, float]


class SolarFarmFinancialModel:
    """Run deterministic project finance projections for a solar farm."""

    def __init__(self, assumptions: Assumptions) -> None:
        self.assumptions = assumptions
        self._timeline = self._build_timeline()

    def run(self) -> ModelOutputs:
        """Execute the projection and return consolidated outputs."""

        monthly = pd.DataFrame(index=self._timeline)
        monthly.index.name = "month_start"

        energy = self._compute_energy_profile()
        revenue = self._compute_revenue(energy)
        fixed_opex = self._compute_fixed_opex()
        variable_opex = self._compute_variable_opex(energy)
        capex, depreciation = self._compute_capex_and_depreciation()
        debt_schedule = self._compute_debt_schedule()

        tax_rate = self.assumptions.global_assumptions.tax.income_tax_rate

        monthly["energy_mwh"] = energy
        monthly = monthly.join(revenue)
        monthly = monthly.join(fixed_opex)
        monthly = monthly.join(variable_opex)
        monthly["total_opex"] = monthly.filter(like="opex_").sum(axis=1)
        monthly["capex"] = capex
        monthly["depreciation"] = depreciation
        monthly = monthly.join(debt_schedule)

        monthly["revenue_total"] = monthly.filter(like="revenue_").sum(axis=1)
        monthly["ebitda"] = monthly["revenue_total"] - monthly["total_opex"]
        monthly["ebit"] = monthly["ebitda"] - monthly["depreciation"]

        monthly["taxable_income"] = (monthly["ebit"] - monthly["debt_interest"]).clip(lower=0)
        monthly["tax_payment"] = monthly["taxable_income"] * tax_rate
        monthly["net_income"] = monthly["ebit"] - monthly["debt_interest"] - monthly["tax_payment"]

        monthly["fcff"] = (
            monthly["ebit"] * (1 - tax_rate) + monthly["depreciation"] - monthly["capex"]
        )
        monthly["debt_free_cash_flow"] = (
            monthly["fcff"]
            - monthly["debt_interest"] * (1 - tax_rate)
            - monthly["debt_principal"]
            + monthly["debt_draw"]
        )
        monthly["equity_cash_flow"] = monthly["debt_free_cash_flow"]

        terminal_cash = self._compute_terminal_value(monthly)
        if terminal_cash is not None:
            monthly.iloc[-1, monthly.columns.get_loc("fcff")] += terminal_cash["fcff"]
            monthly.iloc[-1, monthly.columns.get_loc("equity_cash_flow")] += terminal_cash["equity"]

        distribution = self.assumptions.global_assumptions.distribution.normalized()
        monthly["investor_cash_flow"] = monthly["equity_cash_flow"] * distribution.investor_share
        monthly["owner_cash_flow"] = monthly["equity_cash_flow"] * distribution.owner_share

        metrics = self._compute_metrics(monthly)
        annual_summary = self._build_annual_summary(monthly)

        return ModelOutputs(monthly_results=monthly, annual_summary=annual_summary, metrics=metrics)

    # ------------------------------------------------------------------
    # Timeline helpers
    def _build_timeline(self) -> pd.DatetimeIndex:
        start = pd.to_datetime(self.assumptions.global_assumptions.start_date)
        periods = self.assumptions.global_assumptions.forecast_months
        return pd.date_range(start=start, periods=periods, freq="MS")

    def _year_index(self) -> np.ndarray:
        return np.arange(len(self._timeline)) // 12

    def _month_in_year(self) -> np.ndarray:
        return np.arange(len(self._timeline)) % 12

    # ------------------------------------------------------------------
    # Energy
    def _compute_energy_profile(self) -> pd.Series:
        energy_cfg = self.assumptions.energy
        energy_cfg.validate()

        years = self._year_index()
        month_in_year = self._month_in_year()

        base_annual_output = (
            energy_cfg.capacity_mw
            * energy_cfg.annual_hours
            * energy_cfg.capacity_factor
        )
        degradation_factor = (1 - energy_cfg.degradation_rate) ** years
        annual_output = base_annual_output * degradation_factor
        seasonality = np.array(energy_cfg.seasonality)
        seasonality = seasonality / seasonality.sum()
        monthly_output = annual_output * seasonality[month_in_year]

        return pd.Series(monthly_output, index=self._timeline, name="energy_mwh")

    # ------------------------------------------------------------------
    # Revenue
    def _compute_revenue(self, energy: pd.Series) -> pd.DataFrame:
        revenue_cfg = self.assumptions.revenue
        years = self._year_index()

        ppa_rate = revenue_cfg.ppa.rate_curve.initial * (1 + revenue_cfg.ppa.rate_curve.annual_escalation) ** years
        merchant_rate = (
            revenue_cfg.merchant.rate_curve.initial
            * (1 + revenue_cfg.merchant.rate_curve.annual_escalation) ** years
        )
        rec_rate = revenue_cfg.rec.initial * (1 + revenue_cfg.rec.annual_escalation) ** years

        ppa_energy = energy.values * revenue_cfg.ppa.share_of_output
        merchant_energy = energy.values * revenue_cfg.merchant.share_of_output
        rec_energy = energy.values  # assume RECs on all generation

        revenue_df = pd.DataFrame(index=self._timeline)
        revenue_df["revenue_ppa"] = ppa_energy * ppa_rate
        revenue_df["revenue_merchant"] = merchant_energy * merchant_rate
        revenue_df["revenue_rec"] = rec_energy * rec_rate
        return revenue_df

    # ------------------------------------------------------------------
    # Operating expenditure
    def _compute_fixed_opex(self) -> pd.DataFrame:
        years = self._year_index()
        fixed = pd.DataFrame(index=self._timeline)

        for item in self.assumptions.fixed_opex:
            annual_cost = item.annual_cost * (1 + item.inflation_rate) ** years
            monthly_cost = annual_cost / 12.0
            mask = np.arange(len(self._timeline)) + 1 >= item.start_month
            fixed[f"opex_fixed_{item.name.lower().replace(' ', '_')}"] = monthly_cost * mask
        return fixed

    def _compute_variable_opex(self, energy: pd.Series) -> pd.DataFrame:
        years = self._year_index()
        variable = pd.DataFrame(index=self._timeline)

        for item in self.assumptions.variable_opex:
            rate = item.cost_per_mwh * (1 + item.escalation_rate) ** years
            cost = energy.values * rate
            mask = np.arange(len(self._timeline)) + 1 >= item.start_month
            variable[f"opex_variable_{item.name.lower().replace(' ', '_')}"] = cost * mask
        return variable

    # ------------------------------------------------------------------
    # Capex and depreciation
    def _compute_capex_and_depreciation(self) -> Tuple[pd.Series, pd.Series]:
        capex = pd.Series(0.0, index=self._timeline)
        depreciation = pd.Series(0.0, index=self._timeline)

        for item in self.assumptions.capex_items:
            profile = item.normalized_profile()
            for offset, portion in enumerate(profile):
                if offset < len(capex):
                    capex.iloc[offset] += item.amount * portion
            depreciation_start = len(profile)
            if item.depreciation_years > 0:
                monthly_dep = item.amount / (item.depreciation_years * 12)
                depreciation.iloc[depreciation_start:] += monthly_dep
        return capex, depreciation

    # ------------------------------------------------------------------
    # Debt schedule
    def _compute_debt_schedule(self) -> pd.DataFrame:
        schedule = pd.DataFrame(0.0, index=self._timeline, columns=["debt_interest", "debt_principal", "debt_draw", "debt_balance"])

        for facility in self.assumptions.debt_facilities:
            facility_schedule = self._build_facility_schedule(facility)
            schedule += facility_schedule

        return schedule

    def _build_facility_schedule(self, facility: DebtFacility) -> pd.DataFrame:
        schedule = pd.DataFrame(0.0, index=self._timeline, columns=["debt_interest", "debt_principal", "debt_draw", "debt_balance"])
        start_idx = facility.start_month - 1
        if start_idx >= len(schedule):
            return schedule

        balance = facility.principal
        monthly_rate = facility.interest_rate / 12
        term_months = facility.term_months
        io_months = facility.interest_only_months

        payment_months = max(term_months - io_months, 1)
        amortization_payment = np.pmt(monthly_rate, payment_months, -balance) if payment_months > 0 else 0.0

        for month_idx in range(start_idx, min(start_idx + term_months, len(schedule))):
            row = schedule.iloc[month_idx]
            if month_idx == start_idx:
                row["debt_draw"] = facility.principal
                row["debt_balance"] = balance
            interest = balance * monthly_rate
            principal_payment = 0.0

            if month_idx - start_idx < io_months:
                principal_payment = 0.0
            else:
                principal_payment = amortization_payment - interest
                principal_payment = max(principal_payment, 0.0)
                principal_payment = min(principal_payment, balance)
                balance -= principal_payment

            row["debt_interest"] = interest
            row["debt_principal"] = principal_payment
            row["debt_balance"] = balance
            schedule.iloc[month_idx] = row

        return schedule

    # ------------------------------------------------------------------
    # Terminal value
    def _compute_terminal_value(self, monthly: pd.DataFrame) -> Dict[str, float] | None:
        assumptions = self.assumptions.global_assumptions
        if not assumptions.include_terminal_value:
            return None

        trailing_ebitda = monthly["ebitda"].iloc[-12:].mean() if len(monthly) >= 12 else monthly["ebitda"].iloc[-1]
        enterprise_value = trailing_ebitda * assumptions.exit_multiple

        tax_rate = assumptions.tax.capital_gains_tax_rate
        net_proceeds = enterprise_value * (1 - tax_rate)
        remaining_debt = monthly["debt_balance"].iloc[-1]
        equity_value = net_proceeds - remaining_debt

        return {"fcff": net_proceeds, "equity": equity_value}

    # ------------------------------------------------------------------
    def _compute_metrics(self, monthly: pd.DataFrame) -> Dict[str, float]:
        discount_rate = self.assumptions.global_assumptions.discount_rate
        project_cash_flow = monthly["fcff"].values
        equity_cash_flow = monthly["equity_cash_flow"].values
        investor_cash_flow = monthly["investor_cash_flow"].values
        owner_cash_flow = monthly["owner_cash_flow"].values

        metrics = {
            "project_npv": npv(discount_rate, project_cash_flow),
            "project_irr": irr(project_cash_flow) or float("nan"),
            "equity_irr": irr(equity_cash_flow) or float("nan"),
            "investor_irr": irr(investor_cash_flow) or float("nan"),
            "owner_irr": irr(owner_cash_flow) or float("nan"),
            "project_payback_months": payback_period(project_cash_flow) or float("nan"),
        }
        return metrics

    # ------------------------------------------------------------------
    def _build_annual_summary(self, monthly: pd.DataFrame) -> pd.DataFrame:
        annual = monthly.resample("A").agg(
            {
                "revenue_total": "sum",
                "total_opex": "sum",
                "ebitda": "sum",
                "ebit": "sum",
                "tax_payment": "sum",
                "net_income": "sum",
                "fcff": "sum",
                "equity_cash_flow": "sum",
            }
        )
        annual.index = annual.index.year
        return annual

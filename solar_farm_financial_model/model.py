"""Core simulation logic for the Solar Farm Financial Model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .metrics import irr, npv, payback_period
from .schemas import Assumptions, CapexItem, DebtFacility, InventoryPayableSettings, ReceivableSettings


def capex_item_schedule(
    item: CapexItem, timeline: pd.DatetimeIndex
) -> Tuple[pd.Series, pd.Series, pd.Series, Dict[str, float]]:
    """Return monthly capex/depreciation schedules and summary for an item."""

    total_months = len(timeline)
    capex_series = pd.Series(0.0, index=timeline)
    depreciation_series = pd.Series(0.0, index=timeline)
    opening_series = pd.Series(0.0, index=timeline)

    profile = item.normalized_profile()
    for offset, portion in enumerate(profile):
        if offset >= total_months:
            break
        if portion:
            capex_series.iloc[offset] += item.amount * portion

    start_index = max(0, min(total_months - 1, getattr(item, "service_month", 1) - 1))
    for idx, portion in enumerate(profile):
        if portion > 0:
            start_index = max(start_index, idx)
            break

    opening_balance = max(0.0, getattr(item, "opening_balance", 0.0))
    if opening_balance > 0 and start_index < total_months:
        opening_series.iloc[start_index] += opening_balance

    depreciation_basis = opening_balance + max(0.0, item.amount)
    method = getattr(item, "method", "Straight-Line").lower()
    recognized_months = 0
    ending_balance = depreciation_basis

    if depreciation_basis > 0:
        if method == "declining balance":
            rate = max(0.0, min(1.0, getattr(item, "depreciation_rate", 0.0)))
            if rate > 0:
                monthly_rate = 1 - (1 - rate) ** (1 / 12)
                book_value = depreciation_basis
                for idx in range(start_index, total_months):
                    depreciation_value = book_value * monthly_rate
                    if depreciation_value <= 0:
                        break
                    if depreciation_value > book_value:
                        depreciation_value = book_value
                    depreciation_series.iloc[idx] += depreciation_value
                    book_value = max(0.0, book_value - depreciation_value)
                    recognized_months += 1
                    if book_value <= 1e-6:
                        break
                ending_balance = book_value
            else:
                method = "straight-line"

        if method == "straight-line":
            months_of_life = max(1, item.depreciation_years * 12)
            monthly_dep = depreciation_basis / months_of_life
            for n in range(months_of_life):
                idx = start_index + n
                if idx >= total_months:
                    break
                depreciation_series.iloc[idx] += monthly_dep
                recognized_months += 1
            ending_balance = max(0.0, depreciation_basis - monthly_dep * recognized_months)

    total_depreciation = float(depreciation_series.sum())

    summary = {
        "asset_type": item.name,
        "method": getattr(item, "method", "Straight-Line"),
        "service_month": start_index + 1,
        "acquisition": max(0.0, item.amount),
        "opening_balance": opening_balance,
        "total_asset_cost": opening_balance + max(0.0, item.amount),
        "total_depreciation": total_depreciation,
        "cumulative_depreciation": total_depreciation,
        "ending_book_value": ending_balance,
        "depreciation_years": item.depreciation_years,
        "depreciation_rate": getattr(item, "depreciation_rate", 0.0),
    }

    return capex_series, depreciation_series, opening_series, summary


@dataclass
class ModelOutputs:
    """Container for the model outputs."""

    monthly_results: pd.DataFrame
    annual_summary: pd.DataFrame
    metrics: Dict[str, float]
    asset_summaries: pd.DataFrame


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
        capex, depreciation, opening_ppe, asset_summaries = self._compute_capex_and_depreciation()
        debt_schedule = self._compute_debt_schedule()
        tax_rate_series = self._tax_rate_series()

        monthly["energy_mwh"] = energy
        monthly = monthly.join(revenue)
        monthly = monthly.join(fixed_opex)
        monthly = monthly.join(variable_opex)
        monthly["total_opex"] = monthly.filter(like="opex_").sum(axis=1)
        monthly["capex"] = capex
        monthly["depreciation"] = depreciation
        monthly["ppe_opening_balance"] = opening_ppe
        monthly = monthly.join(debt_schedule)
        monthly["revenue_total"] = monthly.filter(like="revenue_").sum(axis=1)
        monthly["ebitda"] = monthly["revenue_total"] - monthly["total_opex"]
        monthly["ebit"] = monthly["ebitda"] - monthly["depreciation"]

        monthly["tax_rate"] = tax_rate_series

        working_capital = self._compute_working_capital(monthly)
        monthly = monthly.join(working_capital)

        monthly["taxable_income"] = (monthly["ebit"] - monthly["debt_interest"]).clip(lower=0)
        monthly["tax_payment"] = monthly["taxable_income"] * monthly["tax_rate"]
        monthly["net_income"] = (
            monthly["ebit"] - monthly["debt_interest"] - monthly["tax_payment"]
        )

        monthly["fcff"] = (
            monthly["ebit"] * (1 - monthly["tax_rate"])
            + monthly["depreciation"]
            - monthly["capex"]
            - monthly["delta_working_capital"]
        )
        monthly["debt_free_cash_flow"] = (
            monthly["fcff"]
            - monthly["debt_interest"] * (1 - monthly["tax_rate"])
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

        return ModelOutputs(
            monthly_results=monthly,
            annual_summary=annual_summary,
            metrics=metrics,
            asset_summaries=asset_summaries,
        )

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
    def _compute_capex_and_depreciation(
        self,
    ) -> Tuple[pd.Series, pd.Series, pd.Series, pd.DataFrame]:
        capex = pd.Series(0.0, index=self._timeline)
        depreciation = pd.Series(0.0, index=self._timeline)
        opening_balances = pd.Series(0.0, index=self._timeline)
        asset_summaries: List[Dict[str, float]] = []

        for item in self.assumptions.capex_items:
            item_capex, item_dep, item_opening, summary = capex_item_schedule(item, self._timeline)
            capex += item_capex
            depreciation += item_dep
            opening_balances += item_opening
            asset_summaries.append(summary)

        asset_summary_df = pd.DataFrame(asset_summaries)
        return capex, depreciation, opening_balances, asset_summary_df

    # ------------------------------------------------------------------
    # Debt schedule
    def _compute_debt_schedule(self) -> pd.DataFrame:
        schedule = pd.DataFrame(0.0, index=self._timeline, columns=["debt_interest", "debt_principal", "debt_draw", "debt_balance"])

        for facility in self.assumptions.debt_facilities:
            facility_schedule = self._build_facility_schedule(facility)
            schedule += facility_schedule

        return schedule

    # ------------------------------------------------------------------
    def _tax_rate_series(self) -> pd.Series:
        base_rate = self.assumptions.global_assumptions.tax.income_tax_rate
        schedule = sorted(self.assumptions.tax_schedule, key=lambda item: item.year)
        rates = []
        current_rate = base_rate
        schedule_index = 0

        for ts in self._timeline:
            year = ts.year
            while schedule_index < len(schedule) and schedule[schedule_index].year <= year:
                current_rate = schedule[schedule_index].tax_rate
                schedule_index += 1
            rates.append(current_rate)

        return pd.Series(rates, index=self._timeline, name="tax_rate")

    def _compute_working_capital(self, monthly: pd.DataFrame) -> pd.DataFrame:
        receivable_map: Dict[int, ReceivableSettings] = {
            cfg.year: cfg for cfg in self.assumptions.receivable_settings
        }
        inventory_map: Dict[int, InventoryPayableSettings] = {
            cfg.year: cfg for cfg in self.assumptions.inventory_settings
        }

        last_receivable = None
        last_inventory = None

        records = []
        for ts, revenue, opex in zip(
            self._timeline, monthly["revenue_total"].values, monthly["total_opex"].values
        ):
            receivable_cfg = receivable_map.get(ts.year, last_receivable)
            if receivable_cfg is None and receivable_map:
                receivable_cfg = receivable_map[min(receivable_map)]
            last_receivable = receivable_cfg

            inventory_cfg = inventory_map.get(ts.year, last_inventory)
            if inventory_cfg is None and inventory_map:
                inventory_cfg = inventory_map[min(inventory_map)]
            last_inventory = inventory_cfg

            if receivable_cfg:
                denom = max(1.0, receivable_cfg.days_in_year / 12.0)
                accounts_receivable = revenue * (receivable_cfg.receivable_days / denom)
                prepaid = opex * (receivable_cfg.prepaid_expense_days / denom)
                other_assets = opex * (receivable_cfg.other_asset_days / denom)
            else:
                accounts_receivable = 0.0
                prepaid = 0.0
                other_assets = 0.0

            if inventory_cfg:
                denom_inv = max(1.0, inventory_cfg.days_in_year / 12.0)
                inventory_balance = opex * (inventory_cfg.inventory_days / denom_inv)
                accounts_payable = opex * (inventory_cfg.accounts_payable_days / denom_inv)
            else:
                inventory_balance = 0.0
                accounts_payable = 0.0

            working_capital = (
                accounts_receivable + prepaid + other_assets + inventory_balance - accounts_payable
            )

            records.append(
                {
                    "accounts_receivable": accounts_receivable,
                    "prepaid_expenses": prepaid,
                    "other_current_assets": other_assets,
                    "inventory_balance": inventory_balance,
                    "accounts_payable": accounts_payable,
                    "working_capital": working_capital,
                }
            )

        working_capital_df = pd.DataFrame(records, index=self._timeline)
        working_capital_df["delta_working_capital"] = working_capital_df["working_capital"].diff().fillna(
            working_capital_df["working_capital"]
        )
        return working_capital_df

    @staticmethod
    def _level_payment(balance: float, periodic_rate: float, periods: int) -> float:
        """Compute the constant payment needed to amortize a loan.

        Replaces the deprecated ``numpy.pmt`` helper with an explicit
        implementation to keep compatibility with modern NumPy releases.
        """

        if periods <= 0:
            return 0.0
        if abs(periodic_rate) < 1e-12:
            return balance / periods

        growth = (1 + periodic_rate) ** periods
        return balance * periodic_rate * growth / (growth - 1)

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
        amortization_payment = self._level_payment(balance, monthly_rate, payment_months)

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
                "capex": "sum",
                "depreciation": "sum",
                "debt_interest": "sum",
                "debt_principal": "sum",
                "debt_draw": "sum",
                "delta_working_capital": "sum",
            }
        )
        annual.index = annual.index.year
        return annual

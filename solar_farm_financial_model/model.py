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

        if method == "straight-line" and item.depreciation_years > 0:
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
        self.assumptions.validate()
        self._apply_panel_linkages()

        monthly = pd.DataFrame(index=self._timeline)
        monthly.index.name = "month_start"

        energy = self._compute_energy_profile()
        curtailment_rate = max(0.0, min(0.95, float(getattr(self.assumptions.energy, "curtailment_rate", 0.0))))
        if curtailment_rate > 0:
            energy = energy * (1 - curtailment_rate)
        revenue = self._compute_revenue(energy)
        fixed_opex = self._compute_fixed_opex(energy)
        variable_opex = self._compute_variable_opex(energy)
        capex, depreciation, opening_ppe, asset_summaries = self._compute_capex_and_depreciation()
        debt_schedule = self._compute_debt_schedule()
        tax_rate_series = self._tax_rate_series()

        monthly["energy_mwh"] = energy
        monthly = monthly.join(revenue)
        monthly = monthly.join(fixed_opex)
        monthly = monthly.join(variable_opex)
        monthly["total_opex"] = monthly.filter(like="opex_").sum(axis=1)
        legal_opex_adder = max(0.0, float(getattr(self.assumptions, "change_in_law_opex_per_mwh", 0.0)))
        if legal_opex_adder > 0:
            monthly["opex_change_in_law"] = monthly["energy_mwh"] * legal_opex_adder
            monthly["total_opex"] = monthly["total_opex"] + monthly["opex_change_in_law"]
        monthly["capex"] = capex + self._compute_lifecycle_capex()
        arrangement_fee_rate = max(0.0, float(getattr(self.assumptions, "arrangement_fee_rate", 0.0)))
        monthly["arrangement_fees"] = 0.0
        if arrangement_fee_rate > 0 and self.assumptions.debt_facilities:
            upfront_fees = sum(f.principal for f in self.assumptions.debt_facilities) * arrangement_fee_rate
            monthly.iloc[0, monthly.columns.get_loc("capex")] += upfront_fees
            monthly.iloc[0, monthly.columns.get_loc("arrangement_fees")] = upfront_fees
        monthly["depreciation"] = depreciation
        monthly["ppe_opening_balance"] = opening_ppe
        monthly = monthly.join(debt_schedule)
        monthly["revenue_total"] = monthly.filter(like="revenue_").sum(axis=1)
        monthly["ebitda"] = monthly["revenue_total"] - monthly["total_opex"]
        monthly["ebit"] = monthly["ebitda"] - monthly["depreciation"]

        monthly["tax_rate"] = tax_rate_series

        working_capital = self._compute_working_capital(monthly)
        monthly = monthly.join(working_capital)

        bonus_dep_rate = max(
            0.0,
            min(1.0, float(getattr(self.assumptions, "bonus_depreciation_rate", 0.0))),
        )
        bonus_depreciation = monthly["capex"] * bonus_dep_rate
        monthly["bonus_depreciation"] = bonus_depreciation
        monthly["taxable_income"] = (
            monthly["ebit"] - monthly["debt_interest"] - monthly["bonus_depreciation"]
        ).clip(lower=0)
        monthly["tax_payment"] = monthly["taxable_income"] * monthly["tax_rate"]
        monthly["net_income"] = (
            monthly["ebit"] - monthly["debt_interest"] - monthly["tax_payment"]
        )
        monthly["debt_service"] = monthly["debt_interest"] + monthly["debt_principal"]
        monthly["cfads"] = (
            monthly["ebitda"] - monthly["tax_payment"] - monthly["delta_working_capital"]
        )
        monthly["dscr"] = np.where(
            monthly["debt_service"] > 0,
            monthly["cfads"] / monthly["debt_service"],
            np.nan,
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
        monthly["itc_benefit"] = self._compute_itc_benefit(monthly["capex"])
        monthly["debt_free_cash_flow"] = monthly["debt_free_cash_flow"] + monthly["itc_benefit"]
        monthly["dsra_required"] = self._compute_dsra_required(monthly["debt_service"])
        monthly["dsra_change"] = monthly["dsra_required"].diff().fillna(monthly["dsra_required"])
        monthly["cash_after_dsra"] = monthly["debt_free_cash_flow"] - monthly["dsra_change"]
        maintenance_reserve_rate = max(0.0, float(getattr(self.assumptions, "major_maintenance_reserve_rate", 0.0)))
        inverter_reserve_rate = max(0.0, float(getattr(self.assumptions, "inverter_reserve_rate", 0.0)))
        monthly["major_maintenance_reserve_deposit"] = monthly["cash_after_dsra"].clip(lower=0) * maintenance_reserve_rate
        monthly["inverter_reserve_deposit"] = monthly["cash_after_dsra"].clip(lower=0) * inverter_reserve_rate
        monthly["cash_after_reserves"] = (
            monthly["cash_after_dsra"]
            - monthly["major_maintenance_reserve_deposit"]
            - monthly["inverter_reserve_deposit"]
        )
        cash_sweep_pct = max(0.0, min(1.0, float(getattr(self.assumptions, "cash_sweep_pct", 0.0))))
        monthly["cash_sweep"] = monthly["cash_after_reserves"].clip(lower=0) * cash_sweep_pct
        monthly["cash_after_sweep"] = monthly["cash_after_reserves"] - monthly["cash_sweep"]
        monthly["equity_contribution"] = (monthly["capex"] - monthly["debt_draw"]).clip(lower=0)
        monthly["equity_distribution"] = monthly["cash_after_sweep"].clip(lower=0)
        monthly["equity_cash_flow"] = -monthly["equity_contribution"] + monthly["equity_distribution"]

        terminal_cash = self._compute_terminal_value(monthly)
        if terminal_cash is not None:
            monthly.iloc[-1, monthly.columns.get_loc("fcff")] += terminal_cash["fcff"]
            monthly.iloc[-1, monthly.columns.get_loc("equity_cash_flow")] += terminal_cash["equity"]

        distribution = self.assumptions.global_assumptions.distribution.normalized()
        monthly["investor_cash_flow"] = monthly["equity_cash_flow"] * distribution.investor_share
        monthly["owner_cash_flow"] = monthly["equity_cash_flow"] * distribution.owner_share
        monthly["sources_total"] = (
            monthly["debt_draw"]
            + monthly["equity_contribution"]
            + monthly["revenue_total"]
            + monthly["itc_benefit"]
        )
        monthly["uses_total"] = (
            monthly["capex"]
            + monthly["total_opex"]
            + monthly["debt_interest"]
            + monthly["debt_principal"]
            + monthly["tax_payment"]
            + monthly["dsra_change"]
            + monthly["major_maintenance_reserve_deposit"]
            + monthly["inverter_reserve_deposit"]
            + monthly["cash_sweep"]
            + monthly["delta_working_capital"]
        )
        monthly["sources_uses_gap"] = monthly["sources_total"] - monthly["uses_total"]

        metrics = self._compute_metrics(monthly)
        annual_summary = self._build_annual_summary(monthly)

        return ModelOutputs(
            monthly_results=monthly,
            annual_summary=annual_summary,
            metrics=metrics,
            asset_summaries=asset_summaries,
        )

    def _apply_panel_linkages(self) -> None:
        """Link panel assumptions across panel CAPEX, capacity (MW), and generation."""
        energy_cfg = self.assumptions.energy
        panel_count = float(getattr(energy_cfg, "panel_count", 0.0))
        panel_watt_dc = float(getattr(energy_cfg, "panel_watt_dc", 0.0))
        panel_unit_cost = float(getattr(energy_cfg, "panel_unit_cost", 0.0))
        dc_ac_ratio = max(1e-6, float(getattr(energy_cfg, "dc_ac_ratio", 1.25)))

        solar_panels_item = self._find_capex_item("solar panels")

        # Reverse direction support: if panel CAPEX and unit cost are known, derive panel count.
        if panel_count <= 0 and panel_unit_cost > 0 and solar_panels_item is not None:
            panel_count = max(0.0, float(getattr(solar_panels_item, "amount", 0.0))) / panel_unit_cost
            energy_cfg.panel_count = panel_count

        # Forward direction: panels -> DC MW -> AC MW (used by production model).
        if panel_count > 0 and panel_watt_dc > 0:
            capacity_mw_dc = panel_count * panel_watt_dc / 1_000_000
            energy_cfg.capacity_mw = capacity_mw_dc / dc_ac_ratio

        # Forward direction: panels -> panel CAPEX line item.
        if panel_count > 0 and panel_unit_cost > 0 and solar_panels_item is not None:
            solar_panels_item.amount = panel_count * panel_unit_cost

    def _find_capex_item(self, item_name: str):
        """Return the first CAPEX item matching ``item_name`` (case-insensitive)."""
        target = str(item_name).strip().lower()
        for item in self.assumptions.capex_items:
            if str(getattr(item, "name", "")).strip().lower() == target:
                return item
        return None

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

    @staticmethod
    def _escalated_series(initial: float, annual_rate: float, year_index: np.ndarray) -> np.ndarray:
        """Return a vector of annually-escalated values aligned to month-level year indices."""
        return initial * (1 + annual_rate) ** year_index

    def _start_month_mask(self, start_month: int) -> np.ndarray:
        """Return a 0/1 mask that activates values from ``start_month`` onward."""
        return (np.arange(len(self._timeline)) + 1 >= max(1, int(start_month))).astype(float)

    # ------------------------------------------------------------------
    # Energy
    def _compute_energy_profile(self) -> pd.Series:
        energy_cfg = self.assumptions.energy
        energy_cfg.validate()

        years = self._year_index()
        month_in_year = self._month_in_year()

        if getattr(energy_cfg, "energy_model_mode", "share_based") == "monthly_expected_mwh":
            expected = np.array(energy_cfg.monthly_expected_mwh, dtype=float)
            annual_growth = float(getattr(energy_cfg, "annual_production_growth_rate", 0.0))
            growth_factor = (1 + annual_growth) ** years
            monthly_output = expected[month_in_year] * growth_factor
            monthly_floor = float(getattr(energy_cfg, "monthly_min_mwh", 0.0))
            if monthly_floor > 0:
                monthly_output = np.maximum(monthly_output, monthly_floor)
            return pd.Series(monthly_output, index=self._timeline, name="energy_mwh")

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
        total_share = revenue_cfg.ppa.share_of_output + revenue_cfg.merchant.share_of_output
        if total_share > 1.0 + 1e-6:
            raise ValueError(
                "Revenue shares cannot exceed 100% of generation. "
                f"Current total is {total_share:.2%}."
            )

        ppa_rate = self._escalated_series(
            revenue_cfg.ppa.rate_curve.initial,
            revenue_cfg.ppa.rate_curve.annual_escalation,
            years,
        )
        merchant_rate = self._escalated_series(
            revenue_cfg.merchant.rate_curve.initial,
            revenue_cfg.merchant.rate_curve.annual_escalation,
            years,
        )
        rec_rate = self._escalated_series(
            revenue_cfg.rec.initial,
            revenue_cfg.rec.annual_escalation,
            years,
        )

        ppa_share = np.full(len(self._timeline), revenue_cfg.ppa.share_of_output, dtype=float)
        merchant_share = np.full(len(self._timeline), revenue_cfg.merchant.share_of_output, dtype=float)
        ppa_term_years = int(getattr(self.assumptions, "ppa_term_years", 0))
        if ppa_term_years > 0:
            expired = years >= ppa_term_years
            merchant_share[expired] = merchant_share[expired] + ppa_share[expired]
            ppa_share[expired] = 0.0

        hedge_floor_price = float(getattr(self.assumptions, "merchant_floor_price", 0.0))
        if hedge_floor_price > 0:
            merchant_rate = np.maximum(merchant_rate, hedge_floor_price)

        ppa_energy = energy.values * ppa_share
        merchant_energy = energy.values * merchant_share
        rec_energy = energy.values  # assume RECs on all generation

        revenue_df = pd.DataFrame(index=self._timeline)
        revenue_df["revenue_ppa"] = ppa_energy * ppa_rate
        revenue_df["revenue_merchant"] = merchant_energy * merchant_rate
        revenue_df["revenue_rec"] = rec_energy * rec_rate
        counterparty_haircut = max(0.0, min(0.95, float(getattr(self.assumptions, "ppa_counterparty_haircut", 0.0))))
        if counterparty_haircut > 0:
            revenue_df["revenue_ppa"] = revenue_df["revenue_ppa"] * (1 - counterparty_haircut)

        cod_month = max(1, int(getattr(self.assumptions, "cod_month", 1)))
        cod_mask = self._start_month_mask(cod_month)
        for col in revenue_df.columns:
            revenue_df[col] = revenue_df[col] * cod_mask
        return revenue_df

    # ------------------------------------------------------------------
    # Operating expenditure
    def _compute_fixed_opex(self, energy: pd.Series) -> pd.DataFrame:
        years = self._year_index()
        fixed = pd.DataFrame(index=self._timeline)
        energy_array = energy.reindex(self._timeline).fillna(0.0).to_numpy()

        for item in self.assumptions.fixed_opex:
            inflation_factor = self._escalated_series(1.0, item.inflation_rate, years)
            monthly_cost = np.zeros_like(energy_array, dtype=float)

            if getattr(item, "annual_cost", 0.0):
                annual_cost = item.annual_cost * inflation_factor
                monthly_cost += annual_cost / 12.0

            if getattr(item, "cost_per_mwh", 0.0):
                per_mwh_rate = item.cost_per_mwh * inflation_factor
                monthly_cost += energy_array * per_mwh_rate

            mask = self._start_month_mask(getattr(item, "start_month", 1))
            fixed[f"opex_fixed_{item.name.lower().replace(' ', '_')}"] = monthly_cost * mask

        return fixed

    def _compute_variable_opex(self, energy: pd.Series) -> pd.DataFrame:
        years = self._year_index()
        variable = pd.DataFrame(index=self._timeline)

        for item in self.assumptions.variable_opex:
            rate = self._escalated_series(item.cost_per_mwh, item.escalation_rate, years)
            cost = energy.values * rate
            mask = self._start_month_mask(item.start_month)
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
        method = str(getattr(assumptions, "terminal_method", "multiple")).lower()
        trailing_ebitda = monthly["ebitda"].iloc[-12:].mean() if len(monthly) >= 12 else monthly["ebitda"].iloc[-1]

        if method == "gordon":
            growth = float(getattr(self.assumptions, "terminal_growth_rate", 0.0))
            discount = assumptions.discount_rate
            if discount <= growth:
                enterprise_value = trailing_ebitda * assumptions.exit_multiple
            else:
                terminal_fcf = monthly["fcff"].iloc[-12:].sum() if len(monthly) >= 12 else monthly["fcff"].iloc[-1] * 12
                enterprise_value = terminal_fcf * (1 + growth) / (discount - growth)
        else:
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
        debt_service = monthly["debt_service"].replace(0, np.nan)
        dscr_series = (monthly["cfads"] / debt_service).replace([np.inf, -np.inf], np.nan).dropna()
        capacity_mw = max(self.assumptions.energy.capacity_mw, 1e-6)
        total_capex = float(monthly["capex"].sum())
        total_opex = float(monthly["total_opex"].sum())
        total_energy = float(monthly["energy_mwh"].sum())
        negative_equity = -float(monthly.loc[monthly["equity_cash_flow"] < 0, "equity_cash_flow"].sum())
        positive_equity = float(monthly.loc[monthly["equity_cash_flow"] > 0, "equity_cash_flow"].sum())
        equity_multiple = positive_equity / negative_equity if negative_equity > 0 else float("nan")
        llcr, plcr = self._compute_coverage_ratios(monthly, discount_rate)
        downside_npvs = self._compute_downside_npv_distribution(monthly, discount_rate)
        generation_sigma = max(0.0, float(getattr(self.assumptions, "generation_uncertainty", 0.10)))
        annual_energy = total_energy / max(1.0, self.assumptions.global_assumptions.forecast_months / 12.0)
        p50_energy = annual_energy
        p75_energy = annual_energy * (1 - 0.674 * generation_sigma)
        p90_energy = annual_energy * (1 - 1.282 * generation_sigma)
        covenant_breach_months = int((monthly["dscr"] < float(getattr(self.assumptions, "min_dscr_covenant", 1.20))).sum())

        project_irr = irr(project_cash_flow)
        equity_irr = irr(equity_cash_flow)
        investor_irr = irr(investor_cash_flow)
        owner_irr = irr(owner_cash_flow)
        payback_months = payback_period(project_cash_flow)

        metrics = {
            "project_npv": npv(discount_rate, project_cash_flow),
            "project_irr": project_irr if project_irr is not None else float("nan"),
            "equity_irr": equity_irr if equity_irr is not None else float("nan"),
            "investor_irr": investor_irr if investor_irr is not None else float("nan"),
            "owner_irr": owner_irr if owner_irr is not None else float("nan"),
            "project_payback_months": payback_months if payback_months is not None else float("nan"),
            "min_dscr": float(dscr_series.min()) if not dscr_series.empty else float("nan"),
            "avg_dscr": float(dscr_series.mean()) if not dscr_series.empty else float("nan"),
            "capex_per_mw": total_capex / capacity_mw,
            "opex_per_mwh": total_opex / total_energy if total_energy > 0 else float("nan"),
            "lcoe_proxy_per_mwh": (total_capex + total_opex) / total_energy if total_energy > 0 else float("nan"),
            "equity_multiple": equity_multiple,
            "llcr_proxy": llcr,
            "plcr_proxy": plcr,
            "downside_npv_p10": float(np.percentile(downside_npvs, 10)) if len(downside_npvs) else float("nan"),
            "downside_npv_p50": float(np.percentile(downside_npvs, 50)) if len(downside_npvs) else float("nan"),
            "downside_npv_p90": float(np.percentile(downside_npvs, 90)) if len(downside_npvs) else float("nan"),
            "annual_energy_p50_mwh": p50_energy,
            "annual_energy_p75_mwh": p75_energy,
            "annual_energy_p90_mwh": p90_energy,
            "covenant_breach_months": covenant_breach_months,
        }
        return metrics

    # ------------------------------------------------------------------
    def _build_annual_summary(self, monthly: pd.DataFrame) -> pd.DataFrame:
        annual = monthly.resample("YE").agg(
            {
                "revenue_total": "sum",
                "total_opex": "sum",
                "ebitda": "sum",
                "ebit": "sum",
                "tax_payment": "sum",
                "net_income": "sum",
                "cfads": "sum",
                "fcff": "sum",
                "equity_cash_flow": "sum",
                "capex": "sum",
                "depreciation": "sum",
                "debt_interest": "sum",
                "debt_principal": "sum",
                "debt_service": "sum",
                "debt_draw": "sum",
                "delta_working_capital": "sum",
                "energy_mwh": "sum",
                "itc_benefit": "sum",
                "arrangement_fees": "sum",
                "equity_contribution": "sum",
                "equity_distribution": "sum",
                "dsra_change": "sum",
                "major_maintenance_reserve_deposit": "sum",
                "inverter_reserve_deposit": "sum",
                "cash_sweep": "sum",
                "sources_total": "sum",
                "uses_total": "sum",
                "sources_uses_gap": "sum",
            }
        )
        annual["dscr"] = np.where(
            annual["debt_service"] > 0,
            annual["cfads"] / annual["debt_service"],
            np.nan,
        )
        annual["ebitda_margin"] = np.where(
            annual["revenue_total"] != 0,
            annual["ebitda"] / annual["revenue_total"],
            np.nan,
        )
        annual.index = annual.index.year
        return annual

    def _compute_itc_benefit(self, capex: pd.Series) -> pd.Series:
        itc_rate = max(0.0, min(1.0, float(getattr(self.assumptions, "itc_rate", 0.0))))
        itc_series = pd.Series(0.0, index=self._timeline)
        if itc_rate <= 0 or capex.sum() <= 0:
            return itc_series
        grant_month = int(getattr(self.assumptions, "itc_realization_month", 13))
        idx = max(0, min(len(itc_series) - 1, grant_month - 1))
        itc_series.iloc[idx] = float(capex.sum()) * itc_rate
        return itc_series

    def _compute_lifecycle_capex(self) -> pd.Series:
        lifecycle = pd.Series(0.0, index=self._timeline)
        replacement_year = int(getattr(self.assumptions, "lifecycle_replacement_year", 0))
        replacement_fraction = max(0.0, float(getattr(self.assumptions, "lifecycle_replacement_fraction", 0.0)))
        if replacement_year <= 0 or replacement_fraction <= 0:
            return lifecycle
        total_base_capex = sum(item.amount for item in self.assumptions.capex_items)
        replacement_month = replacement_year * 12
        idx = replacement_month - 1
        if 0 <= idx < len(lifecycle):
            lifecycle.iloc[idx] = total_base_capex * replacement_fraction
        return lifecycle

    def _compute_dsra_required(self, debt_service: pd.Series, reserve_months: int = 6) -> pd.Series:
        arr = debt_service.to_numpy(dtype=float)
        req = np.zeros_like(arr)
        n = len(arr)
        for i in range(n):
            end = min(n, i + reserve_months)
            req[i] = float(arr[i:end].mean()) if end > i else 0.0
        return pd.Series(req, index=self._timeline)

    def _compute_coverage_ratios(self, monthly: pd.DataFrame, discount_rate: float) -> Tuple[float, float]:
        periodic = (1 + discount_rate) ** (1 / 12) - 1
        cfads = monthly["cfads"].fillna(0.0).to_numpy()
        debt_balance = monthly["debt_balance"].fillna(0.0).to_numpy()
        debt_service = monthly["debt_service"].fillna(0.0).to_numpy()
        max_debt = float(np.max(debt_balance)) if debt_balance.size else 0.0
        if max_debt <= 0:
            return float("nan"), float("nan")
        loan_mask = debt_service > 0
        cfads_loan = cfads[loan_mask] if loan_mask.any() else np.array([])
        if cfads_loan.size == 0:
            return float("nan"), float("nan")
        llcr = npv(periodic, cfads_loan) / max_debt
        plcr = npv(periodic, cfads) / max_debt
        return float(llcr), float(plcr)

    def _compute_downside_npv_distribution(self, monthly: pd.DataFrame, discount_rate: float) -> List[float]:
        rng = np.random.default_rng(42)
        samples: List[float] = []
        for _ in range(120):
            revenue_mult = float(rng.normal(0.95, 0.05))
            opex_mult = float(rng.normal(1.05, 0.05))
            capex_mult = float(rng.normal(1.05, 0.07))
            stressed_ebit = (
                monthly["revenue_total"] * revenue_mult
                - monthly["total_opex"] * opex_mult
                - monthly["depreciation"]
            )
            stressed_fcff = (
                stressed_ebit * (1 - monthly["tax_rate"])
                + monthly["depreciation"]
                - monthly["capex"] * capex_mult
                - monthly["delta_working_capital"]
            )
            samples.append(float(npv(discount_rate, stressed_fcff.to_numpy())))
        return samples

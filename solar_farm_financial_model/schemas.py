"""Data structures for the Solar Farm Financial Model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Sequence


@dataclass
class RateCurve:
    """Represents a starting value with an annual escalation."""

    name: str
    initial: float
    annual_escalation: float = 0.0

    def value_for_year(self, year_index: int) -> float:
        """Return the value for a given (zero-indexed) year."""
        return self.initial * (1 + self.annual_escalation) ** year_index


@dataclass
class EnergyAssumptions:
    """Core production assumptions for the solar farm."""

    capacity_mw: float
    capacity_factor: float
    degradation_rate: float
    annual_hours: int = 8760
    energy_model_mode: str = "share_based"
    monthly_expected_mwh: Sequence[float] | None = None
    annual_production_growth_rate: float = 0.0
    monthly_min_mwh: float = 0.0
    panel_count: float = 0.0
    panel_watt_dc: float = 0.0
    panel_unit_cost: float = 0.0
    dc_ac_ratio: float = 1.25
    seasonality: Sequence[float] = field(
        default_factory=lambda: [
            0.05,
            0.05,
            0.05,
            0.10,
            0.12,
            0.17,
            0.17,
            0.10,
            0.05,
            0.04,
            0.05,
            0.05,
        ]
    )

    def validate(self) -> None:
        if self.monthly_min_mwh < 0:
            raise ValueError("Monthly minimum MWh cannot be negative.")
        if self.panel_count < 0:
            raise ValueError("panel_count cannot be negative.")
        if self.panel_watt_dc < 0:
            raise ValueError("panel_watt_dc cannot be negative.")
        if self.panel_unit_cost < 0:
            raise ValueError("panel_unit_cost cannot be negative.")
        if self.dc_ac_ratio <= 0:
            raise ValueError("dc_ac_ratio must be greater than zero.")

        if self.energy_model_mode == "monthly_expected_mwh":
            if self.monthly_expected_mwh is None:
                raise ValueError(
                    "monthly_expected_mwh must be provided when energy_model_mode is "
                    "'monthly_expected_mwh'."
                )
            if len(self.monthly_expected_mwh) != 12:
                raise ValueError("monthly_expected_mwh must contain 12 monthly values.")
            if any(value < 0 for value in self.monthly_expected_mwh):
                raise ValueError("monthly_expected_mwh values cannot be negative.")
            return

        total = sum(self.seasonality)
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                "Seasonality factors should sum to ~1.0, "
                f"but sum to {total:.2f}."
            )


@dataclass
class RevenueShare:
    """Defines how energy is monetised."""

    name: str
    share_of_output: float
    rate_curve: RateCurve


@dataclass
class RevenueAssumptions:
    """Revenue configuration across PPA, merchant, and RECs."""

    ppa: RevenueShare
    merchant: RevenueShare
    rec: RateCurve


@dataclass
class CapexItem:
    """A capital expenditure item with depreciation metadata."""

    name: str
    amount: float
    depreciation_years: int
    spend_profile: Sequence[float]
    method: str = "Straight-Line"
    opening_balance: float = 0.0
    depreciation_rate: float = 0.0
    service_month: int = 1

    def normalized_profile(self) -> List[float]:
        total = sum(self.spend_profile)
        if total == 0:
            raise ValueError(f"Capex profile for {self.name} cannot sum to 0")
        return [value / total for value in self.spend_profile]


@dataclass
class FixedOpexItem:
    """Fixed operating cost with optional annual and per-MWh components."""

    name: str
    annual_cost: float = 0.0
    inflation_rate: float = 0.0
    start_month: int = 1
    cost_per_mwh: float = 0.0


@dataclass
class VariableOpexItem:
    """Variable operating cost per MWh generated."""

    name: str
    cost_per_mwh: float
    escalation_rate: float
    start_month: int = 1


@dataclass
class DebtFacility:
    """Defines a single debt facility."""

    name: str
    principal: float
    interest_rate: float
    term_months: int
    interest_only_months: int
    start_month: int = 1


@dataclass
class ReceivableSettings:
    """Working capital assumptions for receivables and other current assets."""

    year: int
    days_in_year: int
    receivable_days: float
    prepaid_expense_days: float
    other_asset_days: float


@dataclass
class InventoryPayableSettings:
    """Working capital assumptions for inventory and accounts payable."""

    year: int
    days_in_year: int
    inventory_days: float
    accounts_payable_days: float


@dataclass
class TaxRateSchedule:
    """Explicit tax rate inputs that can vary by fiscal year."""

    year: int
    tax_rate: float


@dataclass
class DistributionSplit:
    """Equity ownership split between investor and owner."""

    investor_share: float
    owner_share: float

    def normalized(self) -> "DistributionSplit":
        total = self.investor_share + self.owner_share
        if total == 0:
            raise ValueError("Distribution split cannot be zero")
        return DistributionSplit(
            investor_share=self.investor_share / total,
            owner_share=self.owner_share / total,
        )


@dataclass
class TaxAssumptions:
    """Taxation rates for the project."""

    income_tax_rate: float
    capital_gains_tax_rate: float


@dataclass
class GlobalAssumptions:
    """Global settings for the forecast."""

    project_name: str
    start_date: date
    forecast_months: int
    include_terminal_value: bool
    exit_multiple: float
    discount_rate: float
    tax: TaxAssumptions
    distribution: DistributionSplit


@dataclass
class Assumptions:
    """Collection of all assumptions required for the model."""

    global_assumptions: GlobalAssumptions
    energy: EnergyAssumptions
    revenue: RevenueAssumptions
    capex_items: Sequence[CapexItem]
    fixed_opex: Sequence[FixedOpexItem]
    variable_opex: Sequence[VariableOpexItem]
    debt_facilities: Sequence[DebtFacility]
    receivable_settings: Sequence[ReceivableSettings] = field(default_factory=list)
    inventory_settings: Sequence[InventoryPayableSettings] = field(default_factory=list)
    tax_schedule: Sequence[TaxRateSchedule] = field(default_factory=list)
    terminal_growth_rate: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        """Convert assumptions to a serialisable dictionary."""
        return {
            "global": self.global_assumptions,
            "energy": self.energy,
            "revenue": self.revenue,
            "capex": list(self.capex_items),
            "fixed_opex": list(self.fixed_opex),
            "variable_opex": list(self.variable_opex),
            "debt": list(self.debt_facilities),
            "receivables": list(self.receivable_settings),
            "inventory": list(self.inventory_settings),
            "tax_schedule": list(self.tax_schedule),
            "terminal_growth_rate": self.terminal_growth_rate,
        }

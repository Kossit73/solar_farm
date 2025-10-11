"""Utilities for loading assumptions for the Solar Farm Financial Model."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from .schemas import (
    Assumptions,
    CapexItem,
    DebtFacility,
    DistributionSplit,
    EnergyAssumptions,
    FixedOpexItem,
    GlobalAssumptions,
    InventoryPayableSettings,
    RateCurve,
    ReceivableSettings,
    RevenueAssumptions,
    RevenueShare,
    TaxAssumptions,
    TaxRateSchedule,
    VariableOpexItem,
)

DEFAULT_EXCEL_PATH = Path("/mnt/data/Solar-Farmv2-vendor.xlsx")


def load_assumptions(excel_path: Optional[Path] = None) -> Assumptions:
    """Load model assumptions from an Excel workbook or fall back to defaults."""

    excel_path = excel_path or DEFAULT_EXCEL_PATH
    if excel_path.exists():
        loaded = _load_from_excel(excel_path)
        if loaded is not None:
            return loaded
    return _default_assumptions()


def _default_assumptions() -> Assumptions:
    """Return a curated set of assumptions derived from the provided workbook."""

    tax = TaxAssumptions(income_tax_rate=0.25, capital_gains_tax_rate=0.10)
    distribution = DistributionSplit(investor_share=0.95, owner_share=0.05)

    global_assumptions = GlobalAssumptions(
        project_name="Solar 123, LLC",
        start_date=date(2025, 1, 1),
        forecast_months=240,
        include_terminal_value=True,
        exit_multiple=5.0,
        discount_rate=0.10,
        tax=tax,
        distribution=distribution,
    )

    energy = EnergyAssumptions(
        capacity_mw=10.0,
        capacity_factor=0.145,
        degradation_rate=0.005,
    )

    ppa_curve = RateCurve(name="PPA", initial=160.0, annual_escalation=0.015)
    merchant_curve = RateCurve(name="Merchant", initial=56.58, annual_escalation=0.015)
    rec_curve = RateCurve(name="REC", initial=40.0, annual_escalation=0.02)

    revenue = RevenueAssumptions(
        ppa=RevenueShare(name="Power Purchase Agreement", share_of_output=0.90, rate_curve=ppa_curve),
        merchant=RevenueShare(name="Direct-to-Grid", share_of_output=0.10, rate_curve=merchant_curve),
        rec=rec_curve,
    )

    capex_items = [
        CapexItem("Solar Panels", 5_800_000, depreciation_years=20, spend_profile=[0.5, 0.5]),
        CapexItem("Mounting System", 1_600_000, depreciation_years=20, spend_profile=[0.5, 0.5]),
        CapexItem("Inverters", 1_776_000, depreciation_years=15, spend_profile=[0.5, 0.5]),
        CapexItem("Electrical & Wiring", 1_800_000, depreciation_years=20, spend_profile=[0.5, 0.5]),
        CapexItem("Land Acquisition", 200_000, depreciation_years=20, spend_profile=[0.5, 0.5]),
        CapexItem("Permitting & Compliance", 100_000, depreciation_years=10, spend_profile=[0.5, 0.5]),
        CapexItem("Construction Labour", 500_000, depreciation_years=5, spend_profile=[0.5, 0.5]),
        CapexItem("Contingency", 1_177_608, depreciation_years=5, spend_profile=[0.5, 0.5]),
    ]

    fixed_opex = [
        FixedOpexItem("Insurance", annual_cost=20_000, inflation_rate=0.02),
        FixedOpexItem("O&M Service Contract", annual_cost=6_000, inflation_rate=0.02),
        FixedOpexItem("Vegetation Management", annual_cost=10_000, inflation_rate=0.02),
        FixedOpexItem("General & Administrative", annual_cost=100_000, inflation_rate=0.03),
        FixedOpexItem("Sales & Marketing", annual_cost=8_500, inflation_rate=0.02),
        FixedOpexItem("Research & Development", annual_cost=7_650, inflation_rate=0.02),
    ]

    variable_opex = [
        VariableOpexItem("O&M per MWh", cost_per_mwh=2.00, escalation_rate=0.02),
        VariableOpexItem("Grid Fees", cost_per_mwh=1.50, escalation_rate=0.02),
        VariableOpexItem("Market Participation", cost_per_mwh=0.10, escalation_rate=0.02),
        VariableOpexItem("Consumables", cost_per_mwh=0.40, escalation_rate=0.02),
        VariableOpexItem("REC Tracking", cost_per_mwh=0.05, escalation_rate=0.02),
    ]

    debt_facilities = [
        DebtFacility(
            name="Construction Loan",
            principal=2_000_000,
            interest_rate=0.07,
            term_months=240,
            interest_only_months=12,
            start_month=1,
        )
    ]

    receivable_settings = [
        ReceivableSettings(
            year=2025,
            days_in_year=365,
            receivable_days=45,
            prepaid_expense_days=30,
            other_asset_days=5,
        )
    ]

    inventory_settings = [
        InventoryPayableSettings(
            year=2025,
            days_in_year=365,
            inventory_days=50,
            accounts_payable_days=45,
        )
    ]

    tax_schedule = [TaxRateSchedule(year=2025, tax_rate=tax.income_tax_rate)]

    return Assumptions(
        global_assumptions=global_assumptions,
        energy=energy,
        revenue=revenue,
        capex_items=capex_items,
        fixed_opex=fixed_opex,
        variable_opex=variable_opex,
        debt_facilities=debt_facilities,
        receivable_settings=receivable_settings,
        inventory_settings=inventory_settings,
        tax_schedule=tax_schedule,
        terminal_growth_rate=0.02,
    )


def _load_from_excel(excel_path: Path) -> Optional[Assumptions]:
    """Attempt to hydrate assumptions from an Excel workbook."""

    try:
        workbook = pd.ExcelFile(excel_path)
    except Exception:
        return None

    try:
        global_assumptions = _parse_global_assumptions(workbook)
        energy = _parse_energy_assumptions(workbook)
        revenue = _parse_revenue_assumptions(workbook)
        capex_items = _parse_capex(workbook)
        fixed_opex, variable_opex = _parse_opex(workbook)
        debt_facilities = _parse_debt(workbook)
    except Exception:
        return None

    receivable_settings = [
        ReceivableSettings(
            year=global_assumptions.start_date.year,
            days_in_year=365,
            receivable_days=45,
            prepaid_expense_days=30,
            other_asset_days=5,
        )
    ]
    inventory_settings = [
        InventoryPayableSettings(
            year=global_assumptions.start_date.year,
            days_in_year=365,
            inventory_days=50,
            accounts_payable_days=45,
        )
    ]
    tax_schedule = [TaxRateSchedule(year=global_assumptions.start_date.year, tax_rate=global_assumptions.tax.income_tax_rate)]

    return Assumptions(
        global_assumptions=global_assumptions,
        energy=energy,
        revenue=revenue,
        capex_items=capex_items,
        fixed_opex=fixed_opex,
        variable_opex=variable_opex,
        debt_facilities=debt_facilities,
        receivable_settings=receivable_settings,
        inventory_settings=inventory_settings,
        tax_schedule=tax_schedule,
        terminal_growth_rate=0.02,
    )


def _parse_global_assumptions(workbook: pd.ExcelFile) -> GlobalAssumptions:
    df = workbook.parse("global Control", header=None)
    df = df.dropna(how="all").reset_index(drop=True)
    mapping = {str(row[0]).strip(): row[1] for _, row in df.iterrows() if row[0] == row[0]}

    project_name = str(mapping.get("Company Name", "Solar Farm"))
    start_date = pd.to_datetime(mapping.get("First Month of forecast", date.today())).date()
    forecast_months = int(mapping.get("Forecast Period Length (in months)", 240))
    include_terminal = str(mapping.get("Include Terminal Value?", "Yes")).lower().startswith("y")
    exit_multiple = float(mapping.get("Trailing 12-month EBITDA Multiple", 5.0))
    discount_rate = float(mapping.get("Project DCF", 0.10))

    tax = TaxAssumptions(
        income_tax_rate=float(mapping.get("Income Tax Rate", 0.25)),
        capital_gains_tax_rate=float(mapping.get("Long-Term Capital Gains Tax Rate", 0.10)),
    )
    distribution = DistributionSplit(
        investor_share=float(mapping.get("% Share for Investors", 0.95)),
        owner_share=float(mapping.get("Remaining % for Owners", 0.05)),
    )

    return GlobalAssumptions(
        project_name=project_name,
        start_date=start_date,
        forecast_months=forecast_months,
        include_terminal_value=include_terminal,
        exit_multiple=exit_multiple,
        discount_rate=discount_rate,
        tax=tax,
        distribution=distribution,
    )


def _parse_energy_assumptions(workbook: pd.ExcelFile) -> EnergyAssumptions:
    df = workbook.parse("Deployment Cost", header=None)
    df = df.dropna(how="all").reset_index(drop=True)
    mapping = {str(row[0]).strip(): row[1] for _, row in df.iterrows() if row[0] == row[0]}

    capacity_mw = float(mapping.get("Farm Total Capacity (MW)", 10.0))
    capacity_factor = float(mapping.get("Capacity Factor", 0.145))
    if capacity_factor > 1:
        capacity_factor /= 100.0
    degradation_rate = float(mapping.get("Degradation Rate", 0.005))
    if degradation_rate > 1:
        degradation_rate /= 100.0

    seasonality_sheet = "Seasonality"
    if seasonality_sheet in workbook.sheet_names:
        seasonality_df = workbook.parse(seasonality_sheet)
        if {"% of Expected Annual Output"}.issubset(set(seasonality_df.columns)):
            seasonality = seasonality_df["% of Expected Annual Output"].dropna().tolist()
        else:
            seasonality = None
    else:
        seasonality = None

    energy = EnergyAssumptions(
        capacity_mw=capacity_mw,
        capacity_factor=capacity_factor,
        degradation_rate=degradation_rate,
        seasonality=seasonality or EnergyAssumptions(1, 1, 0).seasonality,
    )
    energy.validate()
    return energy


def _parse_revenue_assumptions(workbook: pd.ExcelFile) -> RevenueAssumptions:
    df = workbook.parse("Revenue")
    df = df.rename(columns={df.columns[0]: "Metric"}).dropna(subset=["Metric"])
    df["Metric"] = df["Metric"].astype(str).str.strip()

    def _find(metric: str, default: float) -> float:
        result = df.loc[df["Metric"].str.startswith(metric), df.columns[1]]
        if not result.empty:
            value = float(result.iloc[0])
            if value > 1 and "share" in metric.lower():
                return value / 100.0
            return value
        return default

    ppa_share = _find("% of Power Sold via PPA", 0.9)
    ppa_rate = _find("Agreed Rate per MWh", 160.0)
    ppa_escalation = _find("Annual Increase", 0.015)
    merchant_share = _find("% of Power Sold to Grid", 0.1)
    merchant_rate = _find("Merchant", 56.58)
    merchant_escalation = _find("Merchant Annual Increase", 0.015)
    rec_price = _find("REC Price/MWh", 40.0)
    rec_escalation = _find("REC Annual Increase", 0.02)

    ppa_curve = RateCurve("PPA", ppa_rate, ppa_escalation)
    merchant_curve = RateCurve("Merchant", merchant_rate, merchant_escalation)
    rec_curve = RateCurve("REC", rec_price, rec_escalation)

    return RevenueAssumptions(
        ppa=RevenueShare("Power Purchase Agreement", ppa_share, ppa_curve),
        merchant=RevenueShare("Direct-to-Grid", merchant_share, merchant_curve),
        rec=rec_curve,
    )


def _parse_capex(workbook: pd.ExcelFile):
    df = workbook.parse("Deployment Cost")
    df = df.rename(columns={df.columns[0]: "Item"}).dropna(subset=["Item"])
    df["Item"] = df["Item"].astype(str).str.strip()

    capex_items = []
    for _, row in df.iterrows():
        item = row["Item"]
        if not item or not isinstance(row[1], (int, float)):
            continue
        amount = float(row[1])
        if amount <= 0:
            continue
        if item.lower().startswith("total") or item.lower().startswith("component"):
            continue
        spend_profile = [0.5, 0.5]
        depreciation_years = 20
        if "inverter" in item.lower():
            depreciation_years = 15
        elif "labor" in item.lower():
            depreciation_years = 5
        elif "contingency" in item.lower() or "permit" in item.lower():
            depreciation_years = 5
        capex_items.append(
            CapexItem(item, amount, depreciation_years=depreciation_years, spend_profile=spend_profile)
        )
    return capex_items


def _parse_opex(workbook: pd.ExcelFile):
    df = workbook.parse("OPEX", header=None)
    df = df.dropna(how="all").reset_index(drop=True)
    mapping = {str(row[0]).strip(): row[1] for _, row in df.iterrows() if row[0] == row[0]}

    fixed_items = [
        ("Insurance", mapping.get("Insurance", 20_000)),
        ("Operation / Maintenance (O&M) Service Contracts", mapping.get("Operation / Maintenance (O&M) Service Contracts", 6_000)),
        ("Vegetation Management", mapping.get("Vegetation Management", 10_000)),
        ("General & Administrative", mapping.get("G&A Item 1", 100_000)),
        ("Sales & Marketing", mapping.get("S&M Item 1", 8_500)),
        ("Research & Development", mapping.get("R&D Item 1", 7_650)),
    ]
    fixed_opex = [
        FixedOpexItem(name, float(value) if value is not None else 0.0, inflation_rate=0.02)
        for name, value in fixed_items
    ]

    variable_items = [
        ("O&M per MWh", mapping.get("COGS O&M Costs per MWh Generated", 2.0)),
        ("Grid Fees", mapping.get("COGS Grid Fees per MWh Sold", 1.5)),
        ("Market Participation", mapping.get("COGS Market Participation Fees per MWh Sold", 0.1)),
        ("Consumables", mapping.get("COGS Incremental Maintenance or Consumables Linked to Output", 0.4)),
        ("REC Tracking", mapping.get("COGS REC Tracking Fees per Generated", 0.05)),
    ]
    variable_opex = [
        VariableOpexItem(name, float(value) if value is not None else 0.0, escalation_rate=0.02)
        for name, value in variable_items
    ]

    return fixed_opex, variable_opex


def _parse_debt(workbook: pd.ExcelFile):
    df = workbook.parse("Loan 1", header=None)
    df = df.dropna(how="all").reset_index(drop=True)
    mapping = {str(row[0]).strip(): row[1] for _, row in df.iterrows() if row[0] == row[0]}

    principal = float(mapping.get("Loan Amount", mapping.get("Total Debt (all loans)", 2_000_000)))
    interest_rate = float(mapping.get("Interest Rate", 0.07))
    term_years = float(mapping.get("Term of Loan:", 20))
    interest_only = int(mapping.get("I/O Period:", 12))

    return [
        DebtFacility(
            name="Construction Loan",
            principal=principal,
            interest_rate=interest_rate,
            term_months=int(term_years * 12),
            interest_only_months=interest_only,
            start_month=1,
        )
    ]

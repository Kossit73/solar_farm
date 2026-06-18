from __future__ import annotations

import pandas as pd
from openpyxl import Workbook

from solar_farm_financial_model.data_loader import load_assumptions
from solar_farm_financial_model.excel_reporting import append_comprehensive_workbook_sheets
from solar_farm_financial_model.input_parsing import (
    CALENDAR_HOURS_PER_YEAR,
    apply_energy_input_mode,
    build_opex_items,
)
import solar_farm_financial_model.model as model_module
from solar_farm_financial_model.model import SolarFarmFinancialModel, capex_item_schedule
from solar_farm_financial_model.schemas import EnergyAssumptions, TaxRateSchedule


def test_build_opex_items_maps_fixed_cost_to_annual_cost() -> None:
    fixed_items, variable_items = build_opex_items(
        [
            {
                "name": "Insurance",
                "fixed_cost": 20_000.0,
                "variable_cost": 1.5,
                "inflation_rate": 0.02,
            }
        ],
        0.02,
    )

    assert len(fixed_items) == 1
    assert fixed_items[0].annual_cost == 20_000.0
    assert fixed_items[0].cost_per_mwh == 0.0
    assert len(variable_items) == 1
    assert variable_items[0].cost_per_mwh == 1.5


def test_land_acquisition_default_is_non_depreciable() -> None:
    assumptions = load_assumptions()
    land_item = next(item for item in assumptions.capex_items if item.name == "Land Acquisition")
    timeline = pd.date_range(assumptions.global_assumptions.start_date, periods=24, freq="MS")

    _, depreciation, _, _ = capex_item_schedule(land_item, timeline)

    assert land_item.depreciation_years == 0
    assert float(depreciation.sum()) == 0.0


def test_tax_schedule_uses_base_rate_until_effective_year() -> None:
    assumptions = load_assumptions()
    assumptions.global_assumptions.tax.income_tax_rate = 0.25
    assumptions.tax_schedule = [TaxRateSchedule(year=2027, tax_rate=0.30)]

    model = SolarFarmFinancialModel(assumptions)
    tax_rates = model._tax_rate_series()

    assert tax_rates.loc[pd.Timestamp("2025-01-01")] == 0.25
    assert tax_rates.loc[pd.Timestamp("2026-12-01")] == 0.25
    assert tax_rates.loc[pd.Timestamp("2027-01-01")] == 0.30


def test_zero_irr_and_payback_are_preserved(monkeypatch) -> None:
    assumptions = load_assumptions()
    model = SolarFarmFinancialModel(assumptions)
    index = model._timeline[:2]
    monthly = pd.DataFrame(
        {
            "fcff": [0.0, 0.0],
            "equity_cash_flow": [0.0, 0.0],
            "investor_cash_flow": [0.0, 0.0],
            "owner_cash_flow": [0.0, 0.0],
            "debt_service": [0.0, 0.0],
            "cfads": [0.0, 0.0],
            "capex": [0.0, 0.0],
            "total_opex": [0.0, 0.0],
            "energy_mwh": [0.0, 0.0],
            "dscr": [float("nan"), float("nan")],
            "debt_balance": [0.0, 0.0],
                "revenue_total": [0.0, 0.0],
                "depreciation": [0.0, 0.0],
                "tax_rate": [0.25, 0.25],
                "delta_working_capital": [0.0, 0.0],
                "discount_rate_monthly": [0.0, 0.0],
                "fcff_present_value": [0.0, 0.0],
                "risk_total_premium": [0.0, 0.0],
            },
            index=index,
        )

    monkeypatch.setattr(model_module, "irr", lambda _: 0.0)
    monkeypatch.setattr(model_module, "payback_period", lambda _: 0)

    metrics = model._compute_metrics(monthly)

    assert metrics["project_irr"] == 0.0
    assert metrics["equity_irr"] == 0.0
    assert metrics["investor_irr"] == 0.0
    assert metrics["owner_irr"] == 0.0
    assert metrics["project_payback_months"] == 0


def test_apply_energy_input_mode_resource_hours_derives_capacity_factor() -> None:
    energy = EnergyAssumptions(capacity_mw=10.0, capacity_factor=0.145, degradation_rate=0.005)

    apply_energy_input_mode(
        energy,
        "resource_hours",
        capacity_factor=0.145,
        annual_resource_hours=2500.0,
        monthly_generation_rows=[],
    )

    assert energy.annual_hours == int(CALENDAR_HOURS_PER_YEAR)
    assert energy.capacity_factor == 2500.0 / CALENDAR_HOURS_PER_YEAR
    assert getattr(energy, "annual_resource_hours_input") == 2500.0


def test_apply_energy_input_mode_monthly_expected_derives_capacity_factor() -> None:
    energy = EnergyAssumptions(capacity_mw=5.0, capacity_factor=0.145, degradation_rate=0.005)
    monthly_generation_rows = [{"month": str(month), "expected_mwh": 365.0} for month in range(1, 13)]

    apply_energy_input_mode(
        energy,
        "monthly_expected_mwh",
        capacity_factor=0.145,
        annual_resource_hours=0.0,
        monthly_generation_rows=monthly_generation_rows,
    )

    assert energy.energy_model_mode == "monthly_expected_mwh"
    assert list(energy.monthly_expected_mwh or []) == [365.0] * 12
    assert energy.capacity_factor == (365.0 * 12) / (5.0 * CALENDAR_HOURS_PER_YEAR)


def test_comprehensive_workbook_export_includes_full_solar_sheet_set() -> None:
    assumptions = load_assumptions()
    outputs = SolarFarmFinancialModel(assumptions).run()
    workbook = Workbook()

    append_comprehensive_workbook_sheets(
        workbook,
        outputs,
        assumptions,
        {
            "labour_schedule": pd.DataFrame(
                [
                    {
                        "role": "Operations Technician",
                        "monthly_cost_per_fte": 4500.0,
                        "Year 1": 2.0,
                        "Year 2": 2.1,
                    }
                ]
            )
        },
    )

    expected_sheets = {
        "01_Monthly_Financials",
        "02_Annual_Financials",
        "03_Annual_Performance",
        "04_Annual_Position",
        "05_Annual_Cash_Flow",
        "06_Revenue_Schedule",
        "07_OPEX_Schedule",
        "08_Working_Capital",
        "09_CAPEX_Depreciation",
        "10_Financing_Cash",
        "11_Debt_Schedule",
        "12_Asset_Schedule",
        "13_Global_Assumptions",
        "14_Energy_Assumptions",
        "15_Revenue_Assumptns",
        "16_CAPEX_Assumptions",
        "17_Fixed_OPEX_Assump",
        "18_Var_OPEX_Assump",
        "19_Receivables_WC",
        "20_Inventory_WC",
        "21_Tax_Schedule",
        "22_Risk_Schedule",
        "24_Labour_Schedule",
    }

    assert expected_sheets.issubset(set(workbook.sheetnames))

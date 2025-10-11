"""Interactive Streamlit application for the Solar Farm Financial Model."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from solar_farm_financial_model.data_loader import load_assumptions
from solar_farm_financial_model.model import ModelOutputs, SolarFarmFinancialModel
from solar_farm_financial_model.reporting import build_summary_report
from solar_farm_financial_model.schemas import Assumptions


MetricLabels = {
    "project_npv": "Project NPV",
    "project_irr": "Project IRR",
    "equity_irr": "Equity IRR",
    "investor_irr": "Investor IRR",
    "owner_irr": "Owner IRR",
    "project_payback_months": "Payback (months)",
}


@st.cache_data(show_spinner=False)
def _run_model(
    excel_bytes: bytes | None, override_items: Tuple[Tuple[str, float | bool], ...]
) -> Tuple[ModelOutputs, Dict[str, pd.DataFrame], Assumptions]:
    """Execute the financial model with optional overrides and return outputs."""

    overrides = dict(override_items)
    temp_path: Path | None = None

    if excel_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(excel_bytes)
            temp_path = Path(tmp.name)

    try:
        assumptions = load_assumptions(temp_path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()

    # Apply overrides captured from the UI
    assumptions.global_assumptions.discount_rate = float(overrides["discount_rate"])
    assumptions.global_assumptions.exit_multiple = float(overrides["exit_multiple"])
    assumptions.global_assumptions.include_terminal_value = bool(overrides["include_terminal"])
    assumptions.terminal_growth_rate = float(overrides["terminal_growth_rate"])

    energy = assumptions.energy
    energy.capacity_mw = float(overrides["capacity_mw"])
    energy.capacity_factor = float(overrides["capacity_factor"])
    energy.degradation_rate = float(overrides["degradation_rate"])

    revenue = assumptions.revenue
    ppa_share = float(overrides["ppa_share"])
    merchant_share = max(0.0, min(1.0, 1.0 - ppa_share))
    revenue.ppa.share_of_output = ppa_share
    revenue.merchant.share_of_output = merchant_share

    revenue.ppa.rate_curve.initial = float(overrides["ppa_rate"])
    revenue.ppa.rate_curve.annual_escalation = float(overrides["ppa_escalation"])

    revenue.merchant.rate_curve.initial = float(overrides["merchant_rate"])
    revenue.merchant.rate_curve.annual_escalation = float(overrides["merchant_escalation"])

    revenue.rec.initial = float(overrides["rec_rate"])
    revenue.rec.annual_escalation = float(overrides["rec_escalation"])

    model = SolarFarmFinancialModel(assumptions)
    outputs = model.run()
    summary_tables = build_summary_report(outputs)
    return outputs, summary_tables, assumptions


def _format_currency(value: float) -> str:
    return f"$ {value:,.0f}"


def _format_percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_metric(name: str, value: float) -> str:
    if name.endswith("irr") and pd.notna(value):
        return _format_percentage(value)
    if "payback" in name and pd.notna(value):
        return f"{value:.0f} months"
    if pd.notna(value):
        return _format_currency(value)
    return "N/A"


def _downloadable_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=True).encode("utf-8")


st.set_page_config(page_title="Solar Farm Financial Model", layout="wide")


GenericTableRow = Dict[str, object]


_TABLE_TYPE_LABELS = {"number": "Number", "percent": "Percent", "boolean": "Boolean"}


CORE_ASSUMPTION_DEFAULTS: List[GenericTableRow] = [
    {"label": "Discount Rate", "value": 0.10, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.01},
    {"label": "Exit EBITDA Multiple", "value": 5.0, "input_type": "number", "min": 0.0, "step": 0.5},
    {"label": "Include Terminal Value", "value": True, "input_type": "boolean"},
    {"label": "Terminal Growth Rate", "value": 0.02, "input_type": "percent", "min": 0.0, "max": 0.25, "step": 0.005},
]


GLOBAL_DEFAULTS: List[GenericTableRow] = [
    {"label": "Income Tax Rate", "value": 0.25, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.01},
    {"label": "Capital Gains Tax Rate", "value": 0.10, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.01},
    {"label": "Investor Share", "value": 0.95, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.01},
    {"label": "Owner Share", "value": 0.05, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.01},
]


ENERGY_DEFAULTS: List[GenericTableRow] = [
    {"label": "Capacity (MW)", "value": 10.0, "input_type": "number", "min": 0.0, "step": 0.5},
    {"label": "Capacity Factor", "value": 0.145, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.005},
    {"label": "Annual Degradation", "value": 0.005, "input_type": "percent", "min": 0.0, "max": 0.10, "step": 0.001},
]


REVENUE_DEFAULTS: List[GenericTableRow] = [
    {"label": "Share of Output via PPA", "value": 0.90, "input_type": "percent", "min": 0.0, "max": 1.0, "step": 0.05},
    {"label": "Year 1 PPA Rate ($/MWh)", "value": 160.0, "input_type": "number", "min": 0.0, "step": 5.0},
    {"label": "PPA Annual Escalation", "value": 0.015, "input_type": "number", "min": 0.0, "max": 0.10, "step": 0.005, "format": "%.3f"},
    {"label": "Year 1 Merchant Rate ($/MWh)", "value": 56.58, "input_type": "number", "min": 0.0, "step": 1.0},
    {"label": "Merchant Annual Escalation", "value": 0.015, "input_type": "number", "min": 0.0, "max": 0.10, "step": 0.005, "format": "%.3f"},
    {"label": "Year 1 REC Price ($/MWh)", "value": 40.0, "input_type": "number", "min": 0.0, "step": 1.0},
    {"label": "REC Annual Escalation", "value": 0.02, "input_type": "number", "min": 0.0, "max": 0.10, "step": 0.005, "format": "%.3f"},
]


LABOUR_DEFAULTS = [
    {"role": "Production Manager", "annual_cost": 1_000.0},
    {"role": "Production Operators", "annual_cost": 1_000.0},
    {"role": "Process Engineer", "annual_cost": 1_000.0},
    {"role": "Process Technician", "annual_cost": 1_000.0},
]


FIXED_VARIABLE_DEFAULTS = [
    {"product": "Tablets", "fixed_cost": 0.0, "variable_cost": 0.05},
    {"product": "Capsules", "fixed_cost": 0.0, "variable_cost": 0.065},
    {"product": "Liquid", "fixed_cost": 0.0, "variable_cost": 1.525},
    {"product": "Ointment", "fixed_cost": 0.0, "variable_cost": 3.026},
]


ACCOUNTS_RECEIVABLE_DEFAULTS = [
    {"year": 2024, "days_in_year": 366, "receivable_days": 45, "prepaid_expense_days": 30, "other_asset_days": 5},
    {"year": 2025, "days_in_year": 365, "receivable_days": 45, "prepaid_expense_days": 30, "other_asset_days": 5},
]


INVENTORY_PAYABLE_DEFAULTS = [
    {"year": 2024, "days_in_year": 366, "inventory_days": 50, "accounts_payable_days": 45},
    {"year": 2025, "days_in_year": 365, "inventory_days": 50, "accounts_payable_days": 45},
]


FIXED_ASSET_DEFAULTS = [
    {
        "asset_type": "Land",
        "method": "Straight-Line",
        "year": 2024,
        "acquisition": 1_000_000.0,
        "asset_life": 20.0,
        "net_book_value": 1_000_000.0,
        "depreciation_rate": 0.05,
        "total_asset_cost": 1_000_000.0,
        "total_depreciation": 0.0,
        "cumulative_depreciation": 0.0,
        "ending_book_value": 1_000_000.0,
    },
    {
        "asset_type": "GMP Facility",
        "method": "Straight-Line",
        "year": 2024,
        "acquisition": 2_500_000.0,
        "asset_life": 15.0,
        "net_book_value": 2_500_000.0,
        "depreciation_rate": 0.067,
        "total_asset_cost": 2_500_000.0,
        "total_depreciation": 0.0,
        "cumulative_depreciation": 0.0,
        "ending_book_value": 2_500_000.0,
    },
]


def _ensure_table_state(state_key: str, defaults: List[GenericTableRow]) -> None:
    if state_key not in st.session_state:
        st.session_state[state_key] = copy.deepcopy(defaults)


def _render_label_value_table(title: str, state_key: str, defaults: List[GenericTableRow]) -> None:
    _ensure_table_state(state_key, defaults)
    st.markdown(f"### {title}")
    rows = st.session_state[state_key]
    updated_rows: List[GenericTableRow] = []

    for idx, row in enumerate(rows):
        with st.container(border=True):
            col_label, col_type, col_value, col_remove = st.columns([3, 1.5, 2, 1])
            label = col_label.text_input(
                "Label",
                value=str(row.get("label", "")),
                key=f"{state_key}_label_{idx}",
                label_visibility="collapsed",
            )

            type_options = list(_TABLE_TYPE_LABELS.keys())
            current_type = str(row.get("input_type", "number"))
            if current_type not in type_options:
                current_type = "number"
            type_index = type_options.index(current_type)
            input_type = col_type.selectbox(
                "Type",
                type_options,
                index=type_index,
                key=f"{state_key}_type_{idx}",
                format_func=lambda opt: _TABLE_TYPE_LABELS[opt],
                label_visibility="collapsed",
            )

            value_key = f"{state_key}_value_{idx}"
            if input_type == "boolean":
                value = col_value.checkbox(
                    "Value",
                    value=bool(row.get("value", False)),
                    key=value_key,
                    label_visibility="collapsed",
                )
            else:
                number_kwargs: Dict[str, float | str] = {}
                if row.get("min") is not None:
                    number_kwargs["min_value"] = float(row["min"])
                if row.get("max") is not None:
                    number_kwargs["max_value"] = float(row["max"])
                step = float(row.get("step", 0.01 if input_type == "percent" else 1.0))
                number_kwargs["step"] = step
                if row.get("format"):
                    number_kwargs["format"] = str(row["format"])
                value = col_value.number_input(
                    "Value",
                    value=float(row.get("value", 0.0)),
                    key=value_key,
                    label_visibility="collapsed",
                    **number_kwargs,
                )

            remove_clicked = col_remove.button("Remove", key=f"{state_key}_remove_{idx}")
        if remove_clicked:
            continue
        updated_rows.append(
            {
                "label": label,
                "input_type": input_type,
                "value": value,
                **{k: v for k, v in row.items() if k not in {"label", "input_type", "value"}},
            }
        )

    st.session_state[state_key] = updated_rows

    if st.button(f"Add {title} Row", key=f"{state_key}_add"):
        st.session_state[state_key].append({"label": "New Item", "input_type": "number", "value": 0.0, "step": 0.1})


def _render_projection_horizon_section() -> None:
    st.markdown("### Projection Horizon")
    if "projection_start_year" not in st.session_state:
        st.session_state["projection_start_year"] = 2024
    if "projection_end_year" not in st.session_state:
        st.session_state["projection_end_year"] = 2033

    start_year_options = list(range(2020, 2051))
    start_year = st.selectbox(
        "Start Year",
        options=start_year_options,
        index=start_year_options.index(st.session_state["projection_start_year"]),
        key="projection_start_year",
        help="Select the first year in the forecast horizon.",
    )
    end_year_options = list(range(start_year + 1, start_year + 21))
    if st.session_state["projection_end_year"] not in end_year_options:
        st.session_state["projection_end_year"] = end_year_options[-1]
    st.selectbox(
        "End Year",
        options=end_year_options,
        index=end_year_options.index(st.session_state["projection_end_year"]),
        key="projection_end_year",
        help="Choose the final year for the projection horizon (up to 20 years).",
    )


def _render_labour_structure_section() -> None:
    state_key = "labour_structure"
    if state_key not in st.session_state:
        st.session_state[state_key] = copy.deepcopy(LABOUR_DEFAULTS)

    st.markdown("### Direct Labour Structure")
    rows = st.session_state[state_key]
    updated_rows: List[Dict[str, object]] = []
    for idx, row in enumerate(rows):
        with st.container(border=True):
            col_role, col_cost, col_remove = st.columns([3, 2, 1])
            role = col_role.text_input(
                "Role",
                value=str(row.get("role", "")),
                key=f"{state_key}_role_{idx}",
                label_visibility="collapsed",
            )
            annual_cost = col_cost.number_input(
                "Annual Cost",
                value=float(row.get("annual_cost", 0.0)),
                key=f"{state_key}_cost_{idx}",
                step=100.0,
                min_value=0.0,
                label_visibility="collapsed",
            )
            remove_clicked = col_remove.button("Remove", key=f"{state_key}_remove_{idx}")
        if remove_clicked:
            continue
        updated_rows.append({"role": role, "annual_cost": annual_cost})
    st.session_state[state_key] = updated_rows

    if st.button("Add Labour Role", key=f"{state_key}_add"):
        st.session_state[state_key].append({"role": "New Role", "annual_cost": 0.0})


def _render_fixed_variable_costs_section() -> None:
    state_key = "fixed_variable_costs"
    if state_key not in st.session_state:
        st.session_state[state_key] = copy.deepcopy(FIXED_VARIABLE_DEFAULTS)

    st.markdown("### Fixed & Variable Costs Input Table")
    rows = st.session_state[state_key]
    updated_rows: List[Dict[str, object]] = []
    for idx, row in enumerate(rows):
        with st.container(border=True):
            col_product, col_fixed, col_variable, col_remove = st.columns([3, 2, 2, 1])
            product = col_product.text_input(
                "Product",
                value=str(row.get("product", "")),
                key=f"{state_key}_product_{idx}",
                label_visibility="collapsed",
            )
            fixed_cost = col_fixed.number_input(
                "Fixed Cost",
                value=float(row.get("fixed_cost", 0.0)),
                key=f"{state_key}_fixed_{idx}",
                min_value=0.0,
                step=0.01,
                label_visibility="collapsed",
            )
            variable_cost = col_variable.number_input(
                "Variable Cost",
                value=float(row.get("variable_cost", 0.0)),
                key=f"{state_key}_variable_{idx}",
                min_value=0.0,
                step=0.01,
                label_visibility="collapsed",
            )
            remove_clicked = col_remove.button("Remove", key=f"{state_key}_remove_{idx}")
        if remove_clicked:
            continue
        updated_rows.append({"product": product, "fixed_cost": fixed_cost, "variable_cost": variable_cost})
    st.session_state[state_key] = updated_rows

    if st.button("Add Product Cost", key=f"{state_key}_add"):
        st.session_state[state_key].append({"product": "New Product", "fixed_cost": 0.0, "variable_cost": 0.0})


def _render_accounts_receivable_section() -> None:
    state_key = "accounts_receivable"
    if state_key not in st.session_state:
        st.session_state[state_key] = copy.deepcopy(ACCOUNTS_RECEIVABLE_DEFAULTS)

    st.markdown("### Accounts Receivable Input Table")
    rows = st.session_state[state_key]
    updated_rows: List[Dict[str, object]] = []
    year_options = list(range(2024, 2051))
    for idx, row in enumerate(rows):
        with st.container(border=True):
            col_year, col_days, col_ar_days, col_prepaid, col_other, col_remove = st.columns([1.2, 1, 1, 1, 1, 0.8])
            current_year = int(row.get("year", year_options[0]))
            if current_year not in year_options:
                current_year = year_options[0]
            year = col_year.selectbox(
                "Receivable year",
                options=year_options,
                index=year_options.index(current_year),
                key=f"{state_key}_year_{idx}",
                label_visibility="collapsed",
            )
            days_in_year = col_days.number_input(
                "Days in Year",
                value=float(row.get("days_in_year", 365)),
                key=f"{state_key}_days_{idx}",
                min_value=360.0,
                max_value=370.0,
                step=1.0,
                label_visibility="collapsed",
            )
            receivable_days = col_ar_days.number_input(
                "Accounts Receivable Days",
                value=float(row.get("receivable_days", 45)),
                key=f"{state_key}_ar_{idx}",
                min_value=0.0,
                step=1.0,
                label_visibility="collapsed",
            )
            prepaid_days = col_prepaid.number_input(
                "Prepaid Expense Days",
                value=float(row.get("prepaid_expense_days", 30)),
                key=f"{state_key}_prepaid_{idx}",
                min_value=0.0,
                step=1.0,
                label_visibility="collapsed",
            )
            other_days = col_other.number_input(
                "Other Asset Days",
                value=float(row.get("other_asset_days", 5)),
                key=f"{state_key}_other_{idx}",
                min_value=0.0,
                step=1.0,
                label_visibility="collapsed",
            )
            remove_clicked = col_remove.button("Remove", key=f"{state_key}_remove_{idx}")
        if remove_clicked:
            continue
        updated_rows.append(
            {
                "year": year,
                "days_in_year": days_in_year,
                "receivable_days": receivable_days,
                "prepaid_expense_days": prepaid_days,
                "other_asset_days": other_days,
            }
        )
    st.session_state[state_key] = updated_rows

    if st.button("Add Receivable Year", key=f"{state_key}_add"):
        next_year = max(row["year"] for row in st.session_state[state_key]) + 1 if st.session_state[state_key] else 2024
        st.session_state[state_key].append(
            {
                "year": next_year,
                "days_in_year": 365,
                "receivable_days": 45,
                "prepaid_expense_days": 30,
                "other_asset_days": 5,
            }
        )


def _render_inventory_payables_section() -> None:
    state_key = "inventory_payables"
    if state_key not in st.session_state:
        st.session_state[state_key] = copy.deepcopy(INVENTORY_PAYABLE_DEFAULTS)

    st.markdown("### Inventory & Accounts Payable Input Table")
    rows = st.session_state[state_key]
    updated_rows: List[Dict[str, object]] = []
    year_options = list(range(2024, 2051))
    for idx, row in enumerate(rows):
        with st.container(border=True):
            col_year, col_days, col_inventory, col_payable, col_remove = st.columns([1.2, 1, 1, 1, 0.8])
            current_year = int(row.get("year", year_options[0]))
            if current_year not in year_options:
                current_year = year_options[0]
            year = col_year.selectbox(
                "Inventory year",
                options=year_options,
                index=year_options.index(current_year),
                key=f"{state_key}_year_{idx}",
                label_visibility="collapsed",
            )
            days_in_year = col_days.number_input(
                "Days in Year",
                value=float(row.get("days_in_year", 365)),
                key=f"{state_key}_days_{idx}",
                min_value=360.0,
                max_value=370.0,
                step=1.0,
                label_visibility="collapsed",
            )
            inventory_days = col_inventory.number_input(
                "Inventory Days",
                value=float(row.get("inventory_days", 50)),
                key=f"{state_key}_inventory_{idx}",
                min_value=0.0,
                step=1.0,
                label_visibility="collapsed",
            )
            payable_days = col_payable.number_input(
                "Accounts Payable Days",
                value=float(row.get("accounts_payable_days", 45)),
                key=f"{state_key}_payable_{idx}",
                min_value=0.0,
                step=1.0,
                label_visibility="collapsed",
            )
            remove_clicked = col_remove.button("Remove", key=f"{state_key}_remove_{idx}")
        if remove_clicked:
            continue
        updated_rows.append(
            {
                "year": year,
                "days_in_year": days_in_year,
                "inventory_days": inventory_days,
                "accounts_payable_days": payable_days,
            }
        )
    st.session_state[state_key] = updated_rows

    if st.button("Add Inventory Year", key=f"{state_key}_add"):
        next_year = max(row["year"] for row in st.session_state[state_key]) + 1 if st.session_state[state_key] else 2024
        st.session_state[state_key].append(
            {
                "year": next_year,
                "days_in_year": 365,
                "inventory_days": 50,
                "accounts_payable_days": 45,
            }
        )


def _render_fixed_assets_section() -> None:
    state_key = "fixed_assets_schedule"
    if state_key not in st.session_state:
        st.session_state[state_key] = copy.deepcopy(FIXED_ASSET_DEFAULTS)

    st.markdown("### Fixed Assets Schedule")
    rows = st.session_state[state_key]
    updated_rows: List[Dict[str, object]] = []
    method_options = ["Straight-Line", "Declining Balance"]
    year_options = list(range(2024, 2051))
    for idx, row in enumerate(rows):
        with st.container(border=True):
            (
                col_asset,
                col_method,
                col_year,
                col_acq,
                col_life,
                col_nbv,
                col_rate,
                col_total_cost,
                col_total_dep,
                col_cum_dep,
                col_end_nbv,
                col_remove,
            ) = st.columns([2.2, 1.5, 1, 1.5, 1, 1.5, 1, 1.5, 1.5, 1.5, 1.5, 0.8])

            asset_type = col_asset.text_input(
                "Asset Type",
                value=str(row.get("asset_type", "")),
                key=f"{state_key}_asset_{idx}",
                label_visibility="collapsed",
            )

            method = str(row.get("method", method_options[0]))
            if method not in method_options:
                method = method_options[0]
            method_value = col_method.selectbox(
                "Method",
                method_options,
                index=method_options.index(method),
                key=f"{state_key}_method_{idx}",
                label_visibility="collapsed",
            )

            current_year = int(row.get("year", year_options[0]))
            if current_year not in year_options:
                current_year = year_options[0]
            year = col_year.selectbox(
                "Year",
                options=year_options,
                index=year_options.index(current_year),
                key=f"{state_key}_year_{idx}",
                label_visibility="collapsed",
            )

            acquisition = col_acq.number_input(
                "Acquisition",
                value=float(row.get("acquisition", 0.0)),
                key=f"{state_key}_acq_{idx}",
                min_value=0.0,
                step=1000.0,
                label_visibility="collapsed",
            )
            asset_life = col_life.number_input(
                "Asset Life",
                value=float(row.get("asset_life", 1.0)),
                key=f"{state_key}_life_{idx}",
                min_value=1.0,
                step=1.0,
                label_visibility="collapsed",
            )
            net_book_value = col_nbv.number_input(
                "Net Book Value",
                value=float(row.get("net_book_value", 0.0)),
                key=f"{state_key}_nbv_{idx}",
                min_value=0.0,
                step=1000.0,
                label_visibility="collapsed",
            )
            depreciation_rate = col_rate.number_input(
                "Depreciation Rate",
                value=float(row.get("depreciation_rate", 0.0)),
                key=f"{state_key}_rate_{idx}",
                min_value=0.0,
                max_value=1.0,
                step=0.001,
                label_visibility="collapsed",
            )
            total_asset_cost = col_total_cost.number_input(
                "Total Asset cost",
                value=float(row.get("total_asset_cost", 0.0)),
                key=f"{state_key}_total_cost_{idx}",
                min_value=0.0,
                step=1000.0,
                label_visibility="collapsed",
            )
            total_depreciation = col_total_dep.number_input(
                "Total Depreciation",
                value=float(row.get("total_depreciation", 0.0)),
                key=f"{state_key}_total_dep_{idx}",
                min_value=0.0,
                step=1000.0,
                label_visibility="collapsed",
            )
            cumulative_depreciation = col_cum_dep.number_input(
                "Cumulative Depreciation",
                value=float(row.get("cumulative_depreciation", 0.0)),
                key=f"{state_key}_cum_dep_{idx}",
                min_value=0.0,
                step=1000.0,
                label_visibility="collapsed",
            )
            ending_book_value = col_end_nbv.number_input(
                "Net Book Value",
                value=float(row.get("ending_book_value", 0.0)),
                key=f"{state_key}_ending_nbv_{idx}",
                min_value=0.0,
                step=1000.0,
                label_visibility="collapsed",
            )
            remove_clicked = col_remove.button("Remove", key=f"{state_key}_remove_{idx}")
        if remove_clicked:
            continue
        updated_rows.append(
            {
                "asset_type": asset_type,
                "method": method_value,
                "year": year,
                "acquisition": acquisition,
                "asset_life": asset_life,
                "net_book_value": net_book_value,
                "depreciation_rate": depreciation_rate,
                "total_asset_cost": total_asset_cost,
                "total_depreciation": total_depreciation,
                "cumulative_depreciation": cumulative_depreciation,
                "ending_book_value": ending_book_value,
            }
        )
    st.session_state[state_key] = updated_rows

    if st.button("Add Fixed Asset", key=f"{state_key}_add"):
        st.session_state[state_key].append(
            {
                "asset_type": "New Asset",
                "method": method_options[0],
                "year": year_options[0],
                "acquisition": 0.0,
                "asset_life": 1.0,
                "net_book_value": 0.0,
                "depreciation_rate": 0.0,
                "total_asset_cost": 0.0,
                "total_depreciation": 0.0,
                "cumulative_depreciation": 0.0,
                "ending_book_value": 0.0,
            }
        )


def _get_row_value(state_key: str, label: str, default: float | bool, expected_type: type) -> float | bool:
    rows = st.session_state.get(state_key, [])
    for row in rows:
        if row.get("label") == label:
            value = row.get("value", default)
            break
    else:
        return default

    if expected_type is bool:
        return bool(value)
    try:
        return expected_type(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _render_assumption_controls() -> tuple[bytes | None, Dict[str, float | bool]]:
    """Render the primary assumption inputs and return override values."""

    st.subheader("Assumptions")

    with st.container(border=True):
        st.markdown("#### Upload assumption workbook")
        uploaded_file = st.file_uploader(
            "Drag and drop file here",
            type=["xlsx", "xlsm", "xls"],
            help="Optional Excel workbook matching the model template (max 200MB).",
            key="uploaded_workbook",
        )
        st.caption("Limit 200MB per file · XLSX, XLSM, XLS")

    _render_projection_horizon_section()
    _render_label_value_table("Core Assumptions", "core_table", CORE_ASSUMPTION_DEFAULTS)
    _render_label_value_table("Global", "global_table", GLOBAL_DEFAULTS)
    _render_label_value_table("Energy", "energy_table", ENERGY_DEFAULTS)
    _render_label_value_table("Revenue Inputs", "revenue_table", REVENUE_DEFAULTS)
    _render_labour_structure_section()
    _render_fixed_variable_costs_section()
    _render_accounts_receivable_section()
    _render_inventory_payables_section()
    _render_fixed_assets_section()

    with st.container(border=True):
        st.markdown("#### Deployment")
        st.markdown(
            """
            Use the Streamlit Cloud deployer to launch this app directly from your GitHub repository.

            [Deploy on Streamlit Cloud](https://share.streamlit.io/deploy?repository=https://github.com/YOUR_GITHUB_USERNAME/solar_farm&mainScript=streamlit_app.py)
            """
        )

    excel_bytes = uploaded_file.getvalue() if uploaded_file is not None else None

    overrides: Dict[str, float | bool] = {
        "discount_rate": float(_get_row_value("core_table", "Discount Rate", 0.10, float)),
        "exit_multiple": float(_get_row_value("core_table", "Exit EBITDA Multiple", 5.0, float)),
        "include_terminal": bool(_get_row_value("core_table", "Include Terminal Value", True, bool)),
        "terminal_growth_rate": float(_get_row_value("core_table", "Terminal Growth Rate", 0.02, float)),
        "capacity_mw": float(_get_row_value("energy_table", "Capacity (MW)", 10.0, float)),
        "capacity_factor": float(_get_row_value("energy_table", "Capacity Factor", 0.145, float)),
        "degradation_rate": float(_get_row_value("energy_table", "Annual Degradation", 0.005, float)),
        "ppa_share": float(_get_row_value("revenue_table", "Share of Output via PPA", 0.90, float)),
        "ppa_rate": float(_get_row_value("revenue_table", "Year 1 PPA Rate ($/MWh)", 160.0, float)),
        "ppa_escalation": float(_get_row_value("revenue_table", "PPA Annual Escalation", 0.015, float)),
        "merchant_rate": float(_get_row_value("revenue_table", "Year 1 Merchant Rate ($/MWh)", 56.58, float)),
        "merchant_escalation": float(_get_row_value("revenue_table", "Merchant Annual Escalation", 0.015, float)),
        "rec_rate": float(_get_row_value("revenue_table", "Year 1 REC Price ($/MWh)", 40.0, float)),
        "rec_escalation": float(_get_row_value("revenue_table", "REC Annual Escalation", 0.02, float)),
    }

    return excel_bytes, overrides


def _render_input_landing(assumptions: Assumptions, outputs: ModelOutputs) -> None:
    """Present the core assumptions used to drive the model."""

    global_cfg = assumptions.global_assumptions
    energy_cfg = assumptions.energy
    metrics = outputs.metrics

    st.header("Core Assumptions")
    core_df = pd.DataFrame(
        {
            "Metric": [
                "Project Name",
                "Forecast Months",
                "Start Date",
                "Include Terminal Value",
                "Exit EBITDA Multiple",
                "Discount Rate",
                "Project NPV",
                "Project IRR",
            ],
            "Value": [
                global_cfg.project_name,
                global_cfg.forecast_months,
                global_cfg.start_date.strftime("%Y-%m-%d"),
                "Yes" if global_cfg.include_terminal_value else "No",
                f"{global_cfg.exit_multiple:.2f}x",
                _format_percentage(global_cfg.discount_rate),
                _format_currency(metrics.get("project_npv", float("nan"))),
                _format_percentage(metrics.get("project_irr", float("nan"))),
            ],
        }
    )
    st.dataframe(core_df, use_container_width=True, hide_index=True)

    st.header("Global")
    global_col1, global_col2, global_col3 = st.columns(3)
    with global_col1:
        st.metric("Income Tax Rate", _format_percentage(global_cfg.tax.income_tax_rate))
        st.metric("Capital Gains Tax", _format_percentage(global_cfg.tax.capital_gains_tax_rate))
    with global_col2:
        st.metric("Investor Share", _format_percentage(global_cfg.distribution.investor_share))
        st.metric("Owner Share", _format_percentage(global_cfg.distribution.owner_share))
    with global_col3:
        st.metric("Terminal Growth", _format_percentage(assumptions.terminal_growth_rate))
        st.metric("Payback", _format_metric("project_payback_months", metrics.get("project_payback_months", float("nan"))))

    st.header("Energy")
    energy_cols = st.columns(4)
    energy_cols[0].metric("Capacity (MW)", f"{energy_cfg.capacity_mw:,.2f}")
    energy_cols[1].metric("Capacity Factor", _format_percentage(energy_cfg.capacity_factor))
    energy_cols[2].metric("Degradation Rate", _format_percentage(energy_cfg.degradation_rate))
    energy_cols[3].metric("Annual Hours", f"{energy_cfg.annual_hours:,}")

    st.markdown("#### Seasonal Production Profile")
    seasonality_df = pd.DataFrame(
        {
            "Month": [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ],
            "Share of Annual Output": assumptions.energy.seasonality,
        }
    )
    seasonality_df["Share of Annual Output"] = seasonality_df["Share of Annual Output"].apply(_format_percentage)
    st.dataframe(seasonality_df, use_container_width=True, hide_index=True)


def _render_overview(outputs: ModelOutputs, summary_tables: Dict[str, pd.DataFrame]) -> None:
    """Display the overview page with key metrics and highlights."""

    st.subheader("Headline metrics")
    metrics = outputs.metrics
    metric_cols = st.columns(len(MetricLabels))
    for col, (metric_key, label) in zip(metric_cols, MetricLabels.items()):
        value = metrics.get(metric_key, float("nan"))
        col.metric(label, _format_metric(metric_key, value))

    st.divider()
    st.subheader("Latest drivers")
    st.dataframe(summary_tables["key_drivers"], use_container_width=True)

    st.divider()
    energy_chart, cashflow_chart = st.columns(2)
    with energy_chart:
        st.markdown("#### Energy production")
        st.line_chart(outputs.monthly_results["energy_mwh"], use_container_width=True)
    with cashflow_chart:
        st.markdown("#### Equity cash flow")
        st.area_chart(outputs.monthly_results["equity_cash_flow"], use_container_width=True)

    st.divider()
    st.subheader("Annual summary")
    annual = summary_tables["annual_summary"]
    st.dataframe(annual, use_container_width=True)


def _render_revenue_and_energy(outputs: ModelOutputs) -> None:
    """Display revenue composition and energy output analytics."""

    monthly = outputs.monthly_results
    st.subheader("Energy and revenue")

    st.markdown("#### Monthly energy production")
    st.line_chart(monthly["energy_mwh"], use_container_width=True)

    revenue_cols = monthly.filter(like="revenue_")
    if not revenue_cols.empty:
        st.markdown("#### Revenue mix")
        st.area_chart(revenue_cols, use_container_width=True)
        annual_revenue = revenue_cols.resample("A").sum()
        annual_revenue.index = annual_revenue.index.year
        st.dataframe(annual_revenue, use_container_width=True)
    else:
        st.info("Revenue inputs were not available in the current run.")


def _render_operating_costs(outputs: ModelOutputs) -> None:
    """Display fixed and variable operating cost trends."""

    monthly = outputs.monthly_results
    opex_cols = monthly.filter(like="opex_")

    st.subheader("Operating costs")
    st.markdown("#### Total operating cost")
    st.line_chart(monthly["total_opex"], use_container_width=True)

    if not opex_cols.empty:
        st.markdown("#### Cost breakdown")
        st.area_chart(opex_cols, use_container_width=True)
        annual_opex = opex_cols.resample("A").sum()
        annual_opex.index = annual_opex.index.year
        st.dataframe(annual_opex, use_container_width=True)
    else:
        st.info("No operating expense items were configured for this run.")


def _render_capital_and_debt(outputs: ModelOutputs) -> None:
    """Display capex profile and debt schedule insights."""

    monthly = outputs.monthly_results
    st.subheader("Capital expenditure and debt")

    if "capex" in monthly.columns:
        st.markdown("#### Monthly capex")
        st.bar_chart(monthly[["capex"]], use_container_width=True)
    else:
        st.info("Capex profile not available.")

    debt_cols = [col for col in ["debt_draw", "debt_principal", "debt_interest", "debt_balance"] if col in monthly.columns]
    if debt_cols:
        st.markdown("#### Debt schedule")
        st.line_chart(monthly[debt_cols], use_container_width=True)
        st.dataframe(monthly[debt_cols], use_container_width=True)
    else:
        st.info("Debt facilities are not part of the current assumption set.")


def _render_cash_flows(outputs: ModelOutputs) -> None:
    """Display free cash flow and equity distribution analytics."""

    monthly = outputs.monthly_results
    st.subheader("Cash flow & returns")

    cash_cols = ["fcff", "equity_cash_flow", "investor_cash_flow", "owner_cash_flow"]
    available_cash = [c for c in cash_cols if c in monthly.columns]

    if available_cash:
        st.markdown("#### Monthly cash flows")
        st.area_chart(monthly[available_cash], use_container_width=True)

        cumulative = monthly[available_cash].cumsum()
        cumulative.columns = [f"cumulative_{col}" for col in cumulative.columns]
        st.markdown("#### Cumulative cash flows")
        st.line_chart(cumulative, use_container_width=True)
        st.dataframe(cumulative, use_container_width=True)
    else:
        st.info("Cash flow outputs are not available for the current run.")


def _render_data_and_downloads(outputs: ModelOutputs, summary_tables: Dict[str, pd.DataFrame]) -> None:
    """Expose the raw tables along with download buttons."""

    st.subheader("Model tables")
    st.markdown("#### Monthly detail")
    st.dataframe(outputs.monthly_results, use_container_width=True)

    st.markdown("#### Annual summary")
    st.dataframe(outputs.annual_summary, use_container_width=True)

    st.markdown("#### Metrics")
    st.dataframe(summary_tables["metrics"], use_container_width=True)

    st.divider()
    st.subheader("Downloads")
    st.write("Export CSV extracts for offline analysis.")
    st.download_button(
        "Download monthly results", data=_downloadable_csv(outputs.monthly_results), file_name="monthly_results.csv"
    )
    st.download_button(
        "Download annual summary", data=_downloadable_csv(outputs.annual_summary), file_name="annual_summary.csv"
    )
    st.download_button(
        "Download metrics", data=_downloadable_csv(summary_tables["metrics"]), file_name="metrics.csv"
    )


def _render_financial_performance(outputs: ModelOutputs) -> None:
    """Render detailed income statement schedules."""

    st.header("Statement of Financial Performance")
    income_statement = outputs.annual_summary[
        ["revenue_total", "total_opex", "ebitda", "ebit", "tax_payment", "net_income"]
    ].rename(
        columns={
            "revenue_total": "Revenue",
            "total_opex": "Operating Expenses",
            "ebitda": "EBITDA",
            "ebit": "EBIT",
            "tax_payment": "Taxes",
            "net_income": "Net Income",
        }
    )
    st.dataframe(income_statement, use_container_width=True)

    st.header("Gross Revenue Schedule")
    revenue_schedule = outputs.monthly_results.filter(like="revenue_").resample("A").sum()
    revenue_schedule.index = revenue_schedule.index.year
    revenue_schedule = revenue_schedule.rename(
        columns=lambda c: c.replace("revenue_", "").replace("_", " ").title()
    )
    st.dataframe(revenue_schedule, use_container_width=True)

    st.header("Total Expense Schedule")
    expense_schedule = outputs.monthly_results.filter(like="opex_").resample("A").sum()
    expense_schedule.index = expense_schedule.index.year
    expense_schedule = expense_schedule.rename(
        columns=lambda c: c.replace("opex_", "").replace("_", " ").title()
    )
    expense_schedule["Total"] = expense_schedule.sum(axis=1)
    st.dataframe(expense_schedule, use_container_width=True)


def _render_financial_position(outputs: ModelOutputs) -> None:
    """Display a simplified balance sheet view."""

    monthly = outputs.monthly_results
    net_ppe = (monthly["capex"].cumsum() - monthly["depreciation"].cumsum()).clip(lower=0)
    cash_balance = monthly["equity_cash_flow"].cumsum()
    debt_balance = monthly.get("debt_balance", pd.Series(0.0, index=monthly.index))

    balance = pd.DataFrame(
        {
            "Cash": cash_balance,
            "Net PP&E": net_ppe,
            "Total Assets": cash_balance + net_ppe,
            "Debt Outstanding": debt_balance,
        }
    )
    balance["Equity"] = balance["Total Assets"] - balance["Debt Outstanding"]
    balance["Total Liabilities & Equity"] = balance["Debt Outstanding"] + balance["Equity"]

    balance_sheet = balance.resample("A").last()
    balance_sheet.index = balance_sheet.index.year

    st.header("Statement of Financial Position")
    st.dataframe(balance_sheet, use_container_width=True)


def _render_cash_flow_statement(outputs: ModelOutputs) -> None:
    """Show annual cash flow statement derived from the monthly projection."""

    monthly = outputs.monthly_results
    operating_cf = (monthly["ebitda"] - monthly["tax_payment"] - monthly["debt_interest"]).resample("A").sum()
    investing_cf = (-monthly["capex"]).resample("A").sum()
    financing_cf = (monthly["debt_draw"] - monthly["debt_principal"]).resample("A").sum()
    equity_cf = monthly["equity_cash_flow"].resample("A").sum()

    cash_flow = pd.DataFrame(
        {
            "Operating Cash Flow": operating_cf,
            "Investing Cash Flow": investing_cf,
            "Financing Cash Flow": financing_cf,
            "Equity Cash Flow": equity_cf,
        }
    )
    cash_flow["Net Cash Flow"] = cash_flow[["Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow"]].sum(axis=1)
    cash_flow["Cumulative Net Cash"] = cash_flow["Net Cash Flow"].cumsum()
    cash_flow.index = cash_flow.index.year

    st.header("Statement of Cash Flows")
    st.dataframe(cash_flow, use_container_width=True)


def _simulate_metrics(base: Assumptions, modifier: Callable[[Assumptions], None]) -> Dict[str, float]:
    """Clone assumptions, apply a modifier, and return the resulting metrics."""

    scenario = copy.deepcopy(base)
    modifier(scenario)
    scenario_model = SolarFarmFinancialModel(scenario)
    scenario_outputs = scenario_model.run()
    return scenario_outputs.metrics


def _render_sensitivity_analysis(base_assumptions: Assumptions, outputs: ModelOutputs) -> None:
    """Present one-way sensitivity tables for key drivers."""

    variations: Dict[str, Callable[[Assumptions], None]] = {
        "PPA Rate -10%": lambda a: setattr(a.revenue.ppa.rate_curve, "initial", a.revenue.ppa.rate_curve.initial * 0.90),
        "PPA Rate +10%": lambda a: setattr(a.revenue.ppa.rate_curve, "initial", a.revenue.ppa.rate_curve.initial * 1.10),
        "Capacity Factor -10%": lambda a: setattr(
            a.energy,
            "capacity_factor",
            max(0.01, min(1.0, a.energy.capacity_factor * 0.90)),
        ),
        "Capacity Factor +10%": lambda a: setattr(
            a.energy,
            "capacity_factor",
            max(0.01, min(1.0, a.energy.capacity_factor * 1.10)),
        ),
        "Capex +10%": lambda a: [setattr(item, "amount", item.amount * 1.10) for item in a.capex_items],
        "Capex -10%": lambda a: [setattr(item, "amount", item.amount * 0.90) for item in a.capex_items],
        "Opex +10%": lambda a: (
            [setattr(item, "annual_cost", item.annual_cost * 1.10) for item in a.fixed_opex],
            [setattr(item, "cost_per_mwh", item.cost_per_mwh * 1.10) for item in a.variable_opex],
        ),
        "Opex -10%": lambda a: (
            [setattr(item, "annual_cost", item.annual_cost * 0.90) for item in a.fixed_opex],
            [setattr(item, "cost_per_mwh", item.cost_per_mwh * 0.90) for item in a.variable_opex],
        ),
    }

    records = [
        {
            "Scenario": "Base Case",
            "Project NPV": outputs.metrics.get("project_npv", float("nan")),
            "Project IRR": outputs.metrics.get("project_irr", float("nan")),
            "Equity IRR": outputs.metrics.get("equity_irr", float("nan")),
            "Payback (months)": outputs.metrics.get("project_payback_months", float("nan")),
        }
    ]

    for name, modifier in variations.items():
        metrics = _simulate_metrics(base_assumptions, modifier)
        records.append(
            {
                "Scenario": name,
                "Project NPV": metrics.get("project_npv", float("nan")),
                "Project IRR": metrics.get("project_irr", float("nan")),
                "Equity IRR": metrics.get("equity_irr", float("nan")),
                "Payback (months)": metrics.get("project_payback_months", float("nan")),
            }
        )

    sensitivity_df = pd.DataFrame(records)
    st.header("Sensitivity Analyses")
    st.dataframe(sensitivity_df, use_container_width=True)


def _render_scenario_analysis(base_assumptions: Assumptions, outputs: ModelOutputs) -> None:
    """Display predefined multi-factor scenarios."""

    scenarios: Dict[str, Callable[[Assumptions], None]] = {
        "Base Case": lambda a: None,
        "Optimistic": lambda a: (
            setattr(a.revenue.ppa.rate_curve, "initial", a.revenue.ppa.rate_curve.initial * 1.05),
            setattr(a.energy, "capacity_factor", max(0.01, min(1.0, a.energy.capacity_factor * 1.05))),
            [setattr(item, "amount", item.amount * 0.95) for item in a.capex_items],
            [setattr(item, "annual_cost", item.annual_cost * 0.95) for item in a.fixed_opex],
        ),
        "Downside": lambda a: (
            setattr(a.revenue.ppa.rate_curve, "initial", a.revenue.ppa.rate_curve.initial * 0.95),
            setattr(a.energy, "capacity_factor", max(0.01, min(1.0, a.energy.capacity_factor * 0.95))),
            [setattr(item, "amount", item.amount * 1.05) for item in a.capex_items],
            [setattr(item, "annual_cost", item.annual_cost * 1.05) for item in a.fixed_opex],
        ),
    }

    results = []
    for name, modifier in scenarios.items():
        if name == "Base Case":
            metrics = outputs.metrics
        else:
            metrics = _simulate_metrics(base_assumptions, modifier)
        results.append(
            {
                "Scenario": name,
                "Project NPV": metrics.get("project_npv", float("nan")),
                "Project IRR": metrics.get("project_irr", float("nan")),
                "Equity IRR": metrics.get("equity_irr", float("nan")),
                "Investor IRR": metrics.get("investor_irr", float("nan")),
                "Owner IRR": metrics.get("owner_irr", float("nan")),
                "Payback (months)": metrics.get("project_payback_months", float("nan")),
            }
        )

    scenario_df = pd.DataFrame(results)
    st.header("Scenario / IFs Analysis")
    st.dataframe(scenario_df, use_container_width=True)

    selected = st.selectbox("Select scenario for highlight", scenario_df["Scenario"].tolist())
    selected_row = scenario_df[scenario_df["Scenario"] == selected].iloc[0]
    highlight_cols = st.columns(3)
    highlight_cols[0].metric("Project NPV", _format_currency(selected_row["Project NPV"]))
    highlight_cols[1].metric("Project IRR", _format_percentage(selected_row["Project IRR"]))
    highlight_cols[2].metric("Payback", f"{selected_row['Payback (months)']:.0f} months")


def _render_monte_carlo(base_assumptions: Assumptions) -> None:
    """Run a Monte Carlo analysis across core drivers."""

    st.header("Monte Carlo Simulation")
    iterations = st.slider("Number of simulations", min_value=100, max_value=400, value=200, step=50)
    rng = np.random.default_rng(42)

    results = []
    progress = st.progress(0.0)
    for i in range(iterations):

        def modifier(a: Assumptions) -> None:
            a.energy.capacity_factor = max(0.01, min(0.9, a.energy.capacity_factor * rng.normal(1.0, 0.05)))
            a.revenue.ppa.rate_curve.initial *= rng.normal(1.0, 0.05)
            a.revenue.merchant.rate_curve.initial *= rng.normal(1.0, 0.05)
            for item in a.capex_items:
                item.amount *= rng.normal(1.0, 0.05)
            for item in a.fixed_opex:
                item.annual_cost *= rng.normal(1.0, 0.05)
            for item in a.variable_opex:
                item.cost_per_mwh *= rng.normal(1.0, 0.05)

        metrics = _simulate_metrics(base_assumptions, modifier)
        results.append(
            {
                "Project NPV": metrics.get("project_npv", float("nan")),
                "Project IRR": metrics.get("project_irr", float("nan")),
                "Equity IRR": metrics.get("equity_irr", float("nan")),
                "Payback (months)": metrics.get("project_payback_months", float("nan")),
            }
        )
        progress.progress((i + 1) / iterations)

    progress.empty()
    mc_df = pd.DataFrame(results)

    st.markdown("#### Distribution Summary")
    summary = mc_df.agg(["mean", "std", "min", "max"])
    quantiles = mc_df.quantile([0.1, 0.5, 0.9]).rename(index={0.1: "P10", 0.5: "Median", 0.9: "P90"})
    st.dataframe(pd.concat([summary, quantiles]), use_container_width=True)

    st.markdown("#### Project NPV Distribution")
    hist, bins = np.histogram(mc_df["Project NPV"].dropna(), bins=20)
    if hist.size:
        midpoints = (bins[:-1] + bins[1:]) / 2
        hist_df = pd.DataFrame({"Count": hist}, index=pd.Index(midpoints, name="NPV"))
        st.bar_chart(hist_df)
    else:
        st.info("Not enough data to plot histogram.")


def _render_break_even(outputs: ModelOutputs) -> None:
    """Show break-even and payback diagnostics."""

    st.header("Break-Even & Payback")
    monthly = outputs.monthly_results
    cumulative_equity = monthly["equity_cash_flow"].cumsum()
    breakeven_mask = cumulative_equity >= 0
    breakeven_date = cumulative_equity.index[breakeven_mask.argmax()] if breakeven_mask.any() else None

    metrics = outputs.metrics
    metric_cols = st.columns(3)
    metric_cols[0].metric("Project NPV", _format_currency(metrics.get("project_npv", float("nan"))))
    metric_cols[1].metric("Project IRR", _format_percentage(metrics.get("project_irr", float("nan"))))
    metric_cols[2].metric(
        "Payback",
        _format_metric("project_payback_months", metrics.get("project_payback_months", float("nan"))),
    )

    if breakeven_date is not None:
        st.success(f"Break-even reached in {breakeven_date.strftime('%B %Y')}")
    else:
        st.warning("Break-even is not reached within the projection horizon.")

    st.markdown("#### Cumulative Equity Cash Flow")
    cumulative_df = pd.DataFrame(
        {
            "Equity Cash Flow": monthly["equity_cash_flow"],
            "Cumulative Equity": cumulative_equity,
            "Cumulative FCFF": monthly["fcff"].cumsum(),
        }
    )
    st.line_chart(cumulative_df[["Cumulative Equity", "Cumulative FCFF"]], use_container_width=True)
    st.dataframe(cumulative_df, use_container_width=True)


st.title("Solar Farm Financial Model")
st.caption("Adjust the assumptions, run the project finance model, and inspect the outputs interactively.")

PAGE_OPTIONS = [
    "Input Landing Page",
    "Key Metrics Dashboard",
    "Financial Performance",
    "Financial Position",
    "Cash Flow Statement",
    "Sensitivity Analyses",
    "Scenario / IFs Analysis",
    "Monte Carlo Simulation",
    "Break-Even & Payback",
]

tabs = st.tabs(PAGE_OPTIONS)

with tabs[0]:
    excel_bytes, override_dict = _render_assumption_controls()

override_tuple = tuple(sorted(override_dict.items()))

outputs, summary_tables, assumptions = _run_model(excel_bytes, override_tuple)

with tabs[0]:
    st.divider()
    _render_input_landing(assumptions, outputs)

for page_name, tab in zip(PAGE_OPTIONS[1:], tabs[1:]):
    with tab:
        if page_name == "Key Metrics Dashboard":
            st.header("Overview")
            _render_overview(outputs, summary_tables)
            st.header("Revenue & Energy")
            _render_revenue_and_energy(outputs)
            st.header("Operating Costs")
            _render_operating_costs(outputs)
            st.header("Capital & Debt")
            _render_capital_and_debt(outputs)
            st.header("Cash Flow & Returns")
            _render_cash_flows(outputs)
            st.header("Data & Downloads")
            _render_data_and_downloads(outputs, summary_tables)
        elif page_name == "Financial Performance":
            _render_financial_performance(outputs)
        elif page_name == "Financial Position":
            _render_financial_position(outputs)
        elif page_name == "Cash Flow Statement":
            _render_cash_flow_statement(outputs)
        elif page_name == "Sensitivity Analyses":
            _render_sensitivity_analysis(assumptions, outputs)
        elif page_name == "Scenario / IFs Analysis":
            _render_scenario_analysis(assumptions, outputs)
        elif page_name == "Monte Carlo Simulation":
            _render_monte_carlo(assumptions)
        else:
            _render_break_even(outputs)

with st.sidebar:
    st.info("Use the Input Landing Page tab to upload workbooks and adjust assumptions.")
    st.success("Model run complete. Adjust the inputs to refresh outputs.")

"""Interactive Streamlit application for the Solar Farm Financial Model."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import streamlit as st

from solar_farm_financial_model.data_loader import load_assumptions
from solar_farm_financial_model.model import ModelOutputs, SolarFarmFinancialModel
from solar_farm_financial_model.reporting import build_summary_report


MetricLabels = {
    "project_npv": "Project NPV",
    "project_irr": "Project IRR",
    "equity_irr": "Equity IRR",
    "investor_irr": "Investor IRR",
    "owner_irr": "Owner IRR",
    "project_payback_months": "Payback (months)",
}


@st.cache_data(show_spinner=False)
def _run_model(excel_bytes: bytes | None, override_items: Tuple[Tuple[str, float | bool], ...]) -> Tuple[ModelOutputs, Dict[str, pd.DataFrame]]:
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
    return outputs, summary_tables


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

st.title("☀️ Solar Farm Financial Model")
st.caption("Adjust the assumptions, run the project finance model, and inspect the outputs interactively.")

with st.sidebar:
    st.header("Assumptions")
    uploaded_file = st.file_uploader(
        "Upload assumption workbook", type=["xlsx", "xlsm", "xls"], help="Optional Excel file using the model template."
    )

    st.subheader("Global")
    discount_rate = st.number_input("Discount rate", min_value=0.0, max_value=1.0, value=0.10, step=0.01, format="%.2f")
    exit_multiple = st.number_input("Exit EBITDA multiple", min_value=0.0, value=5.0, step=0.5)
    include_terminal = st.checkbox("Include terminal value", value=True)
    terminal_growth_rate = st.number_input(
        "Terminal growth rate", min_value=0.0, max_value=0.10, value=0.02, step=0.005, format="%.3f"
    )

    st.subheader("Energy")
    capacity_mw = st.number_input("Capacity (MW)", min_value=1.0, value=10.0, step=0.5)
    capacity_factor = st.slider("Capacity factor", min_value=0.05, max_value=0.35, value=0.145, step=0.005)
    degradation_rate = st.slider("Annual degradation", min_value=0.0, max_value=0.05, value=0.005, step=0.001)

    st.subheader("Revenue")
    ppa_share = st.slider("Share of output sold via PPA", min_value=0.0, max_value=1.0, value=0.90, step=0.05)
    ppa_rate = st.number_input("Year 1 PPA rate ($/MWh)", min_value=0.0, value=160.0, step=5.0)
    ppa_escalation = st.number_input("PPA annual escalation", min_value=0.0, max_value=0.10, value=0.015, step=0.005, format="%.3f")

    merchant_rate = st.number_input("Year 1 merchant rate ($/MWh)", min_value=0.0, value=56.58, step=2.0)
    merchant_escalation = st.number_input(
        "Merchant annual escalation", min_value=0.0, max_value=0.10, value=0.015, step=0.005, format="%.3f"
    )

    rec_rate = st.number_input("Year 1 REC price ($/MWh)", min_value=0.0, value=40.0, step=1.0)
    rec_escalation = st.number_input("REC annual escalation", min_value=0.0, max_value=0.10, value=0.02, step=0.005, format="%.3f")

    st.divider()
    st.markdown(
        """
        ### Deploy to Streamlit Cloud
        Use the Streamlit Cloud deployer to launch this app directly from your GitHub repository.

        [Deploy on Streamlit Cloud](https://share.streamlit.io/deploy?repository=https://github.com/YOUR_GITHUB_USERNAME/solar_farm&mainScript=streamlit_app.py)
        """
    )

override_tuple = tuple(
    sorted(
        {
            "discount_rate": float(discount_rate),
            "exit_multiple": float(exit_multiple),
            "include_terminal": bool(include_terminal),
            "terminal_growth_rate": float(terminal_growth_rate),
            "capacity_mw": float(capacity_mw),
            "capacity_factor": float(capacity_factor),
            "degradation_rate": float(degradation_rate),
            "ppa_share": float(ppa_share),
            "ppa_rate": float(ppa_rate),
            "ppa_escalation": float(ppa_escalation),
            "merchant_rate": float(merchant_rate),
            "merchant_escalation": float(merchant_escalation),
            "rec_rate": float(rec_rate),
            "rec_escalation": float(rec_escalation),
        }.items()
    )
)

excel_bytes = uploaded_file.getvalue() if uploaded_file is not None else None

outputs, summary_tables = _run_model(excel_bytes, override_tuple)

metrics = outputs.metrics
metric_cols = st.columns(len(MetricLabels))
for col, (metric_key, label) in zip(metric_cols, MetricLabels.items()):
    value = metrics.get(metric_key, float("nan"))
    col.metric(label, _format_metric(metric_key, value))

energy_chart, cashflow_chart = st.columns(2)
with energy_chart:
    st.subheader("Energy generation (MWh)")
    st.line_chart(outputs.monthly_results["energy_mwh"])
with cashflow_chart:
    st.subheader("Equity cash flow")
    st.area_chart(outputs.monthly_results["equity_cash_flow"])

summary_tab, monthly_tab, annual_tab, download_tab = st.tabs(
    ["Summary tables", "Monthly results", "Annual summary", "Downloads"]
)

with summary_tab:
    st.subheader("Key Drivers")
    st.dataframe(summary_tables["key_drivers"], use_container_width=True)
    st.subheader("Metrics")
    st.dataframe(summary_tables["metrics"], use_container_width=True)

with monthly_tab:
    st.dataframe(outputs.monthly_results, use_container_width=True)

with annual_tab:
    st.dataframe(outputs.annual_summary, use_container_width=True)

with download_tab:
    st.write("Download CSV extracts for offline analysis.")
    st.download_button(
        "Download monthly results", data=_downloadable_csv(outputs.monthly_results), file_name="monthly_results.csv"
    )
    st.download_button(
        "Download annual summary", data=_downloadable_csv(outputs.annual_summary), file_name="annual_summary.csv"
    )
    st.download_button(
        "Download metrics", data=_downloadable_csv(summary_tables["metrics"]), file_name="metrics.csv"
    )

st.success("Model run complete. Adjust the assumptions in the sidebar to refresh the outputs.")

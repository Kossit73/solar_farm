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

    st.subheader("Navigation")
    selected_page = st.radio(
        "Select a page",
        options=[
            "Overview",
            "Revenue & Energy",
            "Operating Costs",
            "Capital & Debt",
            "Cash Flow & Returns",
            "Data & Downloads",
        ],
        index=0,
        key="page_selector",
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

if selected_page == "Overview":
    _render_overview(outputs, summary_tables)
elif selected_page == "Revenue & Energy":
    _render_revenue_and_energy(outputs)
elif selected_page == "Operating Costs":
    _render_operating_costs(outputs)
elif selected_page == "Capital & Debt":
    _render_capital_and_debt(outputs)
elif selected_page == "Cash Flow & Returns":
    _render_cash_flows(outputs)
else:
    _render_data_and_downloads(outputs, summary_tables)

st.success("Model run complete. Adjust the assumptions in the sidebar to refresh the outputs.")

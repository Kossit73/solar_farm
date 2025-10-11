"""Interactive Streamlit application for the Solar Farm Financial Model."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Callable, Dict, Tuple

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
            "Input Landing Page",
            "Key Metrics Dashboard",
            "Financial Performance",
            "Financial Position",
            "Cash Flow Statement",
            "Sensitivity Analyses",
            "Scenario / IFs Analysis",
            "Monte Carlo Simulation",
            "Break-Even & Payback",
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

outputs, summary_tables, assumptions = _run_model(excel_bytes, override_tuple)

if selected_page == "Input Landing Page":
    _render_input_landing(assumptions, outputs)
elif selected_page == "Key Metrics Dashboard":
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
elif selected_page == "Financial Performance":
    _render_financial_performance(outputs)
elif selected_page == "Financial Position":
    _render_financial_position(outputs)
elif selected_page == "Cash Flow Statement":
    _render_cash_flow_statement(outputs)
elif selected_page == "Sensitivity Analyses":
    _render_sensitivity_analysis(assumptions, outputs)
elif selected_page == "Scenario / IFs Analysis":
    _render_scenario_analysis(assumptions, outputs)
elif selected_page == "Monte Carlo Simulation":
    _render_monte_carlo(assumptions)
else:
    _render_break_even(outputs)

st.success("Model run complete. Adjust the assumptions in the sidebar to refresh the outputs.")

"""Reporting helpers for the Solar Farm Financial Model."""

from __future__ import annotations

from typing import Dict

import pandas as pd

from .model import ModelOutputs


def build_summary_report(outputs: ModelOutputs) -> Dict[str, pd.DataFrame]:
    """Create a dictionary of report tables for downstream consumption."""

    metrics_df = (
        pd.Series(outputs.metrics, name="value")
        .to_frame()
        .assign(metric=lambda df: df.index)
        .reset_index(drop=True)[["metric", "value"]]
    )

    latest_month = outputs.monthly_results.iloc[-1]
    key_drivers = pd.DataFrame(
        {
            "Metric": [
                "Final Month Revenue",
                "Final Month EBITDA",
                "Final Month Equity Cash Flow",
                "Cumulative FCFF",
                "Cumulative Equity Cash Flow",
            ],
            "Value": [
                latest_month["revenue_total"],
                latest_month["ebitda"],
                latest_month["equity_cash_flow"],
                outputs.monthly_results["fcff"].sum(),
                outputs.monthly_results["equity_cash_flow"].sum(),
            ],
        }
    )

    tables = {
        "metrics": metrics_df,
        "annual_summary": outputs.annual_summary.reset_index().rename(columns={"index": "year"}),
        "key_drivers": key_drivers,
    }
    return tables

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from solar_farm_financial_model.model import ModelOutputs
from solar_farm_financial_model.schemas import Assumptions

from .types import EvidencePacket, QuestionPlan


def build_model_context(outputs: ModelOutputs, assumptions: Assumptions) -> Dict[str, Any]:
    """Serialize core model outputs/assumptions for reasoning use."""
    return {
        "metrics": dict(outputs.metrics),
        "assumptions": assumptions.to_dict(),
        "monthly": outputs.monthly_results.reset_index().to_dict(orient="records"),
        "annual": outputs.annual_summary.reset_index().to_dict(orient="records"),
    }


def analyze_internal(
    plan: QuestionPlan,
    outputs: ModelOutputs,
    assumptions: Assumptions,
) -> EvidencePacket:
    """Run internal analyses based on the plan intent."""
    del assumptions  # reserved for richer inference where assumption-level deltas are needed

    packet = EvidencePacket()
    monthly = outputs.monthly_results
    annual = outputs.annual_summary
    metrics = outputs.metrics

    packet.internal_facts["intent"] = plan.intent
    packet.internal_facts["project_npv"] = float(metrics.get("project_npv", float("nan")))
    packet.internal_facts["project_irr"] = float(metrics.get("project_irr", float("nan")))
    packet.internal_facts["equity_irr"] = float(metrics.get("equity_irr", float("nan")))

    if "revenue_total" in annual.columns and len(annual) >= 2:
        packet.driver_breakdown["revenue_delta_latest_vs_first"] = float(
            annual["revenue_total"].iloc[-1] - annual["revenue_total"].iloc[0]
        )
    if "ebitda" in annual.columns and len(annual) >= 2:
        packet.driver_breakdown["ebitda_delta_latest_vs_first"] = float(
            annual["ebitda"].iloc[-1] - annual["ebitda"].iloc[0]
        )

    if "dscr" in monthly.columns:
        dscr_series = pd.to_numeric(monthly["dscr"], errors="coerce").dropna()
        packet.internal_facts["avg_dscr"] = float(dscr_series.mean()) if not dscr_series.empty else float("nan")
        packet.internal_facts["min_dscr"] = float(dscr_series.min()) if not dscr_series.empty else float("nan")

    return packet

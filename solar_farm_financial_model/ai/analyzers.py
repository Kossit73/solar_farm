from __future__ import annotations
from typing import Any, Dict
import pandas as pd
from solar_farm_financial_model.model import ModelOutputs
from solar_farm_financial_model.schemas import Assumptions
from .types import QuestionPlan, EvidencePacket

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
    """Run internal-only analyses based on plan intent."""
    packet = EvidencePacket()
    m = outputs.monthly_results
    a = outputs.annual_summary
    metrics = outputs.metrics

    # Minimal baseline facts
    packet.internal_facts["project_npv"] = float(metrics.get("project_npv", float("nan")))
    packet.internal_facts["project_irr"] = float(metrics.get("project_irr", float("nan")))
    packet.internal_facts["equity_irr"] = float(metrics.get("equity_irr", float("nan")))
    packet.internal_facts["capacity_mw"] = float(assumptions.energy.capacity_mw)
    packet.internal_facts["capacity_factor"] = float(assumptions.energy.capacity_factor)
    packet.internal_facts["ppa_rate"] = float(assumptions.revenue.ppa.rate_curve.initial)
    packet.internal_facts["merchant_rate"] = float(assumptions.revenue.merchant.rate_curve.initial)

    # Example driver analysis
    if "revenue_total" in a.columns and len(a) >= 2:
        packet.driver_breakdown["revenue_delta_latest_vs_first"] = float(a["revenue_total"].iloc[-1] - a["revenue_total"].iloc[0])
        packet.driver_breakdown["revenue_latest"] = float(a["revenue_total"].iloc[-1])
    if "ebitda" in a.columns and len(a) >= 2:
        packet.driver_breakdown["ebitda_delta_latest_vs_first"] = float(a["ebitda"].iloc[-1] - a["ebitda"].iloc[0])
        packet.driver_breakdown["ebitda_latest"] = float(a["ebitda"].iloc[-1])
    if "revenue_total" in a.columns and "ebitda" in a.columns and len(a) > 0:
        latest_revenue = float(a["revenue_total"].iloc[-1])
        latest_ebitda = float(a["ebitda"].iloc[-1])
        packet.driver_breakdown["ebitda_margin_latest"] = (
            latest_ebitda / latest_revenue if latest_revenue != 0 else float("nan")
        )

    # Risk/covenants
    if "dscr" in m.columns:
        dscr_series = pd.to_numeric(m["dscr"], errors="coerce").dropna()
        packet.internal_facts["avg_dscr"] = float(dscr_series.mean()) if not dscr_series.empty else float("nan")
        packet.internal_facts["min_dscr"] = float(dscr_series.min()) if not dscr_series.empty else float("nan")
        packet.driver_breakdown["dscr_breach_months"] = int((dscr_series < 1.20).sum()) if not dscr_series.empty else 0

    metric = plan.entities.get("metric")
    if isinstance(metric, str):
        packet.internal_facts["focus_metric"] = metric

    return packet

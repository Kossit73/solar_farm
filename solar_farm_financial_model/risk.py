"""Risk schedule helpers shared by the solar app and model package."""

from __future__ import annotations

import copy
import uuid
from typing import Dict, List, Sequence


_RISK_FIELDS = ("inherent_risk", "climate_risk", "political_risk")


def sync_annual_risk_rows(
    rows: Sequence[Dict[str, object]],
    year_options: Sequence[int],
) -> List[Dict[str, object]]:
    """Return one risk row per projection year, carrying values forward."""

    if not year_options:
        return []

    sorted_years = list(year_options)
    baseline = copy.deepcopy(rows[0]) if rows else {
        "name": "Baseline",
        "year": sorted_years[0],
        "inherent_risk": 0.0,
        "climate_risk": 0.0,
        "political_risk": 0.0,
    }
    baseline.setdefault("name", "Baseline")
    baseline["year"] = int(baseline.get("year", sorted_years[0]))
    baseline["id"] = str(baseline.get("id") or uuid.uuid4().hex)

    existing_by_year = {
        int(row.get("year", sorted_years[0])): copy.deepcopy(row)
        for row in rows
    }

    normalized: List[Dict[str, object]] = []
    prior_row = baseline
    for year in sorted_years:
        explicit_row = existing_by_year.get(int(year))
        source = explicit_row if explicit_row is not None else prior_row
        row = copy.deepcopy(source)
        row["id"] = str(row.get("id") or uuid.uuid4().hex)
        row["year"] = int(year)
        row["name"] = str(row.get("name", baseline.get("name", "Baseline")) or "Baseline")
        for field in _RISK_FIELDS:
            row[field] = max(0.0, float(row.get(field, 0.0)))
        normalized.append(row)
        prior_row = row
    return normalized

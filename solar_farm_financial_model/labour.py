from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pandas as pd

from .schemas import FixedOpexItem


LABOUR_BASE_FIELDS: Tuple[str, ...] = (
    "role",
    "allocation_driver",
    "scope",
    "target_sku_id",
    "monthly_cost_per_fte",
    "annual_raise_pct",
    "benefits_pct",
    "payroll_tax_pct",
    "overtime_pct",
    "capacity_liters_per_fte_month",
)


def labour_year_columns(year_count: int) -> List[str]:
    return [f"Year {idx}" for idx in range(1, max(int(year_count), 1) + 1)]


def labour_tuple_fields(year_count: int) -> Tuple[str, ...]:
    return LABOUR_BASE_FIELDS + tuple(labour_year_columns(year_count))


def default_labour_rows(year_columns: Sequence[str]) -> List[Dict[str, object]]:
    def _year_row(values: Sequence[float]) -> Dict[str, float]:
        padded = list(values) + ([values[-1]] * max(len(year_columns) - len(values), 0))
        return {column: float(padded[idx]) for idx, column in enumerate(year_columns)}

    return [
        {
            "role": "Plant Manager",
            "allocation_driver": "mwh",
            "scope": "global",
            "target_sku_id": "",
            "monthly_cost_per_fte": 6_500.0,
            "annual_raise_pct": 0.03,
            "benefits_pct": 0.10,
            "payroll_tax_pct": 0.08,
            "overtime_pct": 0.02,
            "capacity_liters_per_fte_month": 0.0,
            **_year_row([1.0]),
        },
        {
            "role": "Field Technicians",
            "allocation_driver": "mwh",
            "scope": "global",
            "target_sku_id": "",
            "monthly_cost_per_fte": 3_000.0,
            "annual_raise_pct": 0.03,
            "benefits_pct": 0.15,
            "payroll_tax_pct": 0.08,
            "overtime_pct": 0.02,
            "capacity_liters_per_fte_month": 0.0,
            **_year_row([4.0]),
        },
        {
            "role": "Control Room Operator",
            "allocation_driver": "mwh",
            "scope": "global",
            "target_sku_id": "",
            "monthly_cost_per_fte": 2_600.0,
            "annual_raise_pct": 0.03,
            "benefits_pct": 0.18,
            "payroll_tax_pct": 0.08,
            "overtime_pct": 0.02,
            "capacity_liters_per_fte_month": 0.0,
            **_year_row([2.0]),
        },
        {
            "role": "Maintenance Crew",
            "allocation_driver": "mwh",
            "scope": "global",
            "target_sku_id": "",
            "monthly_cost_per_fte": 3_400.0,
            "annual_raise_pct": 0.03,
            "benefits_pct": 0.13,
            "payroll_tax_pct": 0.07,
            "overtime_pct": 0.025,
            "capacity_liters_per_fte_month": 0.0,
            **_year_row([3.0]),
        },
    ]


def normalize_labour_rows(
    rows: Sequence[Dict[str, object]] | None,
    year_columns: Sequence[str],
) -> List[Dict[str, object]]:
    if rows is None:
        return default_labour_rows(year_columns)
    if not rows:
        return []

    normalized_rows: List[Dict[str, object]] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        normalized_rows.append(_normalize_labour_row(raw_row, year_columns))

    return normalized_rows


def annual_labour_cost_series(
    row: Dict[str, object],
    year_columns: Sequence[str],
) -> List[float]:
    monthly_cost = max(0.0, _coerce_float(row.get("monthly_cost_per_fte")))
    annual_raise_pct = max(-0.99, _coerce_float(row.get("annual_raise_pct")))
    loaded_cost_multiplier = 1.0 + sum(
        max(0.0, _coerce_float(row.get(field)))
        for field in ("benefits_pct", "payroll_tax_pct", "overtime_pct")
    )

    annual_costs: List[float] = []
    for year_index, column in enumerate(year_columns):
        headcount = max(0.0, _coerce_float(row.get(column)))
        escalated_monthly_cost = monthly_cost * ((1.0 + annual_raise_pct) ** year_index)
        annual_costs.append(headcount * escalated_monthly_cost * 12.0 * loaded_cost_multiplier)
    return annual_costs


def labour_rows_to_fixed_opex(
    rows: Sequence[Dict[str, object]] | None,
    year_columns: Sequence[str],
) -> List[FixedOpexItem]:
    fixed_opex: List[FixedOpexItem] = []

    for row in normalize_labour_rows(rows, year_columns):
        role = str(row.get("role", "")).strip()
        if not role:
            continue

        prior_annual_cost = 0.0
        for year_index, annual_cost in enumerate(annual_labour_cost_series(row, year_columns)):
            delta = annual_cost - prior_annual_cost
            if abs(delta) > 1e-9:
                fixed_opex.append(
                    FixedOpexItem(
                        name=f"{role} Labour Step Year {year_index + 1}",
                        annual_cost=delta,
                        inflation_rate=0.0,
                        start_month=(year_index * 12) + 1,
                    )
                )
            prior_annual_cost = annual_cost

    return fixed_opex


def _normalize_labour_row(raw_row: Dict[str, object], year_columns: Sequence[str]) -> Dict[str, object]:
    legacy_annual_cost = _coerce_float(raw_row.get("annual_cost"))
    migrated_legacy_row = "monthly_cost_per_fte" not in raw_row and legacy_annual_cost > 0.0
    existing_year_columns = [column for column in raw_row if isinstance(column, str) and column.startswith("Year ")]
    last_year_value = _coerce_float(raw_row.get(existing_year_columns[-1])) if existing_year_columns else 0.0

    target_sku_id = raw_row.get("target_sku_id", "")
    if pd.isna(target_sku_id):
        target_sku_id = ""

    normalized = {
        "id": str(raw_row.get("id", "")).strip(),
        "role": str(raw_row.get("role", "")).strip(),
        "allocation_driver": str(raw_row.get("allocation_driver", "mwh")).strip() or "mwh",
        "scope": str(raw_row.get("scope", "global")).strip() or "global",
        "target_sku_id": str(target_sku_id).strip(),
        "monthly_cost_per_fte": _coerce_float(
            raw_row.get("monthly_cost_per_fte"),
            legacy_annual_cost / 12.0 if migrated_legacy_row else 0.0,
        ),
        "annual_raise_pct": _coerce_float(raw_row.get("annual_raise_pct")),
        "benefits_pct": _coerce_float(raw_row.get("benefits_pct")),
        "payroll_tax_pct": _coerce_float(raw_row.get("payroll_tax_pct")),
        "overtime_pct": _coerce_float(raw_row.get("overtime_pct")),
        "capacity_liters_per_fte_month": _coerce_float(raw_row.get("capacity_liters_per_fte_month")),
    }

    if migrated_legacy_row:
        normalized["annual_raise_pct"] = 0.0
        normalized["benefits_pct"] = 0.0
        normalized["payroll_tax_pct"] = 0.0
        normalized["overtime_pct"] = 0.0

    for column in year_columns:
        if column in raw_row:
            normalized[column] = _coerce_float(raw_row.get(column))
        elif migrated_legacy_row:
            normalized[column] = 1.0
        elif existing_year_columns:
            normalized[column] = last_year_value
        else:
            normalized[column] = 0.0

    return normalized


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

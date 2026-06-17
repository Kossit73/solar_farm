"""Input parsing helpers for the Solar Farm Streamlit application."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .schemas import CapexItem, EnergyAssumptions, FixedOpexItem, VariableOpexItem

CALENDAR_HOURS_PER_YEAR = 8760.0


def coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def rows_from_tuple(
    data: Tuple[Tuple[object, ...], ...],
    fields: Tuple[str, ...],
) -> List[Dict[str, object]]:
    return [dict(zip(fields, row)) for row in data]


def tupleize(
    rows: List[Dict[str, object]],
    fields: Tuple[str, ...],
) -> Tuple[Tuple[object, ...], ...]:
    return tuple(tuple(row.get(field) for field in fields) for row in rows)


def parse_spend_profile(value: object) -> List[float]:
    if isinstance(value, str):
        values = [segment.strip() for segment in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
    else:
        values = [value]

    parsed = [max(0.0, coerce_float(item)) for item in values if str(item).strip()]
    return parsed or [1.0]


def annual_resource_hours_to_capacity_factor(resource_hours: float) -> float:
    return max(0.0, resource_hours) / CALENDAR_HOURS_PER_YEAR


def expected_mwh_to_capacity_factor(capacity_mw: float, annual_mwh: float) -> float:
    denominator = max(capacity_mw, 0.0) * CALENDAR_HOURS_PER_YEAR
    if denominator <= 0:
        return 0.0
    return max(0.0, annual_mwh) / denominator


def build_opex_items(
    cost_rows: List[Dict[str, object]],
    default_inflation: float,
) -> Tuple[List[FixedOpexItem], List[VariableOpexItem]]:
    """Aggregate operating expense overrides into fixed and variable item lists."""

    fixed_map: Dict[str, Dict[str, float | str]] = {}
    variable_map: Dict[str, Dict[str, float | str]] = {}

    for row in cost_rows:
        name = str(row.get("name", "")).strip()
        if not name:
            continue

        inflation_rate = max(0.0, coerce_float(row.get("inflation_rate"), default_inflation))
        fixed_cost = max(0.0, coerce_float(row.get("fixed_cost")))
        variable_cost = max(0.0, coerce_float(row.get("variable_cost")))
        norm_name = name.lower()

        if fixed_cost > 0:
            entry = fixed_map.setdefault(
                norm_name,
                {"label": name, "cost": 0.0, "inflation": inflation_rate},
            )
            entry["label"] = entry.get("label") or name
            entry["cost"] = float(entry["cost"]) + fixed_cost
            entry["inflation"] = inflation_rate

        if variable_cost > 0:
            entry = variable_map.setdefault(
                norm_name,
                {"label": name, "cost": 0.0, "inflation": inflation_rate},
            )
            entry["label"] = entry.get("label") or name
            entry["cost"] = float(entry["cost"]) + variable_cost
            entry["inflation"] = inflation_rate

    fixed_items = [
        FixedOpexItem(
            name=str(data["label"]),
            annual_cost=float(data["cost"]),
            inflation_rate=float(data["inflation"]),
            cost_per_mwh=0.0,
        )
        for data in sorted(fixed_map.values(), key=lambda entry: str(entry["label"]).lower())
    ]

    variable_items = [
        VariableOpexItem(
            name=f"{data['label']} Variable",
            cost_per_mwh=float(data["cost"]),
            escalation_rate=float(data["inflation"]),
        )
        for data in sorted(variable_map.values(), key=lambda entry: str(entry["label"]).lower())
    ]

    return fixed_items, variable_items


def capex_item_from_row(row: Dict[str, object], start_year: int) -> CapexItem | None:
    name = str(row.get("asset_type", "")).strip()
    if not name:
        return None

    amount = max(0.0, coerce_float(row.get("acquisition")))
    if amount <= 0 and max(0.0, coerce_float(row.get("opening_balance"))) <= 0:
        return None

    asset_life = max(0, int(round(coerce_float(row.get("asset_life"), 1.0))))
    depreciation_rate = max(0.0, min(1.0, coerce_float(row.get("depreciation_rate"), 0.0)))
    year_value = int(coerce_float(row.get("year", start_year), start_year))
    service_month = max(1, (year_value - start_year) * 12 + 1)

    return CapexItem(
        name=name,
        amount=amount,
        depreciation_years=asset_life,
        spend_profile=[1.0],
        method=str(row.get("method", "Straight-Line")),
        opening_balance=max(0.0, coerce_float(row.get("opening_balance"))),
        depreciation_rate=depreciation_rate,
        service_month=service_month,
    )


def capex_item_from_initial(row: Dict[str, object], start_year: int) -> CapexItem | None:
    name = str(row.get("name", "")).strip()
    if not name:
        return None

    amount = max(0.0, coerce_float(row.get("amount")))
    opening_balance = max(0.0, coerce_float(row.get("opening_balance")))
    if amount <= 0 and opening_balance <= 0:
        return None

    method_value = str(row.get("method", "Straight-Line")).strip() or "Straight-Line"
    depreciation_years = max(0, int(round(coerce_float(row.get("depreciation_years", 1.0), 1.0))))
    depreciation_rate = max(0.0, min(1.0, coerce_float(row.get("depreciation_rate", 0.0))))

    year_value = int(coerce_float(row.get("year", start_year), start_year))
    month_in_year = int(coerce_float(row.get("month", 1), 1.0))
    month_in_year = min(12, max(1, month_in_year))
    if year_value < start_year:
        year_value = start_year
    service_month = int(coerce_float(row.get("service_month", 1), 1.0))
    if service_month <= 0:
        service_month = (year_value - start_year) * 12 + month_in_year
    target_month = max(1, service_month)

    spend_profile_values = parse_spend_profile(row.get("spend_profile"))
    prefix_length = max(0, target_month - 1)
    spend_profile = [0.0] * prefix_length + spend_profile_values

    return CapexItem(
        name=name,
        amount=amount,
        depreciation_years=depreciation_years,
        spend_profile=spend_profile,
        method=method_value,
        opening_balance=opening_balance,
        depreciation_rate=depreciation_rate,
        service_month=max(1, service_month),
    )


def apply_energy_input_mode(
    energy: EnergyAssumptions,
    mode: str,
    *,
    capacity_factor: float,
    annual_resource_hours: float,
    monthly_generation_rows: List[Dict[str, object]],
) -> None:
    """Apply a mutually exclusive energy input mode to the energy assumptions."""

    normalized_mode = str(mode).strip().lower()
    monthly_values = [
        max(0.0, coerce_float(row.get("expected_mwh")))
        for row in monthly_generation_rows
        if row.get("expected_mwh") is not None
    ]

    energy.annual_hours = int(CALENDAR_HOURS_PER_YEAR)
    setattr(energy, "input_mode", normalized_mode)
    setattr(energy, "annual_resource_hours_input", None)

    if normalized_mode == "monthly_expected_mwh":
        if len(monthly_values) != 12:
            raise ValueError("Monthly expected MWh mode requires 12 monthly values.")
        energy.energy_model_mode = "monthly_expected_mwh"
        energy.monthly_expected_mwh = monthly_values
        annual_mwh = sum(monthly_values)
        energy.capacity_factor = expected_mwh_to_capacity_factor(energy.capacity_mw, annual_mwh)
        return

    energy.energy_model_mode = "share_based"
    energy.monthly_expected_mwh = None

    if normalized_mode == "resource_hours":
        resource_hours = max(0.0, annual_resource_hours)
        setattr(energy, "annual_resource_hours_input", resource_hours)
        energy.capacity_factor = annual_resource_hours_to_capacity_factor(resource_hours)
        return

    energy.capacity_factor = max(0.0, capacity_factor)

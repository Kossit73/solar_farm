"""Solar Farm Financial Model package with lazy attribute loading."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_ATTRS = {
    "load_assumptions": "solar_farm_financial_model.data_loader",
    "SolarFarmFinancialModel": "solar_farm_financial_model.model",
    "build_summary_report": "solar_farm_financial_model.reporting",
}

__all__ = list(_LAZY_ATTRS)


def __getattr__(name: str) -> Any:
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_LAZY_ATTRS[name])
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover - cosmetic
    return sorted(set(globals()) | set(__all__))

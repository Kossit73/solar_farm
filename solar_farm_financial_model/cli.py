"""Command line interface for running the Solar Farm Financial Model."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .data_loader import load_assumptions


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Solar Farm Financial Model")
    parser.add_argument(
        "--excel",
        type=Path,
        default=None,
        help="Optional path to an Excel workbook containing assumptions.",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory to export CSV summaries.",
    )
    return parser.parse_args(args=args)


def main(args: Optional[list[str]] = None) -> None:
    namespace = parse_args(args)
    try:
        assumptions = load_assumptions(namespace.excel)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)

    try:
        from .model import SolarFarmFinancialModel
        from .reporting import build_summary_report
    except ModuleNotFoundError as exc:
        missing = exc.name or "a required dependency"
        print(
            "Error: Missing dependency "
            f"{missing!r}. Install the packages listed in requirements.txt."
        )
        raise SystemExit(1)

    model = SolarFarmFinancialModel(assumptions)
    outputs = model.run()

    summary_tables = build_summary_report(outputs)

    export_dir = namespace.export_dir
    export_dir.mkdir(parents=True, exist_ok=True)

    outputs.monthly_results.to_csv(export_dir / "monthly_results.csv")
    outputs.annual_summary.to_csv(export_dir / "annual_summary.csv")
    for name, table in summary_tables.items():
        table.to_csv(export_dir / f"{name}.csv", index=False)

    print("Solar Farm Financial Model completed.")
    print(f"Key metrics exported to: {export_dir.resolve()}")


if __name__ == "__main__":
    main()

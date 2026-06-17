"""Workbook reporting helpers for the Solar Farm Streamlit application."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .model import ModelOutputs
from .schemas import Assumptions


def excel_title(ws, title: str, subtitle: str) -> None:
    ws.merge_cells("A1:H1")
    ws["A1"] = title
    ws["A1"].font = Font(size=18, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="0B3D91")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:H2")
    ws["A2"] = subtitle
    ws["A2"].font = Font(size=11, color="1F2D3D", italic=True)
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 22


def write_styled_table(
    ws,
    df: pd.DataFrame,
    title: str,
    start_row: int,
    start_col: int = 1,
) -> int:
    """Write a styled dataframe section and return the next available row."""

    section_row = start_row
    ws.cell(row=section_row, column=start_col, value=title)
    ws.cell(row=section_row, column=start_col).font = Font(size=13, bold=True, color="0B3D91")
    section_row += 1

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    border = Border(
        left=Side(style="thin", color="D9E2F3"),
        right=Side(style="thin", color="D9E2F3"),
        top=Side(style="thin", color="D9E2F3"),
        bottom=Side(style="thin", color="D9E2F3"),
    )

    frame = df.copy()
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.where(pd.notna(frame), None)

    for col_idx, column_name in enumerate(frame.columns, start=start_col):
        cell = ws.cell(row=section_row, column=col_idx, value=str(column_name))
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    data_start = section_row + 1
    for row_offset, values in enumerate(frame.itertuples(index=False), start=0):
        excel_row = data_start + row_offset
        for col_idx, value in enumerate(values, start=start_col):
            cell = ws.cell(row=excel_row, column=col_idx, value=value)
            cell.border = border
            column_name = str(frame.columns[col_idx - start_col]).lower()
            if isinstance(value, (int, float, np.floating)) and value is not None:
                if "irr" in column_name or "rate" in column_name or "share" in column_name:
                    cell.number_format = "0.0%"
                elif "month" in column_name and "payback" in column_name:
                    cell.number_format = "0"
                else:
                    cell.number_format = "#,##0.00;[Red]-#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            if row_offset % 2 == 1:
                cell.fill = PatternFill("solid", fgColor="F7FBFF")

    last_row = data_start + max(len(frame) - 1, 0)
    for col_idx, column_name in enumerate(frame.columns, start=start_col):
        desired = max(14, min(34, len(str(column_name)) + 4))
        for value in frame.iloc[:, col_idx - start_col].head(30):
            desired = max(desired, min(34, len(str(value)) + 2))
        ws.column_dimensions[get_column_letter(col_idx)].width = desired

    return last_row + 2


def add_workbook_overview_sheet(
    wb: Workbook,
    outputs: ModelOutputs,
    summary_tables: Dict[str, pd.DataFrame],
    assumptions: Assumptions,
    metric_labels: Dict[str, str],
) -> None:
    if "Overview" in wb.sheetnames:
        del wb["Overview"]
    ws = wb.create_sheet("Overview", 0)
    accent = "B45309"
    ws["A1"] = assumptions.global_assumptions.project_name or "Solar Farm Financial Model"
    ws["A1"].font = Font(size=20, bold=True, color="0F172A")
    ws["A2"] = "Executive overview covering key metrics, debt profile, cash flows, and analytics output."
    ws["A2"].font = Font(size=11, color="475569")
    ws["A4"] = "Executive Snapshot"
    ws["A4"].font = Font(size=12, bold=True, color=accent)
    ws["A5"] = "Metric"
    ws["B5"] = "Value"
    for cell in ws[5]:
        cell.fill = PatternFill("solid", fgColor=accent)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    metrics_df = summary_tables.get("metrics", pd.DataFrame()).copy()
    rows: List[Tuple[str, object]] = []
    if not metrics_df.empty:
        for _, metric_row in metrics_df.head(6).iterrows():
            key = metric_row.get("metric")
            label = metric_labels.get(key, str(key).replace("_", " ").title())
            rows.append((label, metric_row.get("value")))
    rows.append(("Projection Start", assumptions.global_assumptions.start_date))
    rows.append(("Forecast Months", assumptions.global_assumptions.forecast_months))
    for row_idx, (label, value) in enumerate(rows[:8], start=6):
        ws.cell(row=row_idx, column=1, value=label)
        ws.cell(row=row_idx, column=2, value=value)
    ws["D4"] = "Workbook Notes"
    ws["D4"].font = Font(size=12, bold=True, color=accent)
    notes = [
        "The detailed dashboard, statements, and analytics tabs remain intact in this export.",
        "Use this overview as the executive cover sheet for sponsor and lender circulation.",
        "Key metrics and project assumptions stay aligned to the live model run.",
    ]
    for row_idx, note in enumerate(notes, start=5):
        ws.cell(row=row_idx, column=4, value=f"- {note}")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["D"].width = 60
    ws.freeze_panes = "A6"
    ws.sheet_view.showGridLines = False

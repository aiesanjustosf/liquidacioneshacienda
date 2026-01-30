from __future__ import annotations

from io import BytesIO
from typing import Dict, Optional
import pandas as pd
import re
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def format_ar_number(value: float, decimals: int = 2) -> str:
    """Formatea número con miles '.' y decimales ',' (Argentina)."""
    try:
        v = float(value)
    except Exception:
        return str(value)
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def _col_kind(colname: str) -> str:
    up = (colname or "").upper()
    if re.search(r"(NETO|IVA|GASTO|IMPORTE|MONTO|BRUTO|TOTAL|PRECIO|COMISI|OTROS)", up):
        return "money"
    if "KILO" in up:
        return "kilos"
    if re.search(r"(CABEZA|CANTIDAD)", up):
        return "qty"
    return "text"


def df_to_pdf_bytes(df: pd.DataFrame, title: str = "Grilla") -> bytes:
    """
    Exporta un DataFrame a PDF simple (tabla). Pensado para descargas rápidas desde Streamlit.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=18, bottomMargin=18)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 10)]

    if df is None or df.empty:
        story.append(Paragraph("Sin datos.", styles["Normal"]))
        doc.build(story)
        return buffer.getvalue()

    
    # Convertimos a strings para evitar errores de render (y formatear montos estilo AR)
    kinds = [_col_kind(c) for c in df.columns]
    data = [list(df.columns)]
    for _, row in df.iterrows():
        out_row = []
        for v, k in zip(row.values, kinds):
            if pd.isna(v):
                out_row.append("")
                continue
            if isinstance(v, (int, float)) and k in ("money", "kilos"):
                out_row.append(format_ar_number(v, decimals=2))
            elif isinstance(v, (int, float)) and k == "qty":
                out_row.append(format_ar_number(v, decimals=0))
            else:
                out_row.append(str(v))
        data.append(out_row)

    table = Table(data, repeatRows=1)
    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ])
    table.setStyle(style)

    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def dfs_to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    """
    Exporta múltiples DataFrames a un solo Excel (xlsx) y aplica formato numérico.
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe_name = (name or "Hoja")[:31]
            if df is None:
                df = pd.DataFrame()
            df.to_excel(writer, sheet_name=safe_name, index=False)

            ws = writer.book[safe_name]
            # Aplicar formatos por columna (monto/cantidad/kilos)
            for j, col in enumerate(df.columns, start=1):
                kind = _col_kind(str(col))
                if kind == "money":
                    fmt = '#,##0.00'
                elif kind == "kilos":
                    fmt = '#,##0.00'
                elif kind == "qty":
                    fmt = '#,##0'
                else:
                    fmt = None
                if fmt:
                    for i in range(2, ws.max_row + 1):
                        cell = ws.cell(i, j)
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = fmt
            # Ajuste ancho columnas
            for j, col in enumerate(df.columns, start=1):
                letter = get_column_letter(j)
                ws.column_dimensions[letter].width = min(45, max(12, len(str(col)) + 2))
    return output.getvalue()

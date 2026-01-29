from __future__ import annotations

from io import BytesIO
from typing import Dict, Optional
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


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

    # Convertimos a strings para evitar errores de render
    data = [list(df.columns)]
    for _, row in df.iterrows():
        data.append([("" if pd.isna(v) else str(v)) for v in row.values])

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
    Exporta múltiples DataFrames a un solo Excel (xlsx).
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe_name = (name or "Hoja")[:31]
            if df is None:
                df = pd.DataFrame()
            df.to_excel(writer, sheet_name=safe_name, index=False)
    return output.getvalue()

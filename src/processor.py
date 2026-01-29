from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Any, List, Tuple
import pandas as pd

from .parser import ParsedDoc, ItemHacienda, Gasto
from .rules import Role, movimiento_por_regla


def _pct_from_totales(importe_bruto: float, iva_bruto: float) -> float:
    if importe_bruto and iva_bruto:
        return round((iva_bruto / importe_bruto) * 100, 2)
    return 0.0


def build_outputs(docs: List[ParsedDoc], roles: Dict[str, Role]) -> Dict[str, pd.DataFrame]:
    """
    Devuelve dataframes listos para UI y export.
    roles: dict filename -> 'EMISOR'/'RECEPTOR'
    """
    ventas_rows: List[Dict[str, Any]] = []
    compras_rows: List[Dict[str, Any]] = []
    gastos_rows: List[Dict[str, Any]] = []
    ctrl_v_detail: List[Dict[str, Any]] = []
    ctrl_c_detail: List[Dict[str, Any]] = []
    libro_ventas_rows: List[Dict[str, Any]] = []

    for d in docs:
        role = roles.get(d.filename, "RECEPTOR")
        mov = movimiento_por_regla(d.cod_arca, role)

        # Signo importes (crédito negativo, débito positivo)
        s_m = d.ajuste.signo_montos
        afecta_hacienda = True  # por default, si hay items
        # Para ajuste monetario (financiero), no tocamos cabezas/kilos, pero sí montos
        s_h = s_m if d.ajuste.afecta_cabezas_kilos else 1

        # Contraparte (para grillas)
        if mov == "VENTA":
            contraparte = d.emisor if role == "RECEPTOR" else d.receptor
        elif mov == "COMPRA":
            contraparte = d.receptor if role == "EMISOR" else d.emisor
        else:
            contraparte = d.receptor

        # Neto sin gastos (según tu regla): base hacienda = Importe Bruto (sin IVA, sin gastos)
        neto_hacienda = (d.importe_bruto or 0.0) * s_m
        iva_hacienda = (d.iva_bruto or 0.0) * s_m

        # Resumen cabezas/kilos desde items (si corresponde)
        cabezas = sum((it.cabezas or 0.0) for it in d.items) * (s_h)
        kilos = sum((it.kilos or 0.0) for it in d.items) * (s_h)

        resumen = {
            "Fecha": d.fecha,
            "Fecha Operación": d.fecha_operacion,
            "Título": d.titulo,
            "Tipo": d.tipo_interno,
            "Cód ARCA": d.cod_arca,
            "Letra": d.letra,
            "PV": d.pv,
            "Número": d.numero,
            "Ajuste": "SI" if d.ajuste.es_ajuste else "NO",
            "Ajuste sentido": d.ajuste.sentido or "",
            "Ajuste tipo": d.ajuste.tipo or "",
            "Contraparte CUIT": contraparte.cuit,
            "Contraparte": contraparte.nombre,
            "Cond IVA": contraparte.cond_iva,
            "Cabezas": cabezas,
            "Kilos": kilos,
            "Neto Hacienda (sin gastos)": neto_hacienda,
            "IVA Hacienda": iva_hacienda,
            "Gastos (sin IVA)": (d.total_gastos or 0.0) * s_m,
            "IVA Gastos": (d.iva_gastos or 0.0) * s_m,
        }

        if mov == "VENTA":
            ventas_rows.append(resumen)
        elif mov == "COMPRA":
            compras_rows.append(resumen)

        # Gastos detalle
        for g in d.gastos:
            gastos_rows.append({
                "Movimiento": mov,
                "Fecha": d.fecha,
                "Tipo": d.tipo_interno,
                "Cód ARCA": d.cod_arca,
                "PV": d.pv,
                "Número": d.numero,
                "Contraparte": contraparte.nombre,
                "Concepto": g.concepto,
                "Importe (sin IVA)": (g.importe or 0.0) * s_m,
                "IVA %": g.iva_pct or "",
                "IVA $": (g.iva_importe or 0.0) * s_m if g.iva_importe is not None else "",
            })

        # Control hacienda: sólo si hay items; monto neto sin gastos = suma de bruto de items
        if d.items:
            for it in d.items:
                row = {
                    "Tipo de Hacienda": it.categoria,
                    "Cantidad (Cabezas)": (it.cabezas or 0.0) * (s_h),
                    "Kilos": (it.kilos or 0.0) * (s_h),
                    "Monto Neto (sin gastos)": (it.bruto or 0.0) * (s_m),
                }
                if mov == "VENTA":
                    ctrl_v_detail.append(row)
                elif mov == "COMPRA":
                    ctrl_c_detail.append(row)

        # Libro IVA Ventas (solo VENTAS, sólo hacienda)
        if mov == "VENTA":
            # Determinar alícuota: por items o por totales
            neto_105 = iva_105 = neto_21 = iva_21 = exento = 0.0

            if d.items:
                for it in d.items:
                    neto = (it.bruto or 0.0) * s_m
                    iva = (it.iva_importe or 0.0) * s_m if it.iva_importe is not None else 0.0
                    pct = it.iva_pct
                    if pct is None:
                        # fallback por totales
                        pct = _pct_from_totales(d.importe_bruto or 0.0, d.iva_bruto or 0.0)
                    if pct >= 20:
                        neto_21 += neto
                        iva_21 += iva
                    elif pct > 0:
                        neto_105 += neto
                        iva_105 += iva
                    else:
                        exento += neto
            else:
                # sin items: si hay neto hacienda 0, no carga
                pass

            total = neto_105 + iva_105 + neto_21 + iva_21 + exento
            libro_ventas_rows.append({
                "Fecha": d.fecha,
                "Tipo": d.tipo_interno,
                "Cód ARCA": d.cod_arca,
                "Letra": d.letra,
                "PV": d.pv,
                "Número": d.numero,
                "CUIT Cliente": contraparte.cuit,
                "Razón Social Cliente": contraparte.nombre,
                "Cond IVA": contraparte.cond_iva,
                "Neto 10.5": round(neto_105, 2),
                "IVA 10.5": round(iva_105, 2),
                "Neto 21": round(neto_21, 2),
                "IVA 21": round(iva_21, 2),
                "Exento": round(exento, 2),
                "Total": round(total, 2),
            })

    df_ventas = pd.DataFrame(ventas_rows)
    df_compras = pd.DataFrame(compras_rows)
    df_gastos = pd.DataFrame(gastos_rows)

    # Control: pivote a resumen por tipo
    def _ctrl(df_detail: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if df_detail.empty:
            return df_detail, df_detail
        resumen = (
            df_detail
            .groupby("Tipo de Hacienda", as_index=False)
            .agg({
                "Cantidad (Cabezas)": "sum",
                "Kilos": "sum",
                "Monto Neto (sin gastos)": "sum",
            })
        )
        return df_detail, resumen

    df_ctrl_v_detail = pd.DataFrame(ctrl_v_detail)
    df_ctrl_c_detail = pd.DataFrame(ctrl_c_detail)

    dv_det, dv_res = _ctrl(df_ctrl_v_detail)
    dc_det, dc_res = _ctrl(df_ctrl_c_detail)

    df_libro_ventas = pd.DataFrame(libro_ventas_rows)

    return {
        "ventas": df_ventas,
        "compras": df_compras,
        "gastos": df_gastos,
        "ctrl_ventas_detalle": dv_det,
        "ctrl_ventas_resumen": dv_res,
        "ctrl_compras_detalle": dc_det,
        "ctrl_compras_resumen": dc_res,
        "libro_ventas": df_libro_ventas,
    }

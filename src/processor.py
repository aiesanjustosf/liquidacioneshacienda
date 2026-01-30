from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Any, List, Tuple
import pandas as pd

from .parser import ParsedDoc, ItemHacienda, Gasto
from .rules import Role, movimiento_por_regla


# Columnas de salida (mismo formato que tus plantillas Holistor / ARCA)
EMITIDOS_SALIDA_COLS = [
    "Fecha Emisión",
    "Fecha Recepción",
    "Concepto",
    "Tipo",
    "Letra",
    "Punto de Venta",
    "Número Desde",
    "Número Hasta",
    "Tipo Doc. Emisor",
    "Nro. Doc. Emisor",
    "Denominación Emisor",
    "Condición Fiscal",
    "Tipo Cambio",
    "Moneda",
    "Alicuota",
    "Neto",
    "IVA",
    "Ex/Ng",
    "Otros Conceptos",
    "Total",
]

RECIBIDOS_SALIDA_COLS = [
    "Fecha dd/mm/aaaa",
    "Cpbte",
    "Tipo",
    "Suc.",
    "Número",
    "Razón Social o Denominación Cliente",
    "Tipo Doc.",
    "CUIT",
    "Domicilio",
    "C.P.",
    "Pcia",
    "Cond Fisc",
    "Moneda",
    "Tipo de cambio",
    "Cód. Neto",
    "Neto Gravado",
    "Alíc.",
    "IVA Liquidado",
    "IVA Débito",
    "Cód. NG/EX",
    "Conceptos NG/EX",
    "Cód. P/R",
    "Perc./Ret.",
    "Pcia P/R",
    "Total",
]

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
    ventas_salida_rows: List[Dict[str, Any]] = []
    compras_gastos_salida_rows: List[Dict[str, Any]] = []

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


        # --- Ventas (formato "Emitidos Salida") ---
        if mov == "VENTA":
            # Alicuota por items o por totales
            alic = 0.0
            if d.items:
                for it in d.items:
                    if it.iva_pct is not None:
                        alic = float(it.iva_pct)
                        break
            if not alic:
                alic = float(_pct_from_totales(d.importe_bruto or 0.0, d.iva_bruto or 0.0))

            neto_col = neto_hacienda
            exng_col = 0.0
            if (d.iva_bruto or 0.0) == 0.0:
                # sin IVA => va como Ex/Ng
                exng_col = neto_hacienda
                neto_col = 0.0

            ventas_salida_rows.append({
                "Fecha Emisión": d.fecha,
                "Fecha Recepción": d.fecha_operacion or d.fecha,
                "Concepto": 141,
                "Tipo": d.tipo_interno,
                "Letra": d.letra,
                "Punto de Venta": d.pv,
                "Número Desde": d.numero,
                "Número Hasta": d.numero,
                "Tipo Doc. Emisor": "CUIT",
                "Nro. Doc. Emisor": d.emisor.cuit,
                "Denominación Emisor": d.emisor.nombre,
                "Condición Fiscal": d.emisor.cond_iva,
                "Tipo Cambio": 1,
                "Moneda": "PES",
                "Alicuota": alic if alic else "",
                "Neto": neto_col,
                "IVA": iva_hacienda,
                "Ex/Ng": exng_col,
                "Otros Conceptos": 0.0,
                "Total": (neto_col or 0.0) + (iva_hacienda or 0.0) + (exng_col or 0.0),
            })

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

            



        
        # --- Compras/Gastos (formato "Recibidos Salida") ---
        def _append_recibidos_row(*, fecha: str, cpbte: str, letra: str, suc: str, numero: str,
                                  contraparte_nombre: str, contraparte_cuit: str, cond_fisc: str,
                                  cod_neto: str, base: float, iva_pct: float | str, iva_imp: float,
                                  cod_ngex: str = "", concepto_ngex: float | str = "") -> None:
            total = (base or 0.0) + (iva_imp or 0.0)
            row = {
                "Fecha dd/mm/aaaa": fecha,
                "Cpbte": cpbte,
                "Tipo": letra,
                "Suc.": suc,
                "Número": numero,
                "Razón Social o Denominación Cliente": contraparte_nombre,
                "Tipo Doc.": "CUIT",
                "CUIT": contraparte_cuit,
                "Domicilio": "",
                "C.P.": "",
                "Pcia": "",
                "Cond Fisc": cond_fisc,
                "Moneda": "PES",
                "Tipo de cambio": 1,
                "Cód. Neto": cod_neto,
                "Neto Gravado": base if (iva_imp or 0.0) != 0.0 else 0.0,
                "Alíc.": iva_pct if (iva_imp or 0.0) != 0.0 else "",
                "IVA Liquidado": iva_imp if (iva_imp or 0.0) != 0.0 else "",
                "IVA Débito": 0.0,
                "Cód. NG/EX": cod_ngex if (iva_imp or 0.0) == 0.0 else "",
                "Conceptos NG/EX": concepto_ngex if (iva_imp or 0.0) == 0.0 else "",
                "Cód. P/R": "",
                "Perc./Ret.": "",
                "Pcia P/R": "",
                "Total": total,
            }
            compras_gastos_salida_rows.append(row)

        # Línea 525 (valor hacienda) SOLO para comprobantes clasificados como COMPRA
        if mov == "COMPRA":
            base = neto_hacienda
            iva_imp = iva_hacienda
            alic = _pct_from_totales(d.importe_bruto or 0.0, d.iva_bruto or 0.0)
            if base != 0.0:
                if (iva_imp or 0.0) == 0.0:
                    _append_recibidos_row(
                        fecha=d.fecha,
                        cpbte=d.tipo_interno,
                        letra=d.letra,
                        suc=d.pv,
                        numero=d.numero,
                        contraparte_nombre=contraparte.nombre,
                        contraparte_cuit=contraparte.cuit,
                        cond_fisc=contraparte.cond_iva,
                        cod_neto="525",
                        base=base,
                        iva_pct="",
                        iva_imp=0.0,
                        cod_ngex="EX",
                        concepto_ngex=base,
                    )
                else:
                    _append_recibidos_row(
                        fecha=d.fecha,
                        cpbte=d.tipo_interno,
                        letra=d.letra,
                        suc=d.pv,
                        numero=d.numero,
                        contraparte_nombre=contraparte.nombre,
                        contraparte_cuit=contraparte.cuit,
                        cond_fisc=contraparte.cond_iva,
                        cod_neto="525",
                        base=base,
                        iva_pct=alic if alic else "",
                        iva_imp=iva_imp,
                    )

        # Línea 400 (gastos) para compras y también incluir gastos de ventas
        if (d.total_gastos or 0.0) != 0.0:
            base_g = (d.total_gastos or 0.0) * s_m
            iva_g = (d.iva_gastos or 0.0) * s_m
            alic_g = round((iva_g / base_g) * 100, 2) if base_g else ""
            _append_recibidos_row(
                fecha=d.fecha,
                cpbte="ND",
                letra="A",
                suc=d.pv,
                numero=d.numero,
                contraparte_nombre=contraparte.nombre,
                contraparte_cuit=contraparte.cuit,
                cond_fisc=contraparte.cond_iva,
                cod_neto="400",
                base=base_g,
                iva_pct=alic_g if iva_g else "",
                iva_imp=iva_g if iva_g else 0.0,
            )


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

    df_ventas_salida = pd.DataFrame(ventas_salida_rows, columns=EMITIDOS_SALIDA_COLS)
    df_compras_gastos_salida = pd.DataFrame(compras_gastos_salida_rows, columns=RECIBIDOS_SALIDA_COLS)

    return {
        "ventas": df_ventas,
        "compras": df_compras,
        "gastos": df_gastos,
        "ctrl_ventas_detalle": dv_det,
        "ctrl_ventas_resumen": dv_res,
        "ctrl_compras_detalle": dc_det,
        "ctrl_compras_resumen": dc_res,
        "libro_ventas": df_libro_ventas,
        "ventas_salida": df_ventas_salida,
        "compras_gastos_salida": df_compras_gastos_salida,
    }

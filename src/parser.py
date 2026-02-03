from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
import re
import pdfplumber

from .rules import detectar_ajuste, tipo_interno_por_cod, condicion_iva_abreviar


def normalize_text(txt: str) -> str:
    """Normaliza texto extraído para reducir cortes de números y espacios raros."""
    if not txt:
        return ""
    t = txt

    # Une números cortados por salto de línea, ej: "1,876,895.\n78" => "1,876,895.78"
    t = re.sub(r"(\d[\d,]*\.)\s*\n\s*(\d{1,3})\b", r"\1\2", t)
    # Une casos tipo "1,500,000.0\n0" => "1,500,000.00"
    t = re.sub(r"(\d[\d,]*\.\d)\s*\n\s*(\d)\b", r"\1\2", t)

    # Normaliza espacios
    t = re.sub(r"[ \t]+", " ", t)
    return t


def parse_money(s: str) -> Optional[float]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace("$", "").replace(" ", "")
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def parse_int(s: str) -> Optional[int]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return int(float(s))
    except Exception:
        return None


def money_tokens(line: str) -> List[str]:
    """
    Devuelve importes monetarios tipo 1,234.56 o 950.00.
    Excluye alícuotas típicas (10.50, 21.00, 27.00, 0.00) cuando aparecen en la línea.
    """
    toks = re.findall(r"\b\d[\d,]*\.\d{2,3}\b", line)
    excl = {"10.50", "21.00", "27.00", "0.00"}
    return [t for t in toks if t not in excl]


def _find_one(pattern: str, text: str, group: int = 1, flags=re.IGNORECASE) -> str:
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


@dataclass
class Party:
    cuit: str = ""
    nombre: str = ""
    cond_iva_raw: str = ""
    cond_iva: str = ""  # RI/MT/EX
    iibb: str = ""

    def as_dict(self, prefix: str) -> Dict[str, Any]:
        return {
            f"{prefix}_cuit": self.cuit,
            f"{prefix}_nombre": self.nombre,
            f"{prefix}_cond_iva": self.cond_iva,
            f"{prefix}_cond_iva_raw": self.cond_iva_raw,
            f"{prefix}_iibb": self.iibb,
        }


@dataclass
class ItemHacienda:
    categoria: str
    cabezas: float
    kilos: float
    um: str
    precio: float
    bruto: float
    iva_pct: Optional[float] = None
    iva_importe: Optional[float] = None


@dataclass
class Gasto:
    concepto: str
    base: Optional[float]
    alicuota: Optional[float]
    importe: float
    iva_pct: Optional[float]
    iva_importe: Optional[float]


@dataclass
class ParsedDoc:
    filename: str
    cod_arca: int
    letra: str
    pv: str
    numero: str
    titulo: str
    fecha: str
    fecha_operacion: str
    emisor: Party
    receptor: Party
    tipo_interno: str
    ajuste: Any  # Ajuste dataclass
    # Totales
    importe_bruto: float
    iva_bruto: float
    total_gastos: float
    iva_gastos: float
    importe_neto: float
    retenciones: List[Tuple[str, float]]
    # Detalle
    items: List[ItemHacienda]
    gastos: List[Gasto]


def extract_full_text(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        parts = []
        for p in pdf.pages:
            parts.append(p.extract_text() or "")
    return normalize_text("\n".join(parts))


def parse_parties(text: str) -> Tuple[Party, Party]:
    """
    Extrae EMISOR y RECEPTOR.
    En PDFs LSP/ARCA, el EMISOR suele figurar inmediatamente después de la línea "Cód. XXX"
    y antes de "Fecha ...", mientras que el RECEPTOR se encuentra en el bloque que inicia con "Receptor".
    """
    emisor = Party()
    receptor = Party()

    # --- Split por bloque Receptor ---
    m_rec = re.search(r"\bReceptor\b", text, re.IGNORECASE)
    emisor_block = text[: m_rec.start()] if m_rec else text
    receptor_block = text[m_rec.start():] if m_rec else ""

    # --- Emisor ---
    lines = [ln.strip() for ln in emisor_block.splitlines() if ln.strip()]
    idx_cod = next((i for i, ln in enumerate(lines) if re.search(r"\bC[óo]d\.?\b", ln, re.IGNORECASE)), None)

    nombre = ""
    if idx_cod is not None:
        # Caso frecuente: la razón social está ANTES de "Cód." en la misma línea
        ln_cod = lines[idx_cod]
        m_cod = re.search(r"\bC[óo]d\.?\s*\d+\b", ln_cod, re.IGNORECASE)
        if m_cod:
            pre = ln_cod[:m_cod.start()].strip()
            up_pre = pre.upper()
            if pre and "ORIGINAL" not in up_pre and "LIQUID" not in up_pre:
                nombre = pre

        # Continuación en la línea siguiente (ej: "ANONIMA")
        for j in range(idx_cod + 1, min(idx_cod + 4, len(lines))):
            cand = lines[j].strip()
            up = cand.upper()
            if up.startswith("FECHA"):
                break
            if "CUIT" in up or "INGRESOS BRUTOS" in up:
                break
            if any(k in up for k in ["RECEPTOR", "ORIGINAL", "LIQUIDACIÓN", "LIQUIDACION", "N°", "Nº", "COD.", "CÓD."]):
                continue
            if nombre:
                nombre = f"{nombre} {cand}".strip()
            else:
                nombre = cand
            break
    if not nombre:
        nombre = _find_one(r"(?:Raz[oó]n Social|Nombre y Apellido):\s*([A-Z0-9\.\-\sÁÉÍÓÚÑáéíóúñ]+?)(?:\n|CUIT:|Situaci|$)", emisor_block)

    emisor.nombre = re.sub(r"\s+Fecha\b.*$", "", nombre.strip(), flags=re.IGNORECASE)
    emisor.cuit = _find_one(r"CUIT:\s*([0-9]{11})", emisor_block)
    emisor.iibb = _find_one(r"Ingresos Brutos:\s*([A-Z0-9\-\.\s]*)", emisor_block)
    emisor.cond_iva_raw = _find_one(r"Condicion frente al IVA:\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]+)", emisor_block)
    emisor.cond_iva = condicion_iva_abreviar(emisor.cond_iva_raw)

    # --- Receptor ---
    m = re.search(r"Receptor(.*?)(Fecha Operaci[oó]n:|Fecha Operacion:)", receptor_block, re.IGNORECASE | re.DOTALL)
    rb = m.group(1) if m else receptor_block

    receptor.cuit = _find_one(r"CUIT:\s*([0-9]{11})", rb)
    receptor.nombre = _find_one(r"(?:Nombre y Apellido|Raz[oó]n Social):\s*([A-Z0-9\.\-\sÁÉÍÓÚÑáéíóúñ]+?)(?:\n|CUIT:|Situaci|$)", rb, group=1)
    receptor.cond_iva_raw = _find_one(r"(?:Situaci[oó]n IVA|Situación IVA):\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]+)", rb, group=1)
    receptor.cond_iva = condicion_iva_abreviar(receptor.cond_iva_raw)
    receptor.iibb = _find_one(r"N[°º] IIBB:\s*([A-Z0-9\-\.\s]*)", rb)

    return emisor, receptor

def parse_header(text: str) -> Dict[str, str]:
    titulo = _find_one(r"ORIGINAL\s+[AB]\s+(.+?)\s+N[°º]", text)
    if not titulo:
        first_lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:3]
        titulo = " ".join(first_lines)

    cod = _find_one(r"C[oó]d\.\s*([0-9]{3})", text)
    letra = _find_one(r"ORIGINAL\s+([AB])", text)
    pv = ""
    numero = ""
    m = re.search(r"N[°º]\s*([0-9]{5})-([0-9]{8})", text)
    if m:
        pv, numero = m.group(1), m.group(2)

    fecha = _find_one(r"Fecha\s+([0-9]{2}/[0-9]{2}/[0-9]{4})", text)
    fecha_operacion = _find_one(r"Fecha Operaci[oó]n:([0-9]{2}/[0-9]{2}/[0-9]{4})", text)

    return {
        "titulo": titulo.strip(),
        "cod_arca": cod.strip(),
        "letra": letra.strip(),
        "pv": pv.strip(),
        "numero": numero.strip(),
        "fecha": fecha.strip(),
        "fecha_operacion": fecha_operacion.strip(),
    }



def parse_retenciones(text: str) -> List[Tuple[str, float]]:
    """Busca retenciones/tributos relevantes para exportar en Ventas (Otros conceptos).
    Devuelve lista de (concepto, importe). Importes siempre positivos (signo se aplica en processor si corresponde).
    """
    out: List[Tuple[str, float]] = []
    patterns = [
        (r"Ret\.?\s*Gananc\w*\s*[:\-]?\s*\$?\s*([0-9\.,]+)", "Ret. Ganancias"),
        (r"Ret\.?\s*Imp\.?\s*Nacion\w*\s*[:\-]?\s*\$?\s*([0-9\.,]+)", "Ret. Imp. Nacionales"),
        (r"Imp\.?\s*Nacion\w*\s*Ret\.?\s*[:\-]?\s*\$?\s*([0-9\.,]+)", "Ret. Imp. Nacionales"),
    ]
    for rgx, label in patterns:
        for m in re.finditer(rgx, text, flags=re.IGNORECASE):
            amt = parse_money(m.group(1)) or 0.0
            if amt:
                out.append((label, float(amt)))
    # dedup (sum by label)
    if out:
        agg: Dict[str, float] = {}
        for k, v in out:
            agg[k] = agg.get(k, 0.0) + float(v)
        out = [(k, v) for k, v in agg.items()]
    return out

def parse_totales(text: str) -> Dict[str, float]:
    def money_after(label: str) -> float:
        m = re.search(label + r"\s*\$?\s*([0-9][0-9,]*\.[0-9]{2})", text, re.IGNORECASE)
        return parse_money(m.group(1)) if m else 0.0

    return {
        "importe_bruto": money_after(r"Importe Bruto:"),
        "iva_bruto": money_after(r"IVA s/Bruto:"),
        "total_gastos": money_after(r"Total Gastos:"),
        "iva_gastos": money_after(r"IVA s/Gastos:"),
        "importe_neto": money_after(r"Importe Neto:"),
    }


def _text_only_category(line: str) -> str:
    # Quita importes monetarios y números sueltos, dejando texto/categoría
    # Elimina prefijos tipo '305041318889 - NOMBRE ...' (cliente) que aparecen en algunas cuentas de venta.
    line = re.sub(r'^\s*\d{11}\s*-\s*', '', line)
    t = re.sub(r"\b\d[\d,]*\.\d{2}\b", " ", line)  # importes
    t = re.sub(r"\b\d[\d,]*\b", " ", t)  # enteros
    t = re.sub(r"\bKg\.?\s*Vivo\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bCabeza\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bUN(?:ID(?:AD(?:ES)?)?)?\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\.\s*", " ", t)  # puntos sueltos por cortes de importes
    t = re.sub(r"\s{2,}", " ", t).strip(" -/")
    return t.strip()


def parse_items(text: str) -> List[ItemHacienda]:
    items: List[ItemHacienda] = []

    start = re.search(r"Categor[ií]a\s*/\s*Raza", text, re.IGNORECASE)
    end = re.search(r"Importe Bruto:", text, re.IGNORECASE)
    if not start or not end or end.start() <= start.end():
        return items

    # El bloque de items termina antes de 'Gastos' (para evitar que entren comisión/base imponible como hacienda)
    between = text[start.start(): end.start()]
    g = re.search(r"\bGastos\b", between, re.IGNORECASE)
    if g:
        between = between[: g.start()]
    block = between
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

    header_idx = next((i for i, ln in enumerate(lines) if re.search(r"Categor[ií]a\s*/\s*Raza", ln, re.IGNORECASE)), None)
    if header_idx is None:
        return items

    data_lines = lines[header_idx + 1:]

    # Merge robusto: junta líneas cuando la categoría/precio está en una línea y la UM en la siguiente
    merged: List[str] = []
    i = 0
    while i < len(data_lines):
        cur = data_lines[i]
        nxt = data_lines[i + 1] if i + 1 < len(data_lines) else ""

        cur_has_um = bool(re.search(r"Kg\.?\s*Vivo|\bCabeza\b", cur, re.IGNORECASE))
        nxt_has_um = bool(re.search(r"Kg\.?\s*Vivo|\bCabeza\b", nxt, re.IGNORECASE))

        if (not cur_has_um) and nxt_has_um:
            combined = f"{cur} {nxt}".strip()
            i += 2
            # tercera línea de texto (raza/categoría) sin importes, ej: "Brangus 0"
            if i < len(data_lines):
                third = data_lines[i]
                if (len(money_tokens(third)) == 0) and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", third):
                    combined = f"{combined} {third}".strip()
                    i += 1
            merged.append(combined)
            continue

        # fallback: si la línea es muy corta (pocos números), pegarla con la anterior
        if merged:
            digits = re.findall(r"\d", cur)
            if len(digits) < 3 and len(money_tokens(cur)) == 0:
                merged[-1] = f"{merged[-1]} {cur}".strip()
                i += 1
                continue

        # Si la línea siguiente parece continuar la categoría (texto) sin importes, la anexamos
        if i + 1 < len(data_lines):
            nxt = data_lines[i + 1].strip()
            if nxt and re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", nxt) and len(money_tokens(nxt)) == 0:
                if len(money_tokens(cur)) > 0 and not re.search(r"^(Datos\s+Adicionales|VENCIMIENTO)\b", nxt, re.IGNORECASE):
                    cur = f"{cur} {nxt}".strip()
                    i += 1

        merged.append(cur)
        i += 1

    for ln in merged:
        # Detectar UM
        um = ""
        if re.search(r"Kg\.?\s*Vivo", ln, re.IGNORECASE):
            um = "Kg Vivo"
        elif re.search(r"\bCabeza\b", ln, re.IGNORECASE):
            um = "Cabeza"
        elif re.search(r"\bUN(?:ID(?:AD(?:ES)?)?)?\b|\bUNIDADES?\b|\bUNIDAD\b", ln, re.IGNORECASE):
            um = "Unidad"

        # IVA pct
        iva_pct = None
        m_pct = re.search(r"\b(10\.50|21\.00|27\.00|0\.00)\b", ln)
        if m_pct:
            iva_pct = float(m_pct.group(1))

        monies = money_tokens(ln)

        # precio, bruto, iva (si aplica)
        precio = bruto = 0.0
        iva_imp = None

        vals = []
        for mny in monies:
            v = parse_money(mny)
            if v is not None:
                vals.append(float(v))

        if iva_pct is not None:
            if len(vals) >= 2:
                # Heurística robusta: en tablas con columnas desalineadas, tomamos:
                # - bruto = mayor
                # - iva  = segundo mayor
                # - precio = menor (si existe)
                vals_sorted = sorted(vals)
                bruto = vals_sorted[-1]
                iva_imp = vals_sorted[-2] if len(vals_sorted) >= 2 else None
                precio = vals_sorted[0] if len(vals_sorted) >= 3 else 0.0
            else:
                continue
        else:
            if len(vals) >= 1:
                vals_sorted = sorted(vals)
                bruto = vals_sorted[-1]
                precio = vals_sorted[0] if len(vals_sorted) >= 2 else 0.0
            else:
                continue

        cabezas = 0.0
        kilos = 0.0

        if um.lower().startswith("kg"):
            m = re.search(r"\s(\d{1,5})\s+Kg\.?\s*Vivo\s+(\d[\d,]*)", ln, re.IGNORECASE)
            if m:
                cabezas = float(parse_int(m.group(1)) or 0)
                kilos = float(parse_int(m.group(2)) or 0)
            else:
                m2 = re.search(r"\b(\d{1,5})\s+Kg\.?\s*Vivo\b", ln, re.IGNORECASE)
                if m2:
                    cabezas = float(parse_int(m2.group(1)) or 0)
                m3 = re.search(r"Kg\.?\s*Vivo\s+(\d[\d,]*)", ln, re.IGNORECASE)
                if m3:
                    kilos = float(parse_int(m3.group(1)) or 0)

        elif um.lower().startswith("cabeza"):
            m = re.search(r"\bCabeza\s+(\d[\d,]*)", ln, re.IGNORECASE)
            if m:
                cabezas = float(parse_int(m.group(1)) or 0)
            kilos = 0.0

        elif um.lower().startswith("unidad"):
            m = re.search(r"\bUN(?:ID(?:AD(?:ES)?)?)?\b\s+(\d[\d,]*)", ln, re.IGNORECASE)
            if m:
                cabezas = float(parse_int(m.group(1)) or 0)
            kilos = 0.0

        else:
            # fallback: usar cantidad asociada a la UM como "cabezas" cuando no hay kilos
            if um:
                m4 = re.search(rf"\b{re.escape(um)}\b\s+(\d[\d,]*)", ln, re.IGNORECASE)
                if m4:
                    cabezas = float(parse_int(m4.group(1)) or 0)
        categoria = _text_only_category(ln)
        if not categoria:
            continue

        # Filtro anti-gastos: nunca incluir comisión/base imponible/IVA en items de hacienda
        if re.search(r"\b(Comisi[oó]n|Gastos?|Base\s+Imponible|Alicuota|Al[ií]cuota|IVA\b|Importe\s+IVA)\b", categoria, re.IGNORECASE):
            continue

        items.append(
            ItemHacienda(
                categoria=categoria,
                cabezas=cabezas,
                kilos=kilos,
                um=um,
                precio=precio,
                bruto=bruto,
                iva_pct=iva_pct,
                iva_importe=iva_imp,
            )
        )

    return items



def parse_items_from_pdf(pdf_path: str) -> List[ItemHacienda]:
    """Extrae el detalle de animales desde la tabla del PDF usando pdfplumber.

    Esta vía es la más confiable porque respeta columnas (evita mezclar 'Cliente' con 'Categoría/Raza').
    Si no se encuentra la tabla, devuelve [] y el caller puede usar el fallback por texto.
    """
    items: List[ItemHacienda] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            best_table = None
            best_score = -1
            for page in pdf.pages[:2]:
                for t in page.extract_tables() or []:
                    if not t or not t[0]:
                        continue
                    header = [(c or "").strip() for c in t[0]]
                    header_join = " | ".join(header)
                    if not re.search(r"Categor[ií]a\s*/\s*Raza", header_join, re.IGNORECASE):
                        continue
                    score = sum(
                        1
                        for h in header
                        if re.search(
                            r"(Cabezas|\bUM\b|Cantidad|\$\s*Bruto|%\s*IVA|\$\s*IVA|\$\s*UM|Cliente)",
                            h,
                            re.IGNORECASE,
                        )
                    )
                    score = score * 100 + len(t)
                    if score > best_score:
                        best_score = score
                        best_table = t

            if not best_table:
                return items

            header = [(c or "").strip() for c in best_table[0]]

            def idx_of(patterns):
                for i, h in enumerate(header):
                    for p in patterns:
                        if re.search(p, h, re.IGNORECASE):
                            return i
                return None

            idx_categoria = idx_of([r"Categor[ií]a\s*/\s*Raza"])
            idx_cabezas = idx_of([r"\bCabezas\b"])
            idx_um = idx_of([r"\bUM\b"])
            idx_cantidad = idx_of([r"\bCantidad\b"])
            idx_precio = idx_of([r"\$\s*UM", r"\$\s*U\.?M\.?"])
            idx_bruto = idx_of([r"\$\s*Bruto", r"\bBruto\b"])
            idx_iva_pct = idx_of([r"%\s*IVA", r"\bIVA\b\s*%"])
            idx_iva_imp = idx_of([r"\$\s*IVA"])

            if idx_categoria is None or idx_cabezas is None or idx_um is None or idx_bruto is None:
                return items

            for row in best_table[1:]:
                if not row or idx_categoria >= len(row):
                    continue
                cat_raw = (row[idx_categoria] or "").strip()
                if not cat_raw:
                    continue

                categoria = re.sub(r"\s+", " ", cat_raw).strip()
                categoria = re.sub(r"^\s*\d{11}\s*-\s*", "", categoria).strip()

                if re.search(
                    r"\b(Comisi[oó]n|Gastos?|Base\s+Imponible|Alicuota|Al[ií]cuota|IVA\b|Importe\s+IVA)\b",
                    categoria,
                    re.IGNORECASE,
                ):
                    continue

                cabezas = float(parse_int((row[idx_cabezas] or '').strip()) or 0)

                um_raw = (row[idx_um] or "").strip()
                um = re.sub(r"\s+", " ", um_raw).strip()
                um = um.replace("Kg.", "Kg").replace("Kgs", "Kg")
                if re.search(r"Kg\s*Vivo", um, re.IGNORECASE):
                    um = "Kg Vivo"
                elif re.search(r"\bCabeza\b", um, re.IGNORECASE):
                    um = "Cabeza"
                elif re.search(r"\bUN\b|Unidad|Unidades", um, re.IGNORECASE):
                    um = "Unidad"

                kilos = 0.0
                if idx_cantidad is not None and idx_cantidad < len(row):
                    kilos = float(parse_int((row[idx_cantidad] or '').strip()) or 0)

                precio = 0.0
                if idx_precio is not None and idx_precio < len(row):
                    precio = float(parse_money((row[idx_precio] or '').strip()) or 0.0)

                bruto = float(parse_money((row[idx_bruto] or '').strip()) or 0.0)

                iva_pct = None
                if idx_iva_pct is not None and idx_iva_pct < len(row):
                    s = (row[idx_iva_pct] or "").strip()
                    if s:
                        try:
                            iva_pct = float(s.replace(",", "").replace("%", ""))
                        except Exception:
                            iva_pct = None

                iva_imp = None
                if idx_iva_imp is not None and idx_iva_imp < len(row):
                    s = (row[idx_iva_imp] or "").strip()
                    iva_imp = float(parse_money(s) or 0.0) if s else None

                items.append(
                    ItemHacienda(
                        categoria=categoria,
                        cabezas=cabezas,
                        kilos=kilos,
                        um=um,
                        precio=precio,
                        bruto=bruto,
                        iva_pct=iva_pct,
                        iva_importe=iva_imp,
                    )
                )

    except Exception:
        return []

    return items

def parse_gastos(text: str) -> List[Gasto]:
    gastos: List[Gasto] = []
    m = re.search(r"Gastos\s+.*?\n(.*?)\nImporte Bruto:", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return gastos
    block = m.group(1)
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    for ln in lines:
        concepto = re.sub(r"\s+\d.*$", "", ln).strip() or "Gasto"
        m_pct = re.search(r"\b(10\.50|21\.00|27\.00|0\.00)\b", ln)
        iva_pct = float(m_pct.group(1)) if m_pct else None

        monies = money_tokens(ln)
        # Esperado: [importe, iva] o [base, importe, iva] etc. Tomamos los 2 últimos.
        if len(monies) >= 2:
            importe = parse_money(monies[-2]) or 0.0
            iva_imp = parse_money(monies[-1]) or 0.0
            gastos.append(Gasto(concepto=concepto, base=None, alicuota=None, importe=importe, iva_pct=iva_pct, iva_importe=iva_imp))
        elif len(monies) == 1:
            importe = parse_money(monies[-1]) or 0.0
            gastos.append(Gasto(concepto=concepto, base=None, alicuota=None, importe=importe, iva_pct=iva_pct, iva_importe=None))
    return gastos


def parse_pdf(pdf_path: str) -> ParsedDoc:
    text = extract_full_text(pdf_path)
    hdr = parse_header(text)
    cod_arca = int(hdr.get("cod_arca") or 0)
    emisor, receptor = parse_parties(text)
    ajuste = detectar_ajuste(text)
    tipo_interno = tipo_interno_por_cod(cod_arca, text)
    tot = parse_totales(text)
    items = parse_items_from_pdf(pdf_path) or parse_items(text)
    gastos = parse_gastos(text)
    retenciones = parse_retenciones(text)

    return ParsedDoc(
        filename=pdf_path.split("/")[-1],
        cod_arca=cod_arca,
        letra=hdr.get("letra") or "",
        pv=hdr.get("pv") or "",
        numero=hdr.get("numero") or "",
        titulo=hdr.get("titulo") or "",
        fecha=hdr.get("fecha") or "",
        fecha_operacion=hdr.get("fecha_operacion") or "",
        emisor=emisor,
        receptor=receptor,
        tipo_interno=tipo_interno,
        ajuste=ajuste,
        importe_bruto=tot["importe_bruto"],
        iva_bruto=tot["iva_bruto"],
        total_gastos=tot["total_gastos"],
        iva_gastos=tot["iva_gastos"],
        importe_neto=tot["importe_neto"],
        retenciones=retenciones,
        items=items,
        gastos=gastos,
    )
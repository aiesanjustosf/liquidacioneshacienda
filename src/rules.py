from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal
import re

Role = Literal["EMISOR", "RECEPTOR"]
Movimiento = Literal["VENTA", "COMPRA", "NEUTRO"]


@dataclass
class Ajuste:
    """Describe si el comprobante es un ajuste y cómo impacta."""

    es_ajuste: bool
    sentido: Optional[Literal["CREDITO", "DEBITO"]] = None
    tipo: Optional[Literal["FISICO", "MONETARIO"]] = None

    @property
    def signo_montos(self) -> int:
        """Signo para importes: crédito = -1, débito = +1, no ajuste = +1."""
        if not self.es_ajuste:
            return 1
        return -1 if self.sentido == "CREDITO" else 1

    @property
    def afecta_cabezas_kilos(self) -> bool:
        """Sólo el ajuste físico afecta cabezas y kilos."""
        return self.es_ajuste and self.tipo == "FISICO"


def detectar_ajuste(texto: str) -> Ajuste:
    t = texto.upper()
    if "AJUSTE" not in t:
        return Ajuste(False)

    # Sentido
    sentido: Optional[Literal["CREDITO", "DEBITO"]] = None
    if "CRÉDITO" in t or "CREDITO" in t:
        sentido = "CREDITO"
    elif "DÉBITO" in t or "DEBITO" in t:
        sentido = "DEBITO"

    # Tipo
    tipo: Optional[Literal["FISICO", "MONETARIO"]] = None
    if "AJUSTE FÍSICO" in t or "AJUSTE FISICO" in t:
        tipo = "FISICO"
    elif "AJUSTE FINANCIERO" in t or "AJUSTE MONETARIO" in t:
        tipo = "MONETARIO"

    return Ajuste(True, sentido=sentido, tipo=tipo)


def movimiento_por_regla(cod_arca: int, role: Role) -> Movimiento:
    """Aplica las reglas de negocio que definiste para decidir si es compra o venta."""
    if cod_arca in (186, 188):
        # Liquidación compra directa
        return "COMPRA" if role == "EMISOR" else "VENTA"

    if cod_arca == 180:
        # Cuenta de venta: emisor consignataria, receptor vendedor
        return "VENTA" if role == "RECEPTOR" else "NEUTRO"

    if cod_arca in (183, 185):
        # Liquidación de compra: emisor consignataria, receptor comprador
        return "COMPRA" if role == "RECEPTOR" else "NEUTRO"

    if cod_arca in (190, 191):
        # Venta directa
        return "VENTA" if role == "EMISOR" else "COMPRA"

    return "NEUTRO"


def tipo_interno_por_cod(cod_arca: int, texto: str) -> str:
    t = texto.upper()
    # Ajustes: CN / LA / LN según vos
    if cod_arca in (186, 188):
        if "AJUSTE" in t and ("CRÉDITO" in t or "CREDITO" in t):
            return "CN"  # Nota de crédito
        return "CD"

    if cod_arca == 180:
        if "AJUSTE" in t and ("CRÉDITO" in t or "CREDITO" in t):
            return "LA"
        return "CV"

    if cod_arca in (183, 185):
        if "AJUSTE" in t and ("CRÉDITO" in t or "CREDITO" in t):
            return "LN"
        return "LC"

    if cod_arca in (190, 191):
        if "AJUSTE" in t and ("CRÉDITO" in t or "CREDITO" in t):
            return "CN"
        return "VC"

    return "OTRO"


def condicion_iva_abreviar(texto: str) -> str:
    t = (texto or "").upper()
    if "MONOTRIB" in t:
        return "MT"
    if "EXENT" in t:
        return "EX"
    if "RESPONSABLE" in t and "INSCRIP" in t:
        return "RI"
    # fallbacks
    if "IVA" in t and "RESP" in t:
        return "RI"
    return ""

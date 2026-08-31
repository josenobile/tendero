"""Capa de dominio pura: reglas colombianas sin red, disco ni reloj del sistema.

Todo lo que decide si una venta es legal, cuanto cuesta y como se paga vive
aqui y se puede probar con pytest sin levantar nada. La capa WebMCP encima solo
traduce estas funciones a herramientas que el agente del navegador puede
invocar.
"""

from __future__ import annotations

from tendero.domain import catalogo, dinero, documento, envio, errores, impuesto, pago, retracto

__all__ = [
    "catalogo",
    "dinero",
    "documento",
    "envio",
    "errores",
    "impuesto",
    "pago",
    "retracto",
]

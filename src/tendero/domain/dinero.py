"""Aritmetica monetaria en centavos de peso colombiano.

El dinero se representa como ``int`` de centavos y nunca como ``float`` porque
la DIAN valida que la suma de los impuestos linea a linea coincida exactamente
con el total del documento electronico: medio centavo de deriva por linea
rechaza la factura completa. El redondeo se hace explicito (ROUND_HALF_UP, el
criterio del articulo 802 del Estatuto Tributario) en un solo lugar.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

__all__ = [
    "CENTAVOS_POR_PESO",
    "MULTIPLO_EFECTIVO",
    "Centavos",
    "a_pesos",
    "aplicar_tarifa",
    "de_pesos",
    "formatear_cop",
    "redondear_a_pesos",
    "redondear_efectivo",
    "reparto_proporcional",
]

type Centavos = int
"""Un entero de centavos de COP. 1_000_00 son mil pesos."""

CENTAVOS_POR_PESO: Final = 100

MULTIPLO_EFECTIVO: Final[Centavos] = 50 * CENTAVOS_POR_PESO
"""La moneda mas pequena en circulacion es la de cincuenta pesos.

El pago en efectivo (y por tanto el contraentrega) se redondea a ese multiplo
porque el mensajero no puede dar cambio por debajo de el.
"""

_UN_CENTAVO: Final = Decimal(1)


def aplicar_tarifa(base: Centavos, tarifa: Decimal) -> Centavos:
    """Aplica una tarifa fraccionaria a una base y redondea a centavo entero."""
    bruto = Decimal(base) * tarifa
    return int(bruto.quantize(_UN_CENTAVO, rounding=ROUND_HALF_UP))


def redondear_a_pesos(monto: Centavos) -> Centavos:
    """Lleva el monto al peso entero mas cercano (los centavos no circulan)."""
    pesos = (Decimal(monto) / CENTAVOS_POR_PESO).quantize(_UN_CENTAVO, rounding=ROUND_HALF_UP)
    return int(pesos) * CENTAVOS_POR_PESO


def redondear_efectivo(monto: Centavos, multiplo: Centavos = MULTIPLO_EFECTIVO) -> Centavos:
    """Redondea al multiplo pagable en efectivo mas cercano.

    Se usa para el contraentrega: el valor a recaudar tiene que ser una cifra
    que el cliente pueda entregar y el mensajero devolver con monedas reales.
    """
    if multiplo <= 0:
        msg = "el multiplo de redondeo debe ser positivo"
        raise ValueError(msg)
    unidades = (Decimal(monto) / multiplo).quantize(_UN_CENTAVO, rounding=ROUND_HALF_UP)
    return int(unidades) * multiplo


def a_pesos(monto: Centavos) -> Decimal:
    """Convierte centavos a pesos con dos decimales exactos."""
    return (Decimal(monto) / CENTAVOS_POR_PESO).quantize(Decimal("0.01"))


def de_pesos(pesos: Decimal | int | str) -> Centavos:
    """Convierte una cifra en pesos a centavos enteros."""
    valor = Decimal(pesos) * CENTAVOS_POR_PESO
    return int(valor.quantize(_UN_CENTAVO, rounding=ROUND_HALF_UP))


def formatear_cop(monto: Centavos, *, con_centavos: bool = False) -> str:
    """Formatea en la convencion colombiana: punto de miles, coma decimal."""
    negativo = monto < 0
    absoluto = abs(monto)
    pesos, centavos = divmod(absoluto, CENTAVOS_POR_PESO)
    entero = f"{pesos:,}".replace(",", ".")
    cuerpo = f"{entero},{centavos:02d}" if con_centavos else entero
    signo = "-" if negativo else ""
    return f"{signo}$ {cuerpo}"


def reparto_proporcional(total: Centavos, pesos_relativos: tuple[int, ...]) -> tuple[Centavos, ...]:
    """Reparte ``total`` entre n destinos sin perder ni inventar centavos.

    Se necesita para prorratear un descuento o el flete sobre lineas con
    regimenes de IVA distintos: si el reparto no cierra al centavo, la base
    gravable declarada deja de cuadrar con el total facturado.
    """
    if not pesos_relativos:
        return ()
    suma = sum(pesos_relativos)
    if suma <= 0:
        msg = "los pesos relativos deben sumar un valor positivo"
        raise ValueError(msg)
    asignado = 0
    partes: list[Centavos] = []
    for peso in pesos_relativos[:-1]:
        parte = int((Decimal(total) * peso / suma).quantize(_UN_CENTAVO, rounding=ROUND_HALF_UP))
        partes.append(parte)
        asignado += parte
    partes.append(total - asignado)
    return tuple(partes)

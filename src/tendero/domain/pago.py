"""Que rieles de pago aplican a un pedido colombiano concreto.

En Colombia el medio de pago no es una preferencia del cliente sino una funcion
del destino, del monto y de lo que va en el carrito. El contra entrega, que es
el riel dominante fuera de las capitales, tiene tope de recaudo, cobertura
parcial y no existe donde solo llega el avion. Nequi es un deposito de bajo
monto y por norma no puede mover mas de ocho salarios minimos. PSE necesita que
el cliente escoja banco antes de empezar. La tarjeta arrastra retencion en la
fuente del 1,5 por ciento contra el comercio, y todo lo que termina en una
cuenta paga el cuatro por mil.

Por eso la herramienta no ofrece una lista fija de botones: evalua, descarta y
explica. Un catalogo pensado para tarjeta prepagada no tiene donde poner nada
de esto.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from tendero.domain.dinero import (
    Centavos,
    aplicar_tarifa,
    formatear_cop,
    redondear_efectivo,
)
from tendero.domain.envio import Ciudad, diagnostico_contraentrega, tope_contraentrega
from tendero.domain.errores import MetodoPagoError
from tendero.domain.impuesto import TARIFA_IVA_GENERAL

__all__ = [
    "BANCOS_PSE",
    "PARAMETROS_VIGENTES",
    "SMMLV_TOPE_DEPOSITO_BAJO_MONTO",
    "TARIFA_GMF",
    "TARIFA_RETEFUENTE_TARJETAS",
    "UVT_EXENTAS_GMF_MENSUALES",
    "ContextoPago",
    "EvaluacionPago",
    "MetodoPago",
    "ParametrosFiscales",
    "evaluar",
    "gmf",
    "recomendar",
]

TARIFA_GMF: Final = Decimal("0.004")
"""Gravamen a los movimientos financieros, el cuatro por mil (Art. 870 ET)."""

UVT_EXENTAS_GMF_MENSUALES: Final = 65
"""Retiros mensuales exentos de GMF en una cuenta marcada (Art. 879 num. 1 ET)."""

TARIFA_RETEFUENTE_TARJETAS: Final = Decimal("0.015")
"""Retencion en la fuente sobre pagos con tarjeta, sobre la base sin IVA."""

SMMLV_TOPE_DEPOSITO_BAJO_MONTO: Final = 8
"""Tope en salarios minimos de un deposito de bajo monto (Decreto 2555 de 2010).

Es el techo regulatorio de Nequi y de los demas depositos electronicos: por eso
un pedido grande no se puede pagar por ahi aunque el cliente quiera.
"""

_CUOTAS_MAXIMAS_TARJETA: Final = 36
_DIAS_LIQUIDACION_CONTRAENTREGA: Final = 8


@dataclass(frozen=True, slots=True)
class ParametrosFiscales:
    """Valores que el Gobierno reajusta cada ano.

    Van en un objeto y no en constantes sueltas porque cambian por decreto en
    diciembre: si estuvieran incrustados en la logica, el sistema empezaria el
    ano calculando topes viejos sin que nadie se entere.
    """

    anio: int
    uvt_centavos: Centavos
    smmlv_centavos: Centavos

    @property
    def tope_deposito_bajo_monto_centavos(self) -> Centavos:
        """Ocho salarios minimos, el techo de un deposito de bajo monto."""
        return SMMLV_TOPE_DEPOSITO_BAJO_MONTO * self.smmlv_centavos

    @property
    def exencion_gmf_mensual_centavos(self) -> Centavos:
        """Sesenta y cinco UVT de retiros exentos del cuatro por mil al mes."""
        return UVT_EXENTAS_GMF_MENSUALES * self.uvt_centavos


PARAMETROS_VIGENTES: Final = ParametrosFiscales(
    anio=2025,
    uvt_centavos=49_799_00,
    smmlv_centavos=1_423_500_00,
)
"""Ultimos valores verificados. Actualizar con el decreto anual de UVT y de salario minimo."""

BANCOS_PSE: Final[frozenset[str]] = frozenset(
    {
        "bancolombia",
        "davivienda",
        "banco de bogota",
        "bbva colombia",
        "banco de occidente",
        "banco popular",
        "banco caja social",
        "scotiabank colpatria",
        "itau",
        "banco av villas",
        "banco agrario",
        "banco falabella",
        "banco pichincha",
        "banco gnb sudameris",
        "banco serfinanza",
        "bancoomeva",
        "lulo bank",
        "nequi",
        "daviplata",
    }
)
"""Entidades habilitadas en PSE que un cliente de tienda de barrio suele tener."""


class MetodoPago(StrEnum):
    """Rieles de pago que el comercio puede ofrecer."""

    NEQUI = "nequi"
    PSE = "pse"
    BANCOLOMBIA = "bancolombia"
    TARJETA = "tarjeta"
    CONTRAENTREGA = "contraentrega"


_NOMBRES: Final[Mapping[MetodoPago, str]] = MappingProxyType(
    {
        MetodoPago.NEQUI: "Nequi",
        MetodoPago.PSE: "PSE (debito de cuenta bancaria)",
        MetodoPago.BANCOLOMBIA: "Transferencia Bancolombia",
        MetodoPago.TARJETA: "Tarjeta debito o credito",
        MetodoPago.CONTRAENTREGA: "Contra entrega (efectivo al mensajero)",
    }
)


@dataclass(frozen=True, slots=True)
class ContextoPago:
    """Todo lo que condiciona la disponibilidad de un riel."""

    total_centavos: Centavos
    ciudad: Ciudad
    base_sin_impuestos_centavos: Centavos = 0
    comision_recaudo_centavos: Centavos = 0
    contiene_servicios: bool = False
    banco_pse: str | None = None
    cliente_tiene_bancolombia: bool = False
    parametros: ParametrosFiscales = PARAMETROS_VIGENTES

    def __post_init__(self) -> None:
        """Un pedido sin valor no se puede cobrar por ningun riel."""
        if self.total_centavos <= 0:
            msg = "el total del pedido debe ser positivo"
            raise ValueError(msg)

    @property
    def base_retefuente_centavos(self) -> Centavos:
        """Base de la retencion: el valor de la venta sin impuestos."""
        return self.base_sin_impuestos_centavos or self.total_centavos


@dataclass(frozen=True, slots=True)
class EvaluacionPago:
    """Veredicto sobre un riel, con su costo real para el comercio."""

    metodo: MetodoPago
    nombre: str
    disponible: bool
    motivos: tuple[str, ...]
    requisitos: tuple[str, ...] = ()
    recargo_cliente_centavos: Centavos = 0
    comision_centavos: Centavos = 0
    retencion_centavos: Centavos = 0
    gmf_centavos: Centavos = 0
    dias_habiles_liquidacion: int = 0
    cuotas_maximas: int = 1
    total_cliente_centavos: Centavos = 0
    neto_comercio_centavos: Centavos = 0
    notas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def costo_total_comercio_centavos(self) -> Centavos:
        """Suma de comision, retencion y GMF: lo que se pierde por el camino."""
        return self.comision_centavos + self.retencion_centavos + self.gmf_centavos


def gmf(monto: Centavos) -> Centavos:
    """Cuatro por mil sobre un movimiento financiero."""
    return aplicar_tarifa(monto, TARIFA_GMF)


def _comision(base: Centavos, porcentual: Decimal, fijo: Centavos) -> Centavos:
    """Comision de pasarela con su IVA, que tambien lo asume el comercio."""
    bruta = aplicar_tarifa(base, porcentual) + fijo
    return bruta + aplicar_tarifa(bruta, TARIFA_IVA_GENERAL)


def _plegar(texto: str) -> str:
    """Normaliza el nombre de un banco escrito a mano."""
    descompuesto = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _armar(
    metodo: MetodoPago,
    contexto: ContextoPago,
    *,
    motivos: tuple[str, ...],
    comision: Centavos,
    retencion: Centavos = 0,
    recargo_cliente: Centavos = 0,
    dias: int = 0,
    cuotas: int = 1,
    requisitos: tuple[str, ...] = (),
    notas: tuple[str, ...] = (),
) -> EvaluacionPago:
    """Cierra las cuentas de un riel una vez decidida su disponibilidad."""
    disponible = not motivos
    total_cliente = contexto.total_centavos + recargo_cliente
    bruto_comercio = total_cliente - comision - retencion
    impuesto_movimiento = gmf(bruto_comercio) if disponible else 0
    return EvaluacionPago(
        metodo=metodo,
        nombre=_NOMBRES[metodo],
        disponible=disponible,
        motivos=motivos,
        requisitos=requisitos,
        recargo_cliente_centavos=recargo_cliente,
        comision_centavos=comision,
        retencion_centavos=retencion,
        gmf_centavos=impuesto_movimiento,
        dias_habiles_liquidacion=dias,
        cuotas_maximas=cuotas,
        total_cliente_centavos=total_cliente,
        neto_comercio_centavos=bruto_comercio - impuesto_movimiento,
        notas=notas,
    )


def _evaluar_nequi(contexto: ContextoPago) -> EvaluacionPago:
    """Nequi: instantaneo, barato y con techo regulatorio."""
    motivos: list[str] = []
    tope = contexto.parametros.tope_deposito_bajo_monto_centavos
    if contexto.total_centavos > tope:
        motivos.append(
            f"Nequi es un deposito de bajo monto y no admite mas de "
            f"{SMMLV_TOPE_DEPOSITO_BAJO_MONTO} salarios minimos por operacion "
            f"(Decreto 2555 de 2010); el pedido los supera"
        )
    return _armar(
        MetodoPago.NEQUI,
        contexto,
        motivos=tuple(motivos),
        comision=_comision(contexto.total_centavos, Decimal("0.015"), 0),
        dias=0,
        requisitos=("numero de celular del cliente",),
        notas=("acreditacion inmediata: el pedido se despacha el mismo dia",),
    )


def _evaluar_pse(contexto: ContextoPago) -> EvaluacionPago:
    """PSE: debito directo de cuenta, exige escoger banco de antemano."""
    motivos: list[str] = []
    if contexto.banco_pse is None:
        motivos.append("PSE exige que el cliente elija su banco antes de iniciar el debito")
    elif _plegar(contexto.banco_pse) not in BANCOS_PSE:
        motivos.append(f"el banco {contexto.banco_pse!r} no esta habilitado en PSE")
    minimo = 1_500_00
    if contexto.total_centavos < minimo:
        motivos.append("PSE no procesa transacciones por debajo de mil quinientos pesos")
    return _armar(
        MetodoPago.PSE,
        contexto,
        motivos=tuple(motivos),
        comision=_comision(contexto.total_centavos, Decimal("0"), 1_500_00),
        dias=1,
        requisitos=("banco del cliente", "clave de banca virtual"),
        notas=("comision fija: es el riel mas barato para pedidos grandes",),
    )


def _evaluar_bancolombia(contexto: ContextoPago) -> EvaluacionPago:
    """Boton Bancolombia: transferencia entre cuentas de la misma entidad."""
    motivos: list[str] = []
    if not contexto.cliente_tiene_bancolombia:
        motivos.append("la transferencia directa requiere que el cliente tenga cuenta Bancolombia")
    return _armar(
        MetodoPago.BANCOLOMBIA,
        contexto,
        motivos=tuple(motivos),
        comision=_comision(contexto.total_centavos, Decimal("0"), 1_200_00),
        dias=0,
        requisitos=("cuenta Bancolombia del cliente",),
        notas=("transferencia entre cuentas de la misma entidad: se acredita al instante",),
    )


def _evaluar_tarjeta(contexto: ContextoPago) -> EvaluacionPago:
    """Tarjeta: el unico riel con cuotas, y el mas caro para el comercio."""
    motivos: list[str] = []
    minimo = 2_000_00
    if contexto.total_centavos < minimo:
        motivos.append("las franquicias no autorizan compras por debajo de dos mil pesos")
    retencion = aplicar_tarifa(contexto.base_retefuente_centavos, TARIFA_RETEFUENTE_TARJETAS)
    return _armar(
        MetodoPago.TARJETA,
        contexto,
        motivos=tuple(motivos),
        comision=_comision(contexto.total_centavos, Decimal("0.0299"), 900_00),
        retencion=retencion,
        dias=2,
        cuotas=_CUOTAS_MAXIMAS_TARJETA,
        requisitos=("numero de tarjeta", "autenticacion 3-D Secure"),
        notas=(
            "el adquiriente practica retencion en la fuente del 1,5 por ciento "
            "sobre la venta sin impuestos; es un anticipo de renta, no un costo perdido",
            f"admite hasta {_CUOTAS_MAXIMAS_TARJETA} cuotas",
        ),
    )


def _evaluar_contraentrega(contexto: ContextoPago) -> EvaluacionPago:
    """Contra entrega: el riel dominante, y el que mas restricciones tiene."""
    motivos: list[str] = []
    if contexto.contiene_servicios:
        motivos.append("el contra entrega necesita un bulto fisico que entregar")
    cubierto, detalle = diagnostico_contraentrega(contexto.ciudad)
    if not cubierto:
        motivos.append(detalle)
    tope = tope_contraentrega(contexto.ciudad)
    if cubierto and contexto.total_centavos > tope:
        motivos.append(
            f"ninguna transportadora que cubra {contexto.ciudad.etiqueta} recauda mas de "
            f"{formatear_cop(tope)}; este pedido debe cobrarse por adelantado"
        )
    if contexto.comision_recaudo_centavos <= 0 and cubierto:
        motivos.append(
            "falta cotizar el recaudo con la transportadora antes de ofrecer contra entrega"
        )
    recargo = redondear_efectivo(contexto.comision_recaudo_centavos)
    return _armar(
        MetodoPago.CONTRAENTREGA,
        contexto,
        motivos=tuple(motivos),
        comision=0,
        recargo_cliente=recargo,
        dias=_DIAS_LIQUIDACION_CONTRAENTREGA,
        requisitos=("direccion exacta", "telefono de contacto", "efectivo al recibir"),
        notas=(
            "el valor a recaudar se redondea a los cincuenta pesos mas cercanos "
            "porque el mensajero no da cambio por debajo de esa moneda",
            "la transportadora gira el recaudo despues de entregar: el dinero "
            "entra dias despues de despachar el pedido",
        ),
    )


_EVALUADORES: Final[Mapping[MetodoPago, Callable[[ContextoPago], EvaluacionPago]]] = (
    MappingProxyType(
        {
            MetodoPago.NEQUI: _evaluar_nequi,
            MetodoPago.PSE: _evaluar_pse,
            MetodoPago.BANCOLOMBIA: _evaluar_bancolombia,
            MetodoPago.TARJETA: _evaluar_tarjeta,
            MetodoPago.CONTRAENTREGA: _evaluar_contraentrega,
        }
    )
)


def evaluar(contexto: ContextoPago) -> tuple[EvaluacionPago, ...]:
    """Evalua los cinco rieles y los ordena por lo que le queda al comercio.

    Devuelve tambien los que no aplican, con su motivo: el agente necesita poder
    decir por que no aparece el contra entrega, no solo omitirlo.
    """
    resultados = [evaluador(contexto) for evaluador in _EVALUADORES.values()]
    return tuple(
        sorted(
            resultados,
            key=lambda e: (not e.disponible, -e.neto_comercio_centavos, e.dias_habiles_liquidacion),
        )
    )


def recomendar(contexto: ContextoPago) -> EvaluacionPago:
    """El mejor riel disponible; falla si ninguno aplica."""
    for evaluacion in evaluar(contexto):
        if evaluacion.disponible:
            return evaluacion
    msg = f"ningun medio de pago aplica a un pedido a {contexto.ciudad.etiqueta}"
    raise MetodoPagoError(msg)

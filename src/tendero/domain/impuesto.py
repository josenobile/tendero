"""IVA colombiano: 19 por ciento, 5 por ciento, exento y excluido.

Exento y excluido no son sinonimos y confundirlos falsea el precio y la
declaracion. Un bien EXENTO (articulo 477 del Estatuto Tributario: carne,
leche, huevos) esta gravado a tarifa cero, de modo que el vendedor si tiene
derecho a descontar el IVA que pago por sus insumos. Un bien EXCLUIDO
(articulo 424: frutas frescas, panela, arroz de consumo humano) simplemente no
causa el impuesto, y entonces el IVA de sus insumos se vuelve mayor costo y se
traslada al precio. En la factura electronica el exento viaja con una linea de
IVA al 0,00 por ciento y el excluido no lleva linea de impuesto.

Ademas el destino puede apagar el impuesto: el articulo 423 excluye del IVA al
Archipielago de San Andres, Providencia y Santa Catalina, y el articulo 270 de
la Ley 223 de 1995 hace lo propio con Amazonas, Guainia y Vaupes. La misma
canasta cuesta distinto en Leticia que en Medellin, y no por el flete.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from tendero.domain.dinero import Centavos, aplicar_tarifa
from tendero.domain.envio import REGIMEN_IVA_ESPECIAL, Ciudad

__all__ = [
    "IMPUESTOS_SALUDABLES",
    "TARIFA_INC_RESTAURANTES",
    "TARIFA_IVA_GENERAL",
    "TARIFA_IVA_REDUCIDA",
    "TRATAMIENTOS",
    "LineaLiquidada",
    "LineaVenta",
    "Liquidacion",
    "Regimen",
    "ResumenDescontables",
    "SubtotalTributo",
    "TratamientoTributario",
    "liquidar",
    "liquidar_linea",
    "resumen_descontables",
]

TARIFA_IVA_GENERAL: Final = Decimal("0.19")
TARIFA_IVA_REDUCIDA: Final = Decimal("0.05")
TARIFA_INC_RESTAURANTES: Final = Decimal("0.08")
_CERO: Final = Decimal("0")

IMPUESTOS_SALUDABLES: Final = (
    "El IBUA sobre bebidas azucaradas (articulo 513-2 ET) y el ICUI sobre "
    "comestibles ultraprocesados (articulo 513-6 ET) son monofasicos: se causan "
    "en la venta del productor o en la importacion, no en el mostrador. La "
    "tienda no los liquida; ya vienen dentro de su costo de compra."
)
"""Por que este modulo no cobra los impuestos saludables de la Ley 2277 de 2022."""


class Regimen(StrEnum):
    """Tratamiento tributario de una linea de venta."""

    GRAVADO_19 = "gravado_19"
    GRAVADO_5 = "gravado_5"
    EXENTO = "exento"
    EXCLUIDO = "excluido"
    INC_8 = "inc_8"


@dataclass(frozen=True, slots=True)
class TratamientoTributario:
    """Reglas que se derivan de un regimen."""

    regimen: Regimen
    tributo: str | None
    tarifa: Decimal
    causa_impuesto: bool
    da_derecho_a_descontables: bool
    fundamento: str
    explicacion: str


TRATAMIENTOS: Final[Mapping[Regimen, TratamientoTributario]] = MappingProxyType(
    {
        Regimen.GRAVADO_19: TratamientoTributario(
            regimen=Regimen.GRAVADO_19,
            tributo="IVA",
            tarifa=TARIFA_IVA_GENERAL,
            causa_impuesto=True,
            da_derecho_a_descontables=True,
            fundamento="Art. 468 ET",
            explicacion="Tarifa general del impuesto sobre las ventas.",
        ),
        Regimen.GRAVADO_5: TratamientoTributario(
            regimen=Regimen.GRAVADO_5,
            tributo="IVA",
            tarifa=TARIFA_IVA_REDUCIDA,
            causa_impuesto=True,
            da_derecho_a_descontables=True,
            fundamento="Art. 468-1 ET",
            explicacion="Tarifa diferencial para cafe, harinas, pastas y embutidos.",
        ),
        Regimen.EXENTO: TratamientoTributario(
            regimen=Regimen.EXENTO,
            tributo="IVA",
            tarifa=_CERO,
            causa_impuesto=True,
            da_derecho_a_descontables=True,
            fundamento="Art. 477 ET",
            explicacion=(
                "Gravado a tarifa cero: la factura lleva la linea de IVA al 0,00 por "
                "ciento y el vendedor conserva el derecho a impuestos descontables."
            ),
        ),
        Regimen.EXCLUIDO: TratamientoTributario(
            regimen=Regimen.EXCLUIDO,
            tributo=None,
            tarifa=_CERO,
            causa_impuesto=False,
            da_derecho_a_descontables=False,
            fundamento="Art. 424 ET",
            explicacion=(
                "No causa el impuesto: la factura no lleva linea de IVA y el IVA de "
                "los insumos se vuelve mayor costo del producto."
            ),
        ),
        Regimen.INC_8: TratamientoTributario(
            regimen=Regimen.INC_8,
            tributo="INC",
            tarifa=TARIFA_INC_RESTAURANTES,
            causa_impuesto=True,
            da_derecho_a_descontables=False,
            fundamento="Art. 512-1 num. 3 ET",
            explicacion=(
                "Expendio de comidas preparadas: paga impuesto nacional al consumo "
                "del 8 por ciento y, por eso mismo, no causa IVA."
            ),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class LineaVenta:
    """Linea de pedido antes de liquidar impuestos."""

    descripcion: str
    regimen: Regimen
    precio_unitario_centavos: Centavos
    cantidad: int = 1
    descuento_centavos: Centavos = 0

    def __post_init__(self) -> None:
        """Bloquea cantidades, precios y descuentos imposibles de facturar."""
        if self.cantidad <= 0:
            msg = f"{self.descripcion}: la cantidad debe ser positiva"
            raise ValueError(msg)
        if self.precio_unitario_centavos < 0:
            msg = f"{self.descripcion}: el precio no puede ser negativo"
            raise ValueError(msg)
        bruto = self.precio_unitario_centavos * self.cantidad
        if not 0 <= self.descuento_centavos <= bruto:
            msg = f"{self.descripcion}: el descuento debe estar entre 0 y {bruto}"
            raise ValueError(msg)

    @property
    def bruto_centavos(self) -> Centavos:
        """Precio de lista por la cantidad, sin descuentos."""
        return self.precio_unitario_centavos * self.cantidad


@dataclass(frozen=True, slots=True)
class LineaLiquidada:
    """Linea con su impuesto ya calculado y su fundamento legal."""

    descripcion: str
    cantidad: int
    regimen_solicitado: Regimen
    regimen_aplicado: Regimen
    tributo: str | None
    tarifa: Decimal
    bruto_centavos: Centavos
    descuento_centavos: Centavos
    base_gravable_centavos: Centavos
    impuesto_centavos: Centavos
    fundamento: str
    motivo_ajuste: str | None = None

    @property
    def total_centavos(self) -> Centavos:
        """Lo que el cliente paga por esta linea, impuesto incluido."""
        return self.base_gravable_centavos + self.impuesto_centavos

    @property
    def da_derecho_a_descontables(self) -> bool:
        """Si el vendedor puede recuperar el IVA de los insumos de esta linea."""
        return TRATAMIENTOS[self.regimen_aplicado].da_derecho_a_descontables


@dataclass(frozen=True, slots=True)
class SubtotalTributo:
    """Agrupacion por tributo y tarifa, como la exige el bloque UBL de la DIAN."""

    tributo: str
    tarifa: Decimal
    base_centavos: Centavos
    valor_centavos: Centavos

    @property
    def tarifa_porcentual(self) -> str:
        """Tarifa formateada como la imprime la representacion grafica."""
        return f"{self.tarifa * 100:.2f}".replace(".", ",")


@dataclass(frozen=True, slots=True)
class Liquidacion:
    """Resultado completo de liquidar un pedido."""

    lineas: tuple[LineaLiquidada, ...]
    subtotales: tuple[SubtotalTributo, ...]
    bruto_centavos: Centavos
    descuentos_centavos: Centavos
    base_gravable_centavos: Centavos
    iva_centavos: Centavos
    inc_centavos: Centavos
    total_centavos: Centavos
    notas: tuple[str, ...] = ()


def _regimen_efectivo(
    regimen: Regimen,
    *,
    destino: Ciudad | None,
    responsable_iva: bool,
) -> tuple[Regimen, str | None]:
    """Aplica las dos causales que apagan el IVA sin cambiar el producto."""
    tratamiento = TRATAMIENTOS[regimen]
    if tratamiento.tributo != "IVA":
        return regimen, None
    if destino is not None and destino.codigo_dane in REGIMEN_IVA_ESPECIAL:
        return Regimen.EXCLUIDO, (
            f"venta con destino {destino.etiqueta}: excluida del IVA "
            "(Art. 423 ET / Art. 270 Ley 223 de 1995)"
        )
    if not responsable_iva:
        return Regimen.EXCLUIDO, (
            "el comercio no es responsable de IVA (Art. 437 par. 3 ET), "
            "no puede cobrarlo ni discriminarlo en la factura"
        )
    return regimen, None


def liquidar_linea(
    linea: LineaVenta,
    *,
    destino: Ciudad | None = None,
    responsable_iva: bool = True,
) -> LineaLiquidada:
    """Liquida una linea, aplicando las causales de exclusion territorial."""
    aplicado, motivo = _regimen_efectivo(
        linea.regimen, destino=destino, responsable_iva=responsable_iva
    )
    tratamiento = TRATAMIENTOS[aplicado]
    base = linea.bruto_centavos - linea.descuento_centavos
    impuesto = aplicar_tarifa(base, tratamiento.tarifa) if tratamiento.causa_impuesto else 0
    return LineaLiquidada(
        descripcion=linea.descripcion,
        cantidad=linea.cantidad,
        regimen_solicitado=linea.regimen,
        regimen_aplicado=aplicado,
        tributo=tratamiento.tributo,
        tarifa=tratamiento.tarifa,
        bruto_centavos=linea.bruto_centavos,
        descuento_centavos=linea.descuento_centavos,
        base_gravable_centavos=base,
        impuesto_centavos=impuesto,
        fundamento=tratamiento.fundamento,
        motivo_ajuste=motivo,
    )


def _subtotales(lineas: Sequence[LineaLiquidada]) -> tuple[SubtotalTributo, ...]:
    """Agrupa por tributo y tarifa conservando el orden de aparicion."""
    acumulado: dict[tuple[str, Decimal], list[Centavos]] = {}
    for linea in lineas:
        if linea.tributo is None:
            continue
        clave = (linea.tributo, linea.tarifa)
        cubo = acumulado.setdefault(clave, [0, 0])
        cubo[0] += linea.base_gravable_centavos
        cubo[1] += linea.impuesto_centavos
    return tuple(
        SubtotalTributo(tributo=tributo, tarifa=tarifa, base_centavos=base, valor_centavos=valor)
        for (tributo, tarifa), (base, valor) in acumulado.items()
    )


def liquidar(
    lineas: Iterable[LineaVenta],
    *,
    destino: Ciudad | None = None,
    responsable_iva: bool = True,
) -> Liquidacion:
    """Liquida un pedido completo linea por linea.

    Se calcula por linea y luego se suma, nunca al reves: la DIAN valida que el
    impuesto declarado en cada linea sume exactamente el total del documento, y
    aplicar la tarifa sobre el total agregado produce diferencias de centavos
    que rechazan la factura.
    """
    liquidadas = tuple(
        liquidar_linea(linea, destino=destino, responsable_iva=responsable_iva) for linea in lineas
    )
    bruto = sum(linea.bruto_centavos for linea in liquidadas)
    descuentos = sum(linea.descuento_centavos for linea in liquidadas)
    base = sum(linea.base_gravable_centavos for linea in liquidadas)
    iva = sum(linea.impuesto_centavos for linea in liquidadas if linea.tributo == "IVA")
    inc = sum(linea.impuesto_centavos for linea in liquidadas if linea.tributo == "INC")
    notas = tuple(dict.fromkeys(linea.motivo_ajuste for linea in liquidadas if linea.motivo_ajuste))
    return Liquidacion(
        lineas=liquidadas,
        subtotales=_subtotales(liquidadas),
        bruto_centavos=bruto,
        descuentos_centavos=descuentos,
        base_gravable_centavos=base,
        iva_centavos=iva,
        inc_centavos=inc,
        total_centavos=base + iva + inc,
        notas=notas,
    )


@dataclass(frozen=True, slots=True)
class ResumenDescontables:
    """Cuanto de la venta conserva el derecho a impuestos descontables."""

    base_con_derecho_centavos: Centavos
    base_sin_derecho_centavos: Centavos
    nota: str


def resumen_descontables(liquidacion: Liquidacion) -> ResumenDescontables:
    """Separa la venta segun si el IVA de los insumos se recupera o se pierde.

    Es la consecuencia practica de que exento y excluido sean cosas distintas:
    sobre la porcion excluida el IVA que la tienda pago a su proveedor no se
    descuenta, se vuelve costo, y si no se traslada al precio la venta pierde
    margen sin que nadie lo note en la caja.
    """
    con_derecho = sum(
        linea.base_gravable_centavos
        for linea in liquidacion.lineas
        if linea.da_derecho_a_descontables
    )
    sin_derecho = liquidacion.base_gravable_centavos - con_derecho
    if sin_derecho == 0:
        nota = "toda la venta conserva el derecho a impuestos descontables"
    else:
        nota = (
            "sobre la base sin derecho el IVA pagado a proveedores no se descuenta "
            "(Art. 488 ET) y debe absorberse en el precio de venta"
        )
    return ResumenDescontables(
        base_con_derecho_centavos=con_derecho,
        base_sin_derecho_centavos=sin_derecho,
        nota=nota,
    )

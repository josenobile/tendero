"""Cotizacion de flete nacional desde Medellin.

El costo de llevar una caja en Colombia no depende de la distancia sino de si
el destino esta en un area metropolitana, en una ciudad intermedia o en un
municipio al que solo se llega por avion o por rio. Leticia, Mitu, Inirida,
Puerto Carreno, San Andres y Providencia no tienen carretera: la mercancia
viaja como carga aerea, la entrega la hace un agente local y por eso ninguna
transportadora acepta recaudo contra entrega alli.

Esa asimetria es el punto del modulo. Un catalogo de herramientas pensado para
Estados Unidos asume tarjeta prepagada y direccion postal; aqui el metodo de
pago que domina el comercio electronico -- pagar en efectivo cuando llega el
paquete -- depende de la ciudad, y la herramienta tiene que poder decir que no.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from tendero.domain.dinero import Centavos, aplicar_tarifa
from tendero.domain.errores import CiudadDesconocidaError

__all__ = [
    "CIUDADES",
    "FACTOR_VOLUMETRICO_CM3_POR_KG",
    "FLETE_EXCLUIDO_DE_IVA",
    "PESO_FACTURABLE_MINIMO_GRAMOS",
    "REGIMEN_IVA_ESPECIAL",
    "SIN_CONTRAENTREGA",
    "TRANSPORTADORAS",
    "Ciudad",
    "Cotizacion",
    "Paquete",
    "TarifaZona",
    "Transportadora",
    "Zona",
    "buscar_ciudades",
    "cotizar",
    "diagnostico_contraentrega",
    "mejor_cotizacion",
    "resolver_ciudad",
    "tope_contraentrega",
]

FACTOR_VOLUMETRICO_CM3_POR_KG: Final = 6000
"""Divisor que las transportadoras colombianas usan para el peso volumetrico."""

PESO_FACTURABLE_MINIMO_GRAMOS: Final = 1000
"""Ninguna guia se cobra por debajo de un kilo, asi vaya vacia."""

FLETE_EXCLUIDO_DE_IVA: Final = (
    "Art. 476 num. 2 ET: el transporte nacional de carga esta excluido del IVA. "
    "Por eso el flete se suma al total del pedido sin impuesto y no entra a la "
    "base gravable de la factura."
)
"""Por que el flete se suma al total sin volver a liquidar impuesto."""

_RECARGO_AEREO: Final = Decimal("1.65")
_RECARGO_AEREO_FIJO: Final[Centavos] = 12_000_00
_DIAS_EXTRA_AEREO: Final = 3
_GRAMOS_POR_KILO: Final = 1000


class Zona(StrEnum):
    """Tramo tarifario del destino."""

    METROPOLITANA = "metropolitana"
    INTERMEDIA = "intermedia"
    REMOTA = "remota"


@dataclass(frozen=True, slots=True)
class Ciudad:
    """Municipio de destino identificado por su codigo DANE."""

    codigo_dane: str
    nombre: str
    departamento: str
    zona: Zona
    solo_aereo: bool = False
    regimen_iva_especial: bool = False

    @property
    def etiqueta(self) -> str:
        """Nombre presentable, siempre con departamento para desambiguar."""
        return f"{self.nombre}, {self.departamento}"


def _c(
    codigo: str,
    nombre: str,
    departamento: str,
    zona: Zona,
    *,
    aereo: bool = False,
    iva_especial: bool = False,
) -> tuple[str, Ciudad]:
    """Atajo de construccion para la tabla maestra."""
    return codigo, Ciudad(
        codigo_dane=codigo,
        nombre=nombre,
        departamento=departamento,
        zona=zona,
        solo_aereo=aereo,
        regimen_iva_especial=iva_especial,
    )


_M: Final = Zona.METROPOLITANA
_I: Final = Zona.INTERMEDIA
_R: Final = Zona.REMOTA

CIUDADES: Final[Mapping[str, Ciudad]] = MappingProxyType(
    dict(
        (
            _c("05001", "Medellin", "Antioquia", _M),
            _c("05088", "Bello", "Antioquia", _M),
            _c("05266", "Envigado", "Antioquia", _M),
            _c("05360", "Itagui", "Antioquia", _M),
            _c("05631", "Sabaneta", "Antioquia", _M),
            _c("05380", "La Estrella", "Antioquia", _M),
            _c("05129", "Caldas", "Antioquia", _M),
            _c("05212", "Copacabana", "Antioquia", _M),
            _c("05308", "Girardota", "Antioquia", _M),
            _c("05079", "Barbosa", "Antioquia", _M),
            _c("11001", "Bogota D.C.", "Bogota D.C.", _M),
            _c("25754", "Soacha", "Cundinamarca", _M),
            _c("25175", "Chia", "Cundinamarca", _M),
            _c("76001", "Cali", "Valle del Cauca", _M),
            _c("08001", "Barranquilla", "Atlantico", _M),
            _c("08758", "Soledad", "Atlantico", _M),
            _c("05615", "Rionegro", "Antioquia", _I),
            _c("05045", "Apartado", "Antioquia", _I),
            _c("05837", "Turbo", "Antioquia", _I),
            _c("13001", "Cartagena", "Bolivar", _I),
            _c("68001", "Bucaramanga", "Santander", _I),
            _c("66001", "Pereira", "Risaralda", _I),
            _c("17001", "Manizales", "Caldas", _I),
            _c("63001", "Armenia", "Quindio", _I),
            _c("47001", "Santa Marta", "Magdalena", _I),
            _c("54001", "Cucuta", "Norte de Santander", _I),
            _c("50001", "Villavicencio", "Meta", _I),
            _c("73001", "Ibague", "Tolima", _I),
            _c("52001", "Pasto", "Narino", _I),
            _c("41001", "Neiva", "Huila", _I),
            _c("23001", "Monteria", "Cordoba", _I),
            _c("19001", "Popayan", "Cauca", _I),
            _c("70001", "Sincelejo", "Sucre", _I),
            _c("20001", "Valledupar", "Cesar", _I),
            _c("15001", "Tunja", "Boyaca", _I),
            _c("85001", "Yopal", "Casanare", _I),
            _c("76109", "Buenaventura", "Valle del Cauca", _I),
            _c("44001", "Riohacha", "La Guajira", _I),
            _c("27001", "Quibdo", "Choco", _R),
            _c("18001", "Florencia", "Caqueta", _R),
            _c("81001", "Arauca", "Arauca", _R),
            _c("86001", "Mocoa", "Putumayo", _R),
            _c("95001", "San Jose del Guaviare", "Guaviare", _R),
            _c(
                "88001",
                "San Andres",
                "Archipielago de San Andres",
                _R,
                aereo=True,
                iva_especial=True,
            ),
            _c(
                "88564",
                "Providencia",
                "Archipielago de San Andres",
                _R,
                aereo=True,
                iva_especial=True,
            ),
            _c("91001", "Leticia", "Amazonas", _R, aereo=True, iva_especial=True),
            _c("91540", "Puerto Narino", "Amazonas", _R, aereo=True, iva_especial=True),
            _c("94001", "Inirida", "Guainia", _R, aereo=True, iva_especial=True),
            _c("97001", "Mitu", "Vaupes", _R, aereo=True, iva_especial=True),
            _c("99001", "Puerto Carreno", "Vichada", _R, aereo=True),
        )
    )
)

REGIMEN_IVA_ESPECIAL: Final[frozenset[str]] = frozenset(
    codigo for codigo, ciudad in CIUDADES.items() if ciudad.regimen_iva_especial
)
"""Destinos donde la venta no causa IVA.

San Andres y Providencia por el articulo 423 del Estatuto Tributario; Amazonas,
Guainia y Vaupes por el articulo 270 de la Ley 223 de 1995. El destino, no el
producto, cambia el impuesto: eso lo consume :mod:`tendero.domain.impuesto`.
"""

SIN_CONTRAENTREGA: Final[frozenset[str]] = frozenset(
    codigo for codigo, ciudad in CIUDADES.items() if ciudad.solo_aereo
)
"""Destinos sin recaudo contra entrega: la entrega final la hace un tercero."""


@dataclass(frozen=True, slots=True)
class TarifaZona:
    """Tarifa de una transportadora para un tramo."""

    base_centavos: Centavos
    kilos_incluidos: int
    adicional_por_kilo_centavos: Centavos
    dias_habiles_minimo: int
    dias_habiles_maximo: int


@dataclass(frozen=True, slots=True)
class Transportadora:
    """Operador logistico con su cobertura y su politica de recaudo."""

    codigo: str
    nombre: str
    tarifas: Mapping[Zona, TarifaZona]
    ofrece_contraentrega: bool
    comision_recaudo: Decimal
    recaudo_minimo_centavos: Centavos
    recaudo_maximo_centavos: Centavos
    comision_manejo: Decimal
    manejo_minimo_centavos: Centavos
    nit: str | None = None
    sin_cobertura: frozenset[str] = field(default_factory=frozenset)

    def cubre(self, ciudad: Ciudad) -> bool:
        """Cierto si la transportadora entrega en esa ciudad."""
        return ciudad.zona in self.tarifas and ciudad.codigo_dane not in self.sin_cobertura


def _tarifas(
    metro: tuple[Centavos, Centavos] | None,
    intermedia: tuple[Centavos, Centavos] | None,
    remota: tuple[Centavos, Centavos] | None,
    *,
    kilos_incluidos: int = 1,
) -> Mapping[Zona, TarifaZona]:
    """Arma la tabla de tarifas de un operador a partir de (base, adicional)."""
    plazos = {_M: (1, 2), _I: (2, 4), _R: (4, 8)}
    crudo = {_M: metro, _I: intermedia, _R: remota}
    tabla: dict[Zona, TarifaZona] = {}
    for zona, valores in crudo.items():
        if valores is None:
            continue
        minimo, maximo = plazos[zona]
        tabla[zona] = TarifaZona(
            base_centavos=valores[0],
            kilos_incluidos=kilos_incluidos,
            adicional_por_kilo_centavos=valores[1],
            dias_habiles_minimo=minimo,
            dias_habiles_maximo=maximo,
        )
    return MappingProxyType(tabla)


TRANSPORTADORAS: Final[tuple[Transportadora, ...]] = (
    Transportadora(
        codigo="servientrega",
        nombre="Servientrega",
        nit="860512330-3",
        tarifas=_tarifas((9_500_00, 3_200_00), (15_900_00, 4_500_00), (29_800_00, 8_900_00)),
        ofrece_contraentrega=True,
        comision_recaudo=Decimal("0.045"),
        recaudo_minimo_centavos=7_000_00,
        recaudo_maximo_centavos=2_000_000_00,
        comision_manejo=Decimal("0.010"),
        manejo_minimo_centavos=2_500_00,
    ),
    Transportadora(
        codigo="interrapidisimo",
        nombre="Inter Rapidisimo",
        nit="830029788-2",
        tarifas=_tarifas((8_200_00, 2_900_00), (13_900_00, 4_100_00), (27_500_00, 8_200_00)),
        ofrece_contraentrega=True,
        comision_recaudo=Decimal("0.040"),
        recaudo_minimo_centavos=6_000_00,
        recaudo_maximo_centavos=2_000_000_00,
        comision_manejo=Decimal("0.010"),
        manejo_minimo_centavos=2_000_00,
        sin_cobertura=frozenset({"88564", "94001", "97001", "99001", "91540"}),
    ),
    Transportadora(
        codigo="coordinadora",
        nombre="Coordinadora",
        tarifas=_tarifas((11_000_00, 3_500_00), (18_500_00, 5_200_00), (34_000_00, 9_800_00)),
        ofrece_contraentrega=False,
        comision_recaudo=Decimal("0"),
        recaudo_minimo_centavos=0,
        recaudo_maximo_centavos=0,
        comision_manejo=Decimal("0.012"),
        manejo_minimo_centavos=3_000_00,
        sin_cobertura=frozenset({"88564", "91540", "94001", "97001", "99001"}),
    ),
    Transportadora(
        codigo="envia",
        nombre="Envia",
        tarifas=_tarifas((8_900_00, 3_000_00), (14_800_00, 4_300_00), None),
        ofrece_contraentrega=True,
        comision_recaudo=Decimal("0.045"),
        recaudo_minimo_centavos=6_500_00,
        recaudo_maximo_centavos=1_500_000_00,
        comision_manejo=Decimal("0.010"),
        manejo_minimo_centavos=2_500_00,
    ),
    Transportadora(
        codigo="rapidito_aburra",
        nombre="Rapidito Aburra (mensajeria local)",
        nit="901234567-7",
        tarifas=_tarifas((7_000_00, 1_500_00), None, None, kilos_incluidos=5),
        ofrece_contraentrega=True,
        comision_recaudo=Decimal("0"),
        recaudo_minimo_centavos=0,
        recaudo_maximo_centavos=500_000_00,
        comision_manejo=Decimal("0"),
        manejo_minimo_centavos=0,
    ),
)


@dataclass(frozen=True, slots=True)
class Paquete:
    """Bulto a despachar, con el valor que se declara ante la transportadora."""

    peso_gramos: int
    largo_cm: int = 20
    ancho_cm: int = 20
    alto_cm: int = 15
    valor_declarado_centavos: Centavos = 0

    def __post_init__(self) -> None:
        """Un bulto sin peso o sin volumen no es cotizable."""
        if self.peso_gramos <= 0:
            msg = "el peso del paquete debe ser positivo"
            raise ValueError(msg)
        if min(self.largo_cm, self.ancho_cm, self.alto_cm) <= 0:
            msg = "las dimensiones del paquete deben ser positivas"
            raise ValueError(msg)
        if self.valor_declarado_centavos < 0:
            msg = "el valor declarado no puede ser negativo"
            raise ValueError(msg)

    @property
    def peso_volumetrico_gramos(self) -> int:
        """Peso equivalente al espacio que ocupa la caja en el camion."""
        centimetros_cubicos = self.largo_cm * self.ancho_cm * self.alto_cm
        kilos = Decimal(centimetros_cubicos) / FACTOR_VOLUMETRICO_CM3_POR_KG
        return int(kilos * _GRAMOS_POR_KILO)

    @property
    def peso_facturable_gramos(self) -> int:
        """El mayor entre peso real y volumetrico, con piso de un kilo."""
        return max(self.peso_gramos, self.peso_volumetrico_gramos, PESO_FACTURABLE_MINIMO_GRAMOS)


@dataclass(frozen=True, slots=True)
class Cotizacion:
    """Una opcion de despacho concreta, ya desglosada."""

    transportadora: str
    codigo_transportadora: str
    ciudad: Ciudad
    peso_facturable_gramos: int
    flete_centavos: Centavos
    recargo_aereo_centavos: Centavos
    manejo_centavos: Centavos
    recaudo_centavos: Centavos
    dias_habiles_minimo: int
    dias_habiles_maximo: int
    contraentrega: bool
    notas: tuple[str, ...] = ()

    @property
    def total_centavos(self) -> Centavos:
        """Lo que el comercio paga por mover el pedido."""
        return (
            self.flete_centavos
            + self.recargo_aereo_centavos
            + self.manejo_centavos
            + self.recaudo_centavos
        )


def _plegar(texto: str) -> str:
    """Quita tildes y baja a minusculas para comparar nombres escritos a mano."""
    descompuesto = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def resolver_ciudad(consulta: str) -> Ciudad:
    """Encuentra la ciudad por codigo DANE o por nombre, con o sin tildes."""
    bruto = consulta.strip()
    if bruto in CIUDADES:
        return CIUDADES[bruto]
    relleno = bruto.zfill(5)
    if relleno.isdigit() and relleno in CIUDADES:
        return CIUDADES[relleno]
    objetivo = _plegar(bruto)
    for ciudad in CIUDADES.values():
        if _plegar(ciudad.nombre) == objetivo:
            return ciudad
    parciales = buscar_ciudades(bruto)
    if len(parciales) == 1:
        return parciales[0]
    msg = f"no se reconoce el destino {consulta!r}"
    if parciales:
        opciones = ", ".join(c.etiqueta for c in parciales[:5])
        msg = f"{msg}; quiza: {opciones}"
    raise CiudadDesconocidaError(msg)


def buscar_ciudades(texto: str) -> tuple[Ciudad, ...]:
    """Sugiere ciudades cuyo nombre contiene el texto dado."""
    objetivo = _plegar(texto)
    if not objetivo:
        return ()
    return tuple(ciudad for ciudad in CIUDADES.values() if objetivo in _plegar(ciudad.etiqueta))


def diagnostico_contraentrega(destino: str | Ciudad) -> tuple[bool, str]:
    """Dice si el destino admite pago contra entrega y por que no, si no.

    Devolver el motivo importa: el agente necesita explicarle al cliente que su
    pedido a Leticia si sale, pero pagando por adelantado.
    """
    ciudad = destino if isinstance(destino, Ciudad) else resolver_ciudad(destino)
    if ciudad.codigo_dane in SIN_CONTRAENTREGA:
        return False, (
            f"{ciudad.etiqueta} solo tiene acceso aereo o fluvial; la entrega final "
            "la hace un agente local y ninguna transportadora recauda alli"
        )
    disponibles = [t.nombre for t in TRANSPORTADORAS if t.ofrece_contraentrega and t.cubre(ciudad)]
    if not disponibles:
        return False, f"ninguna transportadora con recaudo cubre {ciudad.etiqueta}"
    return True, f"disponible con {', '.join(disponibles)}"


def tope_contraentrega(destino: str | Ciudad) -> Centavos:
    """Monto maximo que alguna transportadora acepta recaudar en ese destino.

    Es un limite comercial de cada operador, no una tarifa: por encima de el la
    venta existe pero hay que cobrarla por adelantado. Vive aqui porque depende
    de quien cubre la ciudad, y lo consume :mod:`tendero.domain.pago`.
    """
    ciudad = destino if isinstance(destino, Ciudad) else resolver_ciudad(destino)
    if ciudad.codigo_dane in SIN_CONTRAENTREGA:
        return 0
    return max(
        (
            operador.recaudo_maximo_centavos
            for operador in TRANSPORTADORAS
            if operador.ofrece_contraentrega and operador.cubre(ciudad)
        ),
        default=0,
    )


def _flete(tarifa: TarifaZona, peso_gramos: int) -> Centavos:
    """Cobro por peso: base mas kilos adicionales redondeados hacia arriba."""
    kilos = (Decimal(peso_gramos) / _GRAMOS_POR_KILO).quantize(Decimal(1), rounding=ROUND_CEILING)
    adicionales = max(0, int(kilos) - tarifa.kilos_incluidos)
    return tarifa.base_centavos + adicionales * tarifa.adicional_por_kilo_centavos


def cotizar(
    destino: str | Ciudad,
    paquete: Paquete,
    *,
    contraentrega: bool = False,
    monto_a_recaudar_centavos: Centavos = 0,
) -> tuple[Cotizacion, ...]:
    """Cotiza el despacho con todas las transportadoras que sirven el destino.

    Con ``contraentrega`` activo solo devuelve operadores que recauden y que
    aguanten el monto: el tope de recaudo de una transportadora es la razon mas
    frecuente por la que un pedido grande no se puede pagar al mensajero.
    """
    ciudad = destino if isinstance(destino, Ciudad) else resolver_ciudad(destino)
    peso = paquete.peso_facturable_gramos
    opciones: list[Cotizacion] = []
    for operador in TRANSPORTADORAS:
        if not operador.cubre(ciudad):
            continue
        notas: list[str] = []
        if contraentrega:
            if not operador.ofrece_contraentrega:
                continue
            if ciudad.codigo_dane in SIN_CONTRAENTREGA:
                continue
            if monto_a_recaudar_centavos > operador.recaudo_maximo_centavos:
                continue
        tarifa = operador.tarifas[ciudad.zona]
        flete = _flete(tarifa, peso)
        recargo = 0
        dias_minimo = tarifa.dias_habiles_minimo
        dias_maximo = tarifa.dias_habiles_maximo
        if ciudad.solo_aereo:
            recargo = aplicar_tarifa(flete, _RECARGO_AEREO - Decimal(1)) + _RECARGO_AEREO_FIJO
            dias_minimo += _DIAS_EXTRA_AEREO
            dias_maximo += _DIAS_EXTRA_AEREO
            notas.append("carga aerea: sin via terrestre al destino")
        manejo = 0
        if paquete.valor_declarado_centavos > 0 and operador.comision_manejo > 0:
            manejo = max(
                aplicar_tarifa(paquete.valor_declarado_centavos, operador.comision_manejo),
                operador.manejo_minimo_centavos,
            )
        recaudo = 0
        if contraentrega:
            recaudo = max(
                aplicar_tarifa(monto_a_recaudar_centavos, operador.comision_recaudo),
                operador.recaudo_minimo_centavos,
            )
            notas.append(f"recaudo contra entrega hasta {operador.recaudo_maximo_centavos // 100}")
        if ciudad.regimen_iva_especial:
            notas.append("destino con regimen especial de IVA")
        opciones.append(
            Cotizacion(
                transportadora=operador.nombre,
                codigo_transportadora=operador.codigo,
                ciudad=ciudad,
                peso_facturable_gramos=peso,
                flete_centavos=flete,
                recargo_aereo_centavos=recargo,
                manejo_centavos=manejo,
                recaudo_centavos=recaudo,
                dias_habiles_minimo=dias_minimo,
                dias_habiles_maximo=dias_maximo,
                contraentrega=contraentrega,
                notas=tuple(notas),
            )
        )
    return tuple(sorted(opciones, key=lambda c: (c.total_centavos, c.dias_habiles_maximo)))


def mejor_cotizacion(
    destino: str | Ciudad,
    paquete: Paquete,
    *,
    contraentrega: bool = False,
    monto_a_recaudar_centavos: Centavos = 0,
) -> Cotizacion | None:
    """La opcion mas barata, o ``None`` si nadie sirve el destino asi."""
    opciones = cotizar(
        destino,
        paquete,
        contraentrega=contraentrega,
        monto_a_recaudar_centavos=monto_a_recaudar_centavos,
    )
    return opciones[0] if opciones else None

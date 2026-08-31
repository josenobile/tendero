"""Catalogo de una microempresa real de barrio en Medellin.

Surtitienda La Milagrosa es una tienda de Manrique que vende abarrotes, fruver
y almuerzo. Se modela asi, y no como una tienda de camisetas, porque una
canasta de tienda colombiana atraviesa los cuatro regimenes de IVA a la vez: el
platano esta excluido, la leche exenta, el cafe al cinco por ciento, el jabon
al diecinueve y el almuerzo paga impuesto al consumo en vez de IVA. Un carrito
de siete lineas ya obliga a liquidar cinco tratamientos distintos.

Los precios son bases sin impuestos: el precio de gondola se calcula por
destino, porque en San Andres y en Leticia la misma referencia no causa IVA.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from tendero.domain.dinero import Centavos, redondear_efectivo
from tendero.domain.documento import Documento, TipoDocumento
from tendero.domain.envio import Ciudad, Paquete
from tendero.domain.errores import ProductoDesconocidoError
from tendero.domain.impuesto import LineaVenta, Regimen, liquidar_linea

__all__ = [
    "CATALOGO",
    "COMERCIO",
    "Carrito",
    "Categoria",
    "Comercio",
    "LineaCarrito",
    "Producto",
    "armar_carrito",
    "buscar",
    "obtener",
    "por_categoria",
    "precio_al_publico",
    "productos",
]


class Categoria(StrEnum):
    """Seccion de la tienda; agrupa lo que el cliente busca junto."""

    FRUVER = "fruver"
    LACTEOS_Y_HUEVOS = "lacteos_y_huevos"
    CARNICOS = "carnicos"
    ABARROTES = "abarrotes"
    CAFE_Y_CACAO = "cafe_y_cacao"
    PANADERIA = "panaderia"
    ASEO = "aseo"
    BEBIDAS = "bebidas"
    MASCOTAS = "mascotas"
    COMIDA_PREPARADA = "comida_preparada"


@dataclass(frozen=True, slots=True)
class Comercio:
    """Datos del vendedor que van en el encabezado de la factura."""

    nombre: str
    documento: Documento
    direccion: str
    ciudad_codigo_dane: str
    responsable_iva: bool
    correo: str


COMERCIO: Final = Comercio(
    nombre="Surtitienda La Milagrosa S.A.S.",
    documento=Documento.parse(TipoDocumento.NIT, "900123456-8"),
    direccion="Carrera 45 # 67-23, barrio Manrique",
    ciudad_codigo_dane="05001",
    responsable_iva=True,
    correo="pedidos@lamilagrosa.example.co",
)
"""Microempresa de ejemplo; el NIT es ficticio pero su digito de verificacion es real."""


@dataclass(frozen=True, slots=True)
class Producto:
    """Referencia vendible con su tratamiento tributario y su logistica."""

    sku: str
    nombre: str
    categoria: Categoria
    regimen: Regimen
    precio_base_centavos: Centavos
    peso_gramos: int
    largo_cm: int
    ancho_cm: int
    alto_cm: int
    fundamento: str
    exclusiones_retracto: frozenset[str] = frozenset()
    es_servicio: bool = False
    impuesto_saludable_incorporado: bool = False

    def linea_venta(self, cantidad: int = 1) -> LineaVenta:
        """Convierte la referencia en una linea liquidable."""
        return LineaVenta(
            descripcion=self.nombre,
            regimen=self.regimen,
            precio_unitario_centavos=self.precio_base_centavos,
            cantidad=cantidad,
        )


def _p(
    sku: str,
    nombre: str,
    categoria: Categoria,
    regimen: Regimen,
    precio: Centavos,
    peso: int,
    dimensiones: tuple[int, int, int],
    fundamento: str,
    *,
    exclusiones: tuple[str, ...] = (),
    servicio: bool = False,
    saludable: bool = False,
) -> tuple[str, Producto]:
    """Atajo de construccion para la tabla del catalogo."""
    largo, ancho, alto = dimensiones
    return sku, Producto(
        sku=sku,
        nombre=nombre,
        categoria=categoria,
        regimen=regimen,
        precio_base_centavos=precio,
        peso_gramos=peso,
        largo_cm=largo,
        ancho_cm=ancho,
        alto_cm=alto,
        fundamento=fundamento,
        exclusiones_retracto=frozenset(exclusiones),
        es_servicio=servicio,
        impuesto_saludable_incorporado=saludable,
    )


_PERECEDERO: Final = ("perecedero",)
_ART_424: Final = "Art. 424 ET: bien excluido del IVA"
_ART_477: Final = "Art. 477 ET: bien exento, gravado a tarifa cero"
_ART_468_1: Final = "Art. 468-1 ET: tarifa diferencial del cinco por ciento"
_ART_468: Final = "Art. 468 ET: tarifa general del diecinueve por ciento"
_ART_512_1: Final = "Art. 512-1 num. 3 ET: expendio de comidas, impuesto al consumo"

CATALOGO: Final[Mapping[str, Producto]] = MappingProxyType(
    dict(
        (
            _p(
                "FRU-PLA-LB",
                "Platano maduro (libra)",
                Categoria.FRUVER,
                Regimen.EXCLUIDO,
                2_800_00,
                500,
                (20, 12, 8),
                _ART_424,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "FRU-TOM-LB",
                "Tomate chonto (libra)",
                Categoria.FRUVER,
                Regimen.EXCLUIDO,
                3_500_00,
                500,
                (18, 14, 10),
                _ART_424,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "FRU-AGU-UN",
                "Aguacate hass (unidad)",
                Categoria.FRUVER,
                Regimen.EXCLUIDO,
                4_500_00,
                280,
                (12, 10, 10),
                _ART_424,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "FRU-PAP-LB",
                "Papa pastusa (libra)",
                Categoria.FRUVER,
                Regimen.EXCLUIDO,
                2_200_00,
                500,
                (18, 14, 10),
                _ART_424,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "ABA-PAN-500",
                "Panela redonda 500 g",
                Categoria.ABARROTES,
                Regimen.EXCLUIDO,
                4_200_00,
                520,
                (14, 14, 5),
                _ART_424,
            ),
            _p(
                "ABA-ARR-500",
                "Arroz blanco 500 g",
                Categoria.ABARROTES,
                Regimen.EXCLUIDO,
                3_400_00,
                500,
                (18, 11, 5),
                _ART_424,
            ),
            _p(
                "PAN-ARE-X5",
                "Arepa de maiz para asar x5",
                Categoria.PANADERIA,
                Regimen.EXCLUIDO,
                4_800_00,
                600,
                (16, 16, 6),
                _ART_424,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "LAC-HUE-X30",
                "Huevos AA x30",
                Categoria.LACTEOS_Y_HUEVOS,
                Regimen.EXENTO,
                18_500_00,
                1800,
                (30, 30, 8),
                _ART_477,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "LAC-LEC-1L",
                "Leche entera bolsa 1 L",
                Categoria.LACTEOS_Y_HUEVOS,
                Regimen.EXENTO,
                4_300_00,
                1030,
                (18, 10, 8),
                _ART_477,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "LAC-QUE-250",
                "Queso campesino 250 g",
                Categoria.LACTEOS_Y_HUEVOS,
                Regimen.EXENTO,
                9_800_00,
                260,
                (12, 10, 6),
                _ART_477,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "CAR-RES-500",
                "Carne de res molida 500 g",
                Categoria.CARNICOS,
                Regimen.EXENTO,
                14_500_00,
                520,
                (18, 12, 5),
                _ART_477,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "CAR-POL-500",
                "Pechuga de pollo 500 g",
                Categoria.CARNICOS,
                Regimen.EXENTO,
                11_900_00,
                520,
                (20, 12, 5),
                _ART_477,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "CAF-TOS-250",
                "Cafe tostado molido de Antioquia 250 g",
                Categoria.CAFE_Y_CACAO,
                Regimen.GRAVADO_5,
                14_200_00,
                260,
                (14, 9, 5),
                _ART_468_1,
            ),
            _p(
                "CAF-CHO-500",
                "Chocolate de mesa 500 g",
                Categoria.CAFE_Y_CACAO,
                Regimen.GRAVADO_5,
                9_150_00,
                520,
                (16, 10, 6),
                _ART_468_1,
            ),
            _p(
                "ABA-PAS-500",
                "Pasta espagueti 500 g",
                Categoria.ABARROTES,
                Regimen.GRAVADO_5,
                3_700_00,
                500,
                (26, 8, 5),
                _ART_468_1,
            ),
            _p(
                "ABA-HAR-500",
                "Harina de trigo 500 g",
                Categoria.ABARROTES,
                Regimen.GRAVADO_5,
                3_050_00,
                500,
                (18, 11, 5),
                _ART_468_1,
            ),
            _p(
                "CAR-SAL-250",
                "Salchichon cervecero 250 g",
                Categoria.CARNICOS,
                Regimen.GRAVADO_5,
                8_475_00,
                260,
                (22, 7, 7),
                _ART_468_1,
                exclusiones=_PERECEDERO,
            ),
            _p(
                "ASE-JAB-X3",
                "Jabon de barra x3",
                Categoria.ASEO,
                Regimen.GRAVADO_19,
                7_900_00,
                450,
                (18, 9, 6),
                _ART_468,
            ),
            _p(
                "ASE-PAP-X4",
                "Papel higienico x4 rollos",
                Categoria.ASEO,
                Regimen.GRAVADO_19,
                7_300_00,
                480,
                (24, 24, 12),
                _ART_468,
            ),
            _p(
                "ASE-DET-1K",
                "Detergente en polvo 1 kg",
                Categoria.ASEO,
                Regimen.GRAVADO_19,
                10_500_00,
                1050,
                (22, 14, 7),
                _ART_468,
            ),
            _p(
                "BEB-GAS-15",
                "Gaseosa 1,5 L",
                Categoria.BEBIDAS,
                Regimen.GRAVADO_19,
                4_550_00,
                1600,
                (10, 10, 33),
                _ART_468,
                saludable=True,
            ),
            _p(
                "ABA-GAL-300",
                "Galletas dulces 300 g",
                Categoria.ABARROTES,
                Regimen.GRAVADO_19,
                5_700_00,
                320,
                (20, 12, 6),
                _ART_468,
                saludable=True,
            ),
            _p(
                "MAS-CON-2K",
                "Concentrado para perro adulto 2 kg",
                Categoria.MASCOTAS,
                Regimen.GRAVADO_19,
                24_300_00,
                2100,
                (30, 20, 10),
                _ART_468,
            ),
            _p(
                "PRE-ALM-COR",
                "Almuerzo corrientazo del dia",
                Categoria.COMIDA_PREPARADA,
                Regimen.INC_8,
                14_800_00,
                700,
                (20, 20, 8),
                _ART_512_1,
                exclusiones=("perecedero", "servicio_iniciado"),
                servicio=True,
            ),
        )
    )
)


def _plegar(texto: str) -> str:
    """Quita tildes y baja a minusculas para buscar como escribe la gente."""
    descompuesto = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def productos() -> tuple[Producto, ...]:
    """Todo el catalogo en orden estable."""
    return tuple(CATALOGO.values())


def obtener(sku: str) -> Producto:
    """Busca por SKU exacto; falla si no existe."""
    clave = sku.strip().upper()
    if clave not in CATALOGO:
        msg = f"el SKU {sku!r} no existe en el catalogo"
        raise ProductoDesconocidoError(msg)
    return CATALOGO[clave]


def buscar(texto: str) -> tuple[Producto, ...]:
    """Busca por nombre o categoria, tolerando tildes y mayusculas."""
    objetivo = _plegar(texto)
    if not objetivo:
        return ()
    return tuple(
        p
        for p in CATALOGO.values()
        if objetivo in _plegar(p.nombre) or objetivo in _plegar(p.categoria.value)
    )


def por_categoria(categoria: Categoria) -> tuple[Producto, ...]:
    """Referencias de una seccion de la tienda."""
    return tuple(p for p in CATALOGO.values() if p.categoria is categoria)


def precio_al_publico(
    producto: Producto,
    *,
    destino: Ciudad | None = None,
    responsable_iva: bool = True,
    redondear: bool = True,
) -> Centavos:
    """Precio de gondola con impuestos, redondeado a la moneda mas pequena.

    Depende del destino a proposito: la misma referencia vale menos en San
    Andres o en Leticia porque alli la venta no causa IVA.
    """
    liquidada = liquidar_linea(
        producto.linea_venta(1), destino=destino, responsable_iva=responsable_iva
    )
    return redondear_efectivo(liquidada.total_centavos) if redondear else liquidada.total_centavos


@dataclass(frozen=True, slots=True)
class LineaCarrito:
    """Una referencia con su cantidad."""

    producto: Producto
    cantidad: int

    def __post_init__(self) -> None:
        """Una linea de carrito con cantidad no positiva no tiene sentido."""
        if self.cantidad <= 0:
            msg = f"{self.producto.sku}: la cantidad debe ser positiva"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Carrito:
    """Pedido en construccion, con lo que necesitan flete, IVA y retracto."""

    lineas: tuple[LineaCarrito, ...]

    @property
    def peso_gramos(self) -> int:
        """Peso real del pedido, sin contar empaque."""
        return sum(linea.producto.peso_gramos * linea.cantidad for linea in self.lineas)

    @property
    def contiene_servicios(self) -> bool:
        """Cierto si hay algo que no se puede despachar en una caja."""
        return any(linea.producto.es_servicio for linea in self.lineas)

    @property
    def exclusiones_retracto(self) -> frozenset[str]:
        """Union de las causales que dejan el pedido fuera del retracto."""
        return frozenset().union(*(linea.producto.exclusiones_retracto for linea in self.lineas))

    @property
    def lleva_impuestos_saludables(self) -> bool:
        """Cierto si hay referencias con IBUA o ICUI ya incluido en el costo."""
        return any(linea.producto.impuesto_saludable_incorporado for linea in self.lineas)

    @property
    def despachables(self) -> tuple[LineaCarrito, ...]:
        """Lineas con bulto fisico; un servicio no lo recoge ninguna transportadora."""
        return tuple(linea for linea in self.lineas if not linea.producto.es_servicio)

    @property
    def tiene_despachables(self) -> bool:
        """Cierto si hay algo que cotizar con una transportadora.

        Un carrito de solo almuerzos existe y se factura, pero no se despacha:
        preguntarlo antes evita pedirle una cotizacion imposible al dominio.
        """
        return bool(self.despachables)

    def lineas_venta(self) -> tuple[LineaVenta, ...]:
        """Lineas liquidables para :func:`tendero.domain.impuesto.liquidar`."""
        return tuple(linea.producto.linea_venta(linea.cantidad) for linea in self.lineas)

    def paquete(self, *, valor_declarado_centavos: Centavos = 0) -> Paquete:
        """Bulto equivalente del pedido: caja mas ancha y altura apilada."""
        despachables = self.despachables
        if not despachables:
            msg = "el pedido no tiene nada fisico que despachar"
            raise ValueError(msg)
        largo = max(linea.producto.largo_cm for linea in despachables)
        ancho = max(linea.producto.ancho_cm for linea in despachables)
        alto = sum(linea.producto.alto_cm * linea.cantidad for linea in despachables)
        peso = sum(linea.producto.peso_gramos * linea.cantidad for linea in despachables)
        return Paquete(
            peso_gramos=peso,
            largo_cm=largo,
            ancho_cm=ancho,
            alto_cm=alto,
            valor_declarado_centavos=valor_declarado_centavos,
        )


def armar_carrito(items: Mapping[str, int] | Iterable[tuple[str, int]]) -> Carrito:
    """Construye un carrito desde pares de SKU y cantidad."""
    pares = items.items() if isinstance(items, Mapping) else items
    return Carrito(tuple(LineaCarrito(obtener(sku), cantidad) for sku, cantidad in pares))

"""Pruebas del catalogo de la tienda de Manrique."""

from __future__ import annotations

import pytest

from tendero.domain.catalogo import (
    CATALOGO,
    COMERCIO,
    Carrito,
    Categoria,
    LineaCarrito,
    armar_carrito,
    buscar,
    obtener,
    por_categoria,
    precio_al_publico,
    productos,
)
from tendero.domain.documento import TipoDocumento, calcular_dv_nit
from tendero.domain.envio import CIUDADES
from tendero.domain.errores import ProductoDesconocidoError
from tendero.domain.impuesto import Regimen, liquidar
from tendero.domain.retracto import CATEGORIAS_SIN_RETRACTO

MEDELLIN = CIUDADES["05001"]
SAN_ANDRES = CIUDADES["88001"]


def test_el_comercio_tiene_identidad_valida() -> None:
    """El NIT del vendedor encabeza la factura y tiene que pasar el algoritmo."""
    assert COMERCIO.documento.tipo is TipoDocumento.NIT
    assert COMERCIO.documento.dv == calcular_dv_nit(COMERCIO.documento.numero)
    assert COMERCIO.documento.es_persona_juridica
    assert COMERCIO.ciudad_codigo_dane in CIUDADES


def test_el_catalogo_no_esta_vacio_y_los_sku_son_unicos() -> None:
    """El SKU es la clave con la que el agente arma el carrito."""
    assert len(CATALOGO) == len(productos()) >= 20
    assert len({p.sku for p in productos()}) == len(CATALOGO)
    for sku, producto in CATALOGO.items():
        assert sku == producto.sku == sku.upper()


def test_el_catalogo_ejercita_los_cinco_regimenes() -> None:
    """Es el motivo de elegir una tienda de barrio y no una de camisetas."""
    presentes = {p.regimen for p in productos()}
    assert presentes == set(Regimen)


def test_todos_los_productos_citan_su_fundamento() -> None:
    """Un precio sin norma detras no se puede defender ante la DIAN."""
    for producto in productos():
        assert producto.fundamento.startswith("Art.")
        assert producto.precio_base_centavos > 0
        assert producto.peso_gramos > 0
        assert min(producto.largo_cm, producto.ancho_cm, producto.alto_cm) > 0


def test_las_exclusiones_de_retracto_son_causales_legales() -> None:
    """Un producto no puede inventar su propia causal para no devolverse."""
    for producto in productos():
        assert producto.exclusiones_retracto <= CATEGORIAS_SIN_RETRACTO


def test_obtener_por_sku() -> None:
    """La busqueda exacta tolera minusculas y espacios."""
    assert obtener("ASE-JAB-X3").nombre == "Jabon de barra x3"
    assert obtener(" ase-jab-x3 ").sku == "ASE-JAB-X3"


def test_obtener_sku_inexistente() -> None:
    """Un SKU inventado falla con el nombre del SKU en el mensaje."""
    with pytest.raises(ProductoDesconocidoError, match="XXX-000"):
        obtener("XXX-000")


@pytest.mark.parametrize(
    ("consulta", "sku"),
    [
        ("cafe", "CAF-TOS-250"),
        ("CAFÉ", "CAF-TOS-250"),
        ("platano", "FRU-PLA-LB"),
        ("Salchichon", "CAR-SAL-250"),
        ("fruver", "FRU-TOM-LB"),
    ],
)
def test_buscar_tolera_tildes_y_mayusculas(consulta: str, sku: str) -> None:
    """El cliente escribe como habla; la busqueda no puede ser literal."""
    assert sku in {p.sku for p in buscar(consulta)}


def test_buscar_vacio() -> None:
    """Una busqueda en blanco no vuelca el catalogo entero."""
    assert buscar("  ") == ()


def test_por_categoria() -> None:
    """Las secciones agrupan lo que el cliente pide junto."""
    fruver = por_categoria(Categoria.FRUVER)
    assert len(fruver) >= 4
    assert all(p.categoria is Categoria.FRUVER for p in fruver)


@pytest.mark.parametrize(
    ("sku", "publico"),
    [
        ("ASE-JAB-X3", 9_400_00),
        ("ASE-PAP-X4", 8_700_00),
        ("ASE-DET-1K", 12_500_00),
        ("BEB-GAS-15", 5_400_00),
        ("MAS-CON-2K", 28_900_00),
        ("CAF-TOS-250", 14_900_00),
        ("CAF-CHO-500", 9_600_00),
        ("ABA-PAS-500", 3_900_00),
        ("CAR-SAL-250", 8_900_00),
        ("LAC-LEC-1L", 4_300_00),
        ("FRU-PLA-LB", 2_800_00),
        ("PRE-ALM-COR", 16_000_00),
    ],
)
def test_precio_de_gondola_en_medellin(sku: str, publico: int) -> None:
    """El precio de vitrina sale de la base mas su impuesto, redondeado a cincuenta."""
    assert precio_al_publico(obtener(sku), destino=MEDELLIN) == publico


def test_el_mismo_producto_cuesta_menos_en_san_andres() -> None:
    """Art. 423 ET: la venta al archipielago no causa IVA, y el precio lo refleja."""
    jabon = obtener("ASE-JAB-X3")
    assert precio_al_publico(jabon, destino=SAN_ANDRES) == 7_900_00
    assert precio_al_publico(jabon, destino=MEDELLIN) == 9_400_00


def test_un_excluido_cuesta_lo_mismo_en_todas_partes() -> None:
    """El platano ya estaba fuera del impuesto: el destino no lo cambia."""
    platano = obtener("FRU-PLA-LB")
    assert precio_al_publico(platano, destino=SAN_ANDRES) == precio_al_publico(
        platano, destino=MEDELLIN
    )


def test_precio_sin_redondear_conserva_el_centavo() -> None:
    """Para facturar se necesita el valor exacto, no el de la etiqueta."""
    jabon = obtener("ASE-JAB-X3")
    assert precio_al_publico(jabon, redondear=False) == 9_401_00


def test_precio_para_comercio_no_responsable_de_iva() -> None:
    """Una tienda pequena que no es responsable no puede cobrar el impuesto."""
    jabon = obtener("ASE-JAB-X3")
    assert precio_al_publico(jabon, responsable_iva=False) == 7_900_00


def test_armar_carrito_desde_diccionario_y_desde_pares() -> None:
    """El agente puede mandar el pedido en cualquiera de las dos formas."""
    desde_dict = armar_carrito({"FRU-PLA-LB": 2, "LAC-LEC-1L": 3})
    desde_pares = armar_carrito([("FRU-PLA-LB", 2), ("LAC-LEC-1L", 3)])
    assert desde_dict == desde_pares
    assert desde_dict.peso_gramos == 2 * 500 + 3 * 1030


def test_linea_de_carrito_rechaza_cantidad_no_positiva() -> None:
    """Pedir cero unidades es un error del agente, no un carrito vacio."""
    with pytest.raises(ValueError, match="positiva"):
        LineaCarrito(obtener("FRU-PLA-LB"), 0)


def test_el_carrito_reporta_servicios_y_exclusiones() -> None:
    """El almuerzo es servicio y perecedero: dos razones para no despacharlo."""
    carrito = armar_carrito({"PRE-ALM-COR": 1, "ASE-JAB-X3": 1})
    assert carrito.contiene_servicios
    assert carrito.exclusiones_retracto == {"perecedero", "servicio_iniciado"}


def test_un_carrito_de_aseo_no_tiene_exclusiones() -> None:
    """El jabon si se puede devolver dentro del plazo."""
    carrito = armar_carrito({"ASE-JAB-X3": 2})
    assert not carrito.contiene_servicios
    assert carrito.exclusiones_retracto == frozenset()


def test_impuestos_saludables_marcados_pero_no_cobrados() -> None:
    """El IBUA y el ICUI son monofasicos: la tienda no los liquida."""
    carrito = armar_carrito({"BEB-GAS-15": 1})
    assert carrito.lleva_impuestos_saludables
    liquidacion = liquidar(carrito.lineas_venta())
    assert liquidacion.iva_centavos == 864_50
    assert liquidacion.total_centavos == 5_414_50


def test_el_paquete_del_carrito_apila_alturas_y_suma_pesos() -> None:
    """La caja equivalente es la base mas ancha con todo apilado dentro."""
    carrito = armar_carrito({"ASE-PAP-X4": 2, "LAC-LEC-1L": 1})
    paquete = carrito.paquete(valor_declarado_centavos=25_000_00)
    assert paquete.peso_gramos == 2 * 480 + 1030
    assert paquete.largo_cm == 24
    assert paquete.ancho_cm == 24
    assert paquete.alto_cm == 2 * 12 + 8
    assert paquete.valor_declarado_centavos == 25_000_00


def test_el_paquete_ignora_los_servicios() -> None:
    """El almuerzo no viaja en la caja y no pesa en el flete."""
    carrito = armar_carrito({"PRE-ALM-COR": 1, "ASE-JAB-X3": 1})
    assert carrito.paquete().peso_gramos == 450


def test_un_carrito_solo_de_servicios_no_se_despacha() -> None:
    """No hay bulto que cotizar: el error se lanza antes de llamar al flete."""
    carrito = armar_carrito({"PRE-ALM-COR": 2})
    with pytest.raises(ValueError, match="nada fisico"):
        carrito.paquete()


def test_el_carrito_es_inmutable() -> None:
    """El pedido no puede mutar entre la cotizacion y el cobro."""
    carrito = Carrito((LineaCarrito(obtener("ASE-JAB-X3"), 1),))
    with pytest.raises(AttributeError):
        carrito.lineas = ()  # type: ignore[misc]


def test_lineas_venta_conserva_cantidades() -> None:
    """La conversion a lineas facturables no puede perder unidades."""
    carrito = armar_carrito({"ASE-JAB-X3": 3, "LAC-LEC-1L": 2})
    lineas = carrito.lineas_venta()
    assert [x.cantidad for x in lineas] == [3, 2]
    assert lineas[0].bruto_centavos == 3 * 7_900_00


def test_el_carrito_separa_lo_que_se_puede_despachar() -> None:
    """Un almuerzo se factura, pero ninguna transportadora lo recoge."""
    mixto = armar_carrito({"ASE-JAB-X3": 1, "PRE-ALM-COR": 2})
    assert mixto.tiene_despachables
    assert [linea.producto.sku for linea in mixto.despachables] == ["ASE-JAB-X3"]
    assert mixto.paquete().peso_gramos == 450

    solo_servicio = armar_carrito({"PRE-ALM-COR": 1})
    assert not solo_servicio.tiene_despachables
    assert solo_servicio.despachables == ()
    with pytest.raises(ValueError, match="nada fisico que despachar"):
        solo_servicio.paquete()

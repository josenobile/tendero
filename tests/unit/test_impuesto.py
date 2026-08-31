"""Pruebas del IVA colombiano, con enfasis en exento frente a excluido."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tendero.domain.envio import CIUDADES, Ciudad
from tendero.domain.impuesto import (
    TARIFA_INC_RESTAURANTES,
    TARIFA_IVA_GENERAL,
    TARIFA_IVA_REDUCIDA,
    TRATAMIENTOS,
    LineaVenta,
    Regimen,
    liquidar,
    liquidar_linea,
    resumen_descontables,
)

MEDELLIN = CIUDADES["05001"]
SAN_ANDRES = CIUDADES["88001"]
LETICIA = CIUDADES["91001"]
PUERTO_CARRENO = CIUDADES["99001"]


def test_tarifas_publicadas() -> None:
    """Las tarifas son las del Estatuto Tributario, no parametros libres."""
    tarifas = (TARIFA_IVA_GENERAL, TARIFA_IVA_REDUCIDA, TARIFA_INC_RESTAURANTES)
    assert tarifas == (Decimal("0.19"), Decimal("0.05"), Decimal("0.08"))


def test_iva_general_sobre_una_linea() -> None:
    """Dos jabones de siete mil novecientos causan tres mil quinientos setenta y dos."""
    linea = liquidar_linea(LineaVenta("Jabon x3", Regimen.GRAVADO_19, 7_900_00, 2))
    assert linea.base_gravable_centavos == 15_800_00
    assert linea.impuesto_centavos == 3_002_00
    assert linea.total_centavos == 18_802_00


def test_iva_reducido_del_cinco_por_ciento() -> None:
    """El cafe tostado paga cinco por ciento, no diecinueve."""
    linea = liquidar_linea(LineaVenta("Cafe 250 g", Regimen.GRAVADO_5, 14_200_00))
    assert linea.impuesto_centavos == 710_00
    assert linea.fundamento == "Art. 468-1 ET"


def test_redondeo_de_medio_centavo_hacia_arriba() -> None:
    """Cincuenta centavos al diecinueve por ciento dan nueve y medio: sube a diez."""
    linea = liquidar_linea(LineaVenta("Prueba", Regimen.GRAVADO_19, 50))
    assert linea.impuesto_centavos == 10


def test_exento_es_tarifa_cero_con_derecho_a_descontables() -> None:
    """El exento va en la factura con linea de IVA al cero por ciento."""
    linea = liquidar_linea(LineaVenta("Leche 1 L", Regimen.EXENTO, 4_300_00, 3))
    assert linea.tributo == "IVA"
    assert linea.tarifa == Decimal("0")
    assert linea.impuesto_centavos == 0
    assert linea.da_derecho_a_descontables
    assert linea.fundamento == "Art. 477 ET"


def test_excluido_no_causa_impuesto_ni_da_derecho() -> None:
    """El excluido no lleva linea de impuesto y el IVA de insumos se vuelve costo."""
    linea = liquidar_linea(LineaVenta("Platano", Regimen.EXCLUIDO, 2_800_00, 4))
    assert linea.tributo is None
    assert linea.impuesto_centavos == 0
    assert not linea.da_derecho_a_descontables
    assert linea.fundamento == "Art. 424 ET"


def test_exento_y_excluido_pagan_lo_mismo_pero_no_son_lo_mismo() -> None:
    """Mismo total para el cliente, consecuencia distinta para el vendedor."""
    exento = liquidar_linea(LineaVenta("Leche", Regimen.EXENTO, 10_000_00))
    excluido = liquidar_linea(LineaVenta("Papa", Regimen.EXCLUIDO, 10_000_00))
    assert exento.total_centavos == excluido.total_centavos
    assert exento.da_derecho_a_descontables != excluido.da_derecho_a_descontables
    assert exento.tributo != excluido.tributo


def test_el_exento_aparece_en_el_bloque_de_impuestos_y_el_excluido_no() -> None:
    """La diferencia legal se ve en el XML: uno declara base, el otro no existe."""
    liquidacion = liquidar(
        [
            LineaVenta("Leche", Regimen.EXENTO, 4_300_00),
            LineaVenta("Platano", Regimen.EXCLUIDO, 2_800_00),
        ]
    )
    assert len(liquidacion.subtotales) == 1
    subtotal = liquidacion.subtotales[0]
    assert subtotal.tributo == "IVA"
    assert subtotal.tarifa_porcentual == "0,00"
    assert subtotal.base_centavos == 4_300_00
    assert subtotal.valor_centavos == 0


def test_comida_preparada_paga_consumo_y_no_iva() -> None:
    """El expendio de comidas paga INC del ocho por ciento en lugar de IVA."""
    liquidacion = liquidar([LineaVenta("Corrientazo", Regimen.INC_8, 14_800_00)])
    assert liquidacion.iva_centavos == 0
    assert liquidacion.inc_centavos == 1_184_00
    assert liquidacion.total_centavos == 15_984_00
    assert not liquidacion.lineas[0].da_derecho_a_descontables


def test_el_total_es_la_suma_de_las_lineas() -> None:
    """La DIAN valida linea a linea: el agregado no puede diferir ni un centavo."""
    lineas = [
        LineaVenta("Jabon", Regimen.GRAVADO_19, 7_900_00, 3),
        LineaVenta("Cafe", Regimen.GRAVADO_5, 14_200_00, 2),
        LineaVenta("Leche", Regimen.EXENTO, 4_300_00, 5),
        LineaVenta("Papa", Regimen.EXCLUIDO, 2_200_00, 7),
        LineaVenta("Corrientazo", Regimen.INC_8, 14_800_00),
    ]
    liquidacion = liquidar(lineas)
    assert liquidacion.total_centavos == sum(x.total_centavos for x in liquidacion.lineas)
    assert liquidacion.iva_centavos == sum(
        x.impuesto_centavos for x in liquidacion.lineas if x.tributo == "IVA"
    )
    assert liquidacion.base_gravable_centavos == sum(
        x.base_gravable_centavos for x in liquidacion.lineas
    )


def test_los_subtotales_agrupan_por_tributo_y_tarifa() -> None:
    """Es el bloque TaxSubTotal del UBL: una fila por tributo y tarifa."""
    liquidacion = liquidar(
        [
            LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00),
            LineaVenta("Detergente", Regimen.GRAVADO_19, 10_000_00),
            LineaVenta("Cafe", Regimen.GRAVADO_5, 10_000_00),
            LineaVenta("Corrientazo", Regimen.INC_8, 10_000_00),
        ]
    )
    filas = {
        (s.tributo, s.tarifa_porcentual): (s.base_centavos, s.valor_centavos)
        for s in liquidacion.subtotales
    }
    assert filas[("IVA", "19,00")] == (20_000_00, 3_800_00)
    assert filas[("IVA", "5,00")] == (10_000_00, 500_00)
    assert filas[("INC", "8,00")] == (10_000_00, 800_00)


def test_descuento_baja_la_base_gravable() -> None:
    """El descuento se resta antes del impuesto, no despues."""
    linea = liquidar_linea(
        LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00, 2, descuento_centavos=5_000_00)
    )
    assert linea.base_gravable_centavos == 15_000_00
    assert linea.impuesto_centavos == 2_850_00


@pytest.mark.parametrize("destino", [SAN_ANDRES, LETICIA, CIUDADES["97001"]])
def test_el_destino_puede_apagar_el_iva(destino: Ciudad) -> None:
    """San Andres por el Art. 423 ET y la Amazonia por la Ley 223 de 1995."""
    liquidacion = liquidar([LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00)], destino=destino)
    assert liquidacion.iva_centavos == 0
    assert liquidacion.total_centavos == 10_000_00
    assert liquidacion.lineas[0].regimen_solicitado is Regimen.GRAVADO_19
    assert liquidacion.lineas[0].regimen_aplicado is Regimen.EXCLUIDO
    assert liquidacion.notas


def test_vichada_no_tiene_regimen_especial_de_iva() -> None:
    """Puerto Carreno es aereo pero no esta en la exclusion territorial."""
    liquidacion = liquidar(
        [LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00)], destino=PUERTO_CARRENO
    )
    assert liquidacion.iva_centavos == 1_900_00


def test_medellin_si_causa_iva() -> None:
    """El caso base: en el continente el impuesto se cobra normal."""
    liquidacion = liquidar([LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00)], destino=MEDELLIN)
    assert liquidacion.iva_centavos == 1_900_00
    assert liquidacion.notas == ()


def test_el_consumo_no_se_apaga_por_destino() -> None:
    """La exclusion territorial habla del impuesto sobre las ventas, no del INC."""
    liquidacion = liquidar([LineaVenta("Corrientazo", Regimen.INC_8, 10_000_00)], destino=LETICIA)
    assert liquidacion.inc_centavos == 800_00


def test_comercio_no_responsable_de_iva_no_lo_cobra() -> None:
    """Art. 437 par. 3 ET: quien no es responsable no puede discriminar IVA."""
    liquidacion = liquidar(
        [LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00)], responsable_iva=False
    )
    assert liquidacion.iva_centavos == 0
    assert "no es responsable" in liquidacion.notas[0]


def test_resumen_descontables_separa_lo_recuperable() -> None:
    """La porcion excluida pierde el derecho a descontar el IVA de insumos."""
    liquidacion = liquidar(
        [
            LineaVenta("Leche", Regimen.EXENTO, 10_000_00),
            LineaVenta("Jabon", Regimen.GRAVADO_19, 10_000_00),
            LineaVenta("Papa", Regimen.EXCLUIDO, 30_000_00),
        ]
    )
    resumen = resumen_descontables(liquidacion)
    assert resumen.base_con_derecho_centavos == 20_000_00
    assert resumen.base_sin_derecho_centavos == 30_000_00
    assert "Art. 488" in resumen.nota


def test_resumen_descontables_cuando_todo_es_recuperable() -> None:
    """Sin lineas excluidas la nota cambia de tono."""
    liquidacion = liquidar([LineaVenta("Leche", Regimen.EXENTO, 10_000_00)])
    resumen = resumen_descontables(liquidacion)
    assert resumen.base_sin_derecho_centavos == 0
    assert "conserva el derecho" in resumen.nota


def test_liquidacion_vacia() -> None:
    """Un pedido sin lineas liquida en cero sin explotar."""
    liquidacion = liquidar([])
    assert liquidacion.total_centavos == 0
    assert liquidacion.subtotales == ()


@pytest.mark.parametrize(
    ("precio", "cantidad", "descuento"),
    [
        (10_000_00, 0, 0),
        (10_000_00, -1, 0),
        (-1, 1, 0),
        (10_000_00, 1, -1),
        (10_000_00, 1, 10_000_01),
    ],
)
def test_linea_venta_rechaza_datos_imposibles(precio: int, cantidad: int, descuento: int) -> None:
    """Una linea imposible se rechaza al construirla, no al facturarla."""
    with pytest.raises(ValueError, match=r"cantidad|precio|descuento"):
        LineaVenta("Prueba", Regimen.GRAVADO_19, precio, cantidad, descuento)


def test_todos_los_regimenes_tienen_tratamiento_y_fundamento() -> None:
    """Ningun regimen puede quedarse sin norma que lo respalde."""
    assert set(TRATAMIENTOS) == set(Regimen)
    for tratamiento in TRATAMIENTOS.values():
        assert tratamiento.fundamento.startswith("Art.")
        assert tratamiento.explicacion

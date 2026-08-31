"""Pruebas de la aritmetica en centavos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tendero.domain.dinero import (
    MULTIPLO_EFECTIVO,
    a_pesos,
    aplicar_tarifa,
    de_pesos,
    formatear_cop,
    redondear_a_pesos,
    redondear_efectivo,
    reparto_proporcional,
)


@pytest.mark.parametrize(
    ("base", "tarifa", "esperado"),
    [
        (18_800_00, Decimal("0.19"), 3_572_00),
        (100_00, Decimal("0.05"), 5_00),
        (0, Decimal("0.19"), 0),
        (50, Decimal("0.19"), 10),
        (150, Decimal("0.19"), 29),
    ],
)
def test_aplicar_tarifa_redondea_medio_centavo_hacia_arriba(
    base: int, tarifa: Decimal, esperado: int
) -> None:
    """Medio centavo sube: es el criterio con el que la DIAN valida la factura."""
    assert aplicar_tarifa(base, tarifa) == esperado


def test_aplicar_tarifa_nunca_devuelve_decimal() -> None:
    """El resultado tiene que ser entero para poder sumarse sin deriva."""
    assert isinstance(aplicar_tarifa(3_333_33, Decimal("0.19")), int)


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [(1_234_49, 1_234_00), (1_234_50, 1_235_00), (0, 0), (-1_234_50, -1_235_00)],
)
def test_redondear_a_pesos(monto: int, esperado: int) -> None:
    """Los centavos no circulan: el importe se lleva al peso mas cercano."""
    assert redondear_a_pesos(monto) == esperado


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [(9_401_00, 9_400_00), (9_425_00, 9_450_00), (9_424_00, 9_400_00), (24_00, 0)],
)
def test_redondear_efectivo_usa_la_moneda_de_cincuenta(monto: int, esperado: int) -> None:
    """El mensajero no da cambio por debajo de cincuenta pesos."""
    assert redondear_efectivo(monto) == esperado


def test_multiplo_efectivo_es_cincuenta_pesos() -> None:
    """La constante documenta la moneda mas pequena en circulacion."""
    assert MULTIPLO_EFECTIVO == 5000


def test_redondear_efectivo_rechaza_multiplo_no_positivo() -> None:
    """Un multiplo cero o negativo no define ningun redondeo."""
    with pytest.raises(ValueError, match="multiplo"):
        redondear_efectivo(1_000_00, multiplo=0)


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [
        (1_234_567_89, "$ 1.234.567"),
        (0, "$ 0"),
        (-9_400_00, "-$ 9.400"),
        (999_00, "$ 999"),
    ],
)
def test_formatear_cop_usa_punto_de_miles(monto: int, esperado: str) -> None:
    """Colombia separa miles con punto y decimales con coma."""
    assert formatear_cop(monto) == esperado


def test_formatear_cop_con_centavos() -> None:
    """Con centavos se usa coma decimal, no punto."""
    assert formatear_cop(1_234_567_89, con_centavos=True) == "$ 1.234.567,89"


def test_a_pesos_y_de_pesos_son_inversos() -> None:
    """La conversion de ida y vuelta no puede perder centavos."""
    assert de_pesos(a_pesos(9_400_37)) == 9_400_37
    assert a_pesos(9_400_37) == Decimal("9400.37")


def test_de_pesos_acepta_texto() -> None:
    """Un precio dictado como texto tambien se convierte sin float."""
    assert de_pesos("4300.50") == 4_300_50


def test_reparto_proporcional_no_pierde_ni_inventa_centavos() -> None:
    """El residuo del prorrateo cae en la ultima parte, nunca se descarta."""
    partes = reparto_proporcional(10_000_00, (1, 1, 1))
    assert sum(partes) == 10_000_00
    assert partes == (333_333, 333_333, 333_334)


def test_reparto_proporcional_respeta_los_pesos() -> None:
    """Una linea que vale el doble absorbe el doble del descuento."""
    assert reparto_proporcional(900_00, (2, 1)) == (60_000, 30_000)


def test_reparto_proporcional_vacio() -> None:
    """Repartir entre nadie devuelve nada, no falla."""
    assert reparto_proporcional(1_000_00, ()) == ()


def test_reparto_proporcional_rechaza_pesos_nulos() -> None:
    """Sin pesos positivos el reparto no esta definido."""
    with pytest.raises(ValueError, match="positivo"):
        reparto_proporcional(1_000_00, (0, 0))

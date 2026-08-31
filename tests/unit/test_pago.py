"""Pruebas de los rieles de pago y sus restricciones reales."""

from __future__ import annotations

import pytest

from tendero.domain import pago as modulo_pago
from tendero.domain.envio import CIUDADES, Ciudad
from tendero.domain.errores import MetodoPagoError
from tendero.domain.pago import (
    BANCOS_PSE,
    PARAMETROS_VIGENTES,
    SMMLV_TOPE_DEPOSITO_BAJO_MONTO,
    TARIFA_GMF,
    TARIFA_RETEFUENTE_TARJETAS,
    ContextoPago,
    EvaluacionPago,
    MetodoPago,
    evaluar,
    gmf,
    recomendar,
)

MEDELLIN = CIUDADES["05001"]
PASTO = CIUDADES["52001"]
LETICIA = CIUDADES["91001"]


def _contexto(
    *,
    total_centavos: int = 100_000_00,
    ciudad: Ciudad = MEDELLIN,
    base_sin_impuestos_centavos: int = 84_000_00,
    comision_recaudo_centavos: int = 6_000_00,
    contiene_servicios: bool = False,
    banco_pse: str | None = None,
    cliente_tiene_bancolombia: bool = False,
) -> ContextoPago:
    """Contexto base de un pedido mediano a Medellin."""
    return ContextoPago(
        total_centavos=total_centavos,
        ciudad=ciudad,
        base_sin_impuestos_centavos=base_sin_impuestos_centavos,
        comision_recaudo_centavos=comision_recaudo_centavos,
        contiene_servicios=contiene_servicios,
        banco_pse=banco_pse,
        cliente_tiene_bancolombia=cliente_tiene_bancolombia,
    )


def _por_metodo(contexto: ContextoPago) -> dict[MetodoPago, EvaluacionPago]:
    """Indexa la evaluacion por riel para leerla comodo en las pruebas."""
    return {e.metodo: e for e in evaluar(contexto)}


def test_se_evaluan_los_cinco_rieles_siempre() -> None:
    """Devolver tambien los rechazados es lo que permite explicar el porque."""
    resultados = evaluar(_contexto())
    assert {e.metodo for e in resultados} == set(MetodoPago)


def test_el_pedido_debe_tener_valor() -> None:
    """Un pedido en cero no se cobra por ningun riel."""
    with pytest.raises(ValueError, match="positivo"):
        ContextoPago(total_centavos=0, ciudad=MEDELLIN)


def test_los_disponibles_van_primero() -> None:
    """El orden es util para el agente: lo que si se puede, arriba."""
    resultados = evaluar(_contexto(cliente_tiene_bancolombia=True, banco_pse="Bancolombia"))
    disponibles = [e.disponible for e in resultados]
    assert disponibles == sorted(disponibles, reverse=True)


def test_nequi_tiene_techo_de_ocho_salarios_minimos() -> None:
    """Nequi es un deposito de bajo monto: la norma le pone el techo."""
    tope = SMMLV_TOPE_DEPOSITO_BAJO_MONTO * PARAMETROS_VIGENTES.smmlv_centavos
    assert PARAMETROS_VIGENTES.tope_deposito_bajo_monto_centavos == tope
    debajo = _por_metodo(_contexto(total_centavos=tope))[MetodoPago.NEQUI]
    encima = _por_metodo(_contexto(total_centavos=tope + 1))[MetodoPago.NEQUI]
    assert debajo.disponible
    assert not encima.disponible
    assert "deposito de bajo monto" in encima.motivos[0]


def test_nequi_se_acredita_al_instante() -> None:
    """El plazo de liquidacion decide cuando se puede despachar el pedido."""
    nequi = _por_metodo(_contexto())[MetodoPago.NEQUI]
    assert nequi.dias_habiles_liquidacion == 0


def test_pse_exige_banco() -> None:
    """PSE no arranca sin que el cliente elija entidad."""
    sin_banco = _por_metodo(_contexto())[MetodoPago.PSE]
    assert not sin_banco.disponible
    assert "elija su banco" in sin_banco.motivos[0]


@pytest.mark.parametrize("banco", ["Bancolombia", "DAVIVIENDA", "  Banco de Bogota ", "Nequi"])
def test_pse_acepta_bancos_reales_como_los_escribe_la_gente(banco: str) -> None:
    """El nombre llega dictado, con mayusculas y espacios de mas."""
    evaluacion = _por_metodo(_contexto(banco_pse=banco))[MetodoPago.PSE]
    assert evaluacion.disponible


def test_pse_rechaza_un_banco_inexistente() -> None:
    """Un banco que no esta en PSE no puede debitar."""
    evaluacion = _por_metodo(_contexto(banco_pse="Banco Imaginario"))[MetodoPago.PSE]
    assert not evaluacion.disponible
    assert "no esta habilitado" in evaluacion.motivos[0]


def test_pse_tiene_monto_minimo() -> None:
    """Por debajo del minimo la pasarela no procesa."""
    evaluacion = _por_metodo(_contexto(total_centavos=1_000_00, banco_pse="Bancolombia"))[
        MetodoPago.PSE
    ]
    assert not evaluacion.disponible


def test_bancolombia_exige_cuenta_en_la_misma_entidad() -> None:
    """La transferencia directa solo existe entre cuentas Bancolombia."""
    sin_cuenta = _por_metodo(_contexto())[MetodoPago.BANCOLOMBIA]
    con_cuenta = _por_metodo(_contexto(cliente_tiene_bancolombia=True))[MetodoPago.BANCOLOMBIA]
    assert not sin_cuenta.disponible
    assert con_cuenta.disponible


def test_tarjeta_cobra_comision_con_iva_y_retencion() -> None:
    """El costo del riel incluye el IVA de la comision y la retencion de renta."""
    tarjeta = _por_metodo(_contexto())[MetodoPago.TARJETA]
    assert tarjeta.comision_centavos == 4_629_10
    assert tarjeta.retencion_centavos == 1_260_00
    assert tarjeta.cuotas_maximas == 36
    assert tarjeta.dias_habiles_liquidacion == 2


def test_la_retencion_se_calcula_sobre_la_base_sin_impuestos() -> None:
    """La base de la retefuente es el valor de la venta, no el total facturado."""
    esperado = int(84_000_00 * TARIFA_RETEFUENTE_TARJETAS)
    tarjeta = _por_metodo(_contexto())[MetodoPago.TARJETA]
    assert tarjeta.retencion_centavos == esperado


def test_sin_base_declarada_la_retencion_usa_el_total() -> None:
    """Es el comportamiento conservador cuando el agente no manda el desglose."""
    tarjeta = _por_metodo(_contexto(base_sin_impuestos_centavos=0))[MetodoPago.TARJETA]
    assert tarjeta.retencion_centavos == 1_500_00


def test_tarjeta_tiene_monto_minimo() -> None:
    """Las franquicias no autorizan compras minusculas."""
    evaluacion = _por_metodo(_contexto(total_centavos=1_500_00))[MetodoPago.TARJETA]
    assert not evaluacion.disponible


def test_solo_la_tarjeta_ofrece_cuotas() -> None:
    """Comprar a cuotas es una funcion de la franquicia, no del comercio."""
    for metodo, evaluacion in _por_metodo(_contexto()).items():
        esperado = 36 if metodo is MetodoPago.TARJETA else 1
        assert evaluacion.cuotas_maximas == esperado


def test_contraentrega_no_existe_donde_solo_llega_el_avion() -> None:
    """La restriccion logistica se propaga hasta el medio de pago."""
    evaluacion = _por_metodo(_contexto(ciudad=LETICIA))[MetodoPago.CONTRAENTREGA]
    assert not evaluacion.disponible
    assert "aereo" in evaluacion.motivos[0]


def test_contraentrega_funciona_en_ciudad_intermedia() -> None:
    """Donde llega el camion, el cliente paga en efectivo al recibir."""
    evaluacion = _por_metodo(_contexto(ciudad=PASTO))[MetodoPago.CONTRAENTREGA]
    assert evaluacion.disponible
    assert evaluacion.dias_habiles_liquidacion == 8


def test_contraentrega_necesita_algo_fisico_que_entregar() -> None:
    """Un almuerzo consumido en el local no se paga contra entrega."""
    evaluacion = _por_metodo(_contexto(contiene_servicios=True))[MetodoPago.CONTRAENTREGA]
    assert not evaluacion.disponible
    assert "bulto fisico" in evaluacion.motivos[0]


def test_contraentrega_exige_haber_cotizado_el_recaudo() -> None:
    """Ofrecerlo sin conocer la comision seria prometer un precio inventado."""
    evaluacion = _por_metodo(_contexto(comision_recaudo_centavos=0))[MetodoPago.CONTRAENTREGA]
    assert not evaluacion.disponible
    assert "cotizar el recaudo" in evaluacion.motivos[0]


def test_el_recargo_de_contraentrega_se_redondea_a_cincuenta_pesos() -> None:
    """El mensajero no da cambio por debajo de la moneda de cincuenta."""
    evaluacion = _por_metodo(_contexto(comision_recaudo_centavos=6_037_00))[
        MetodoPago.CONTRAENTREGA
    ]
    assert evaluacion.recargo_cliente_centavos == 6_050_00
    assert evaluacion.total_cliente_centavos == 106_050_00


def test_gmf_es_el_cuatro_por_mil() -> None:
    """Todo lo que aterriza en una cuenta paga el gravamen del Art. 870 ET."""
    assert TARIFA_GMF * 1000 == 4
    assert gmf(1_000_000_00) == 4_000_00


def test_el_gmf_solo_se_cobra_sobre_lo_disponible() -> None:
    """Un riel que no aplica no genera movimiento financiero ni gravamen."""
    resultados = _por_metodo(_contexto())
    for evaluacion in resultados.values():
        if not evaluacion.disponible:
            assert evaluacion.gmf_centavos == 0


def test_el_neto_del_comercio_descuenta_todo() -> None:
    """La cuenta cierra: total del cliente menos comision, retencion y gravamen."""
    tarjeta = _por_metodo(_contexto())[MetodoPago.TARJETA]
    bruto = tarjeta.total_cliente_centavos - tarjeta.comision_centavos - tarjeta.retencion_centavos
    assert tarjeta.gmf_centavos == gmf(bruto)
    assert tarjeta.neto_comercio_centavos == bruto - gmf(bruto)
    assert tarjeta.costo_total_comercio_centavos == (
        tarjeta.comision_centavos + tarjeta.retencion_centavos + tarjeta.gmf_centavos
    )


def test_pse_le_deja_mas_al_comercio_que_la_tarjeta_en_pedidos_grandes() -> None:
    """Comision fija contra comision porcentual: la diferencia crece con el monto."""
    contexto = _contexto(total_centavos=2_000_000_00, banco_pse="Davivienda")
    resultados = _por_metodo(contexto)
    pse = resultados[MetodoPago.PSE]
    tarjeta = resultados[MetodoPago.TARJETA]
    assert pse.neto_comercio_centavos > tarjeta.neto_comercio_centavos


def test_recomendar_devuelve_un_riel_disponible() -> None:
    """La recomendacion nunca puede ser un riel que no aplica."""
    elegido = recomendar(_contexto(ciudad=PASTO))
    assert elegido.disponible


def test_recomendar_falla_cuando_no_hay_ningun_riel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin rieles disponibles el error es explicito y nombra la ciudad."""
    monkeypatch.setattr(modulo_pago, "_EVALUADORES", {})
    with pytest.raises(MetodoPagoError, match="Leticia"):
        recomendar(_contexto(ciudad=LETICIA))


def test_los_parametros_fiscales_llevan_su_ano() -> None:
    """El ano queda en el dato para que una cifra vieja se note."""
    assert PARAMETROS_VIGENTES.anio == 2025
    assert PARAMETROS_VIGENTES.exencion_gmf_mensual_centavos == 65 * 49_799_00


def test_los_bancos_pse_estan_normalizados() -> None:
    """La lista se compara en minusculas y sin tildes."""
    assert "bancolombia" in BANCOS_PSE
    assert all(banco == banco.lower() for banco in BANCOS_PSE)


def test_cada_riel_declara_sus_requisitos() -> None:
    """El agente necesita saber que datos pedirle al cliente antes de empezar."""
    for evaluacion in evaluar(_contexto(ciudad=PASTO)):
        assert evaluacion.requisitos
        assert evaluacion.nombre


def test_contraentrega_tiene_techo_de_recaudo() -> None:
    """Por encima del tope del operador la venta se cobra por adelantado."""
    dentro = _por_metodo(_contexto(total_centavos=2_000_000_00))[MetodoPago.CONTRAENTREGA]
    fuera = _por_metodo(_contexto(total_centavos=2_000_000_01))[MetodoPago.CONTRAENTREGA]
    assert dentro.disponible
    assert not fuera.disponible
    assert "recauda mas de" in fuera.motivos[0]
    assert "$ 2.000.000" in fuera.motivos[0]


def test_recomendar_recorre_los_rieles_hasta_agotarlos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si todos los rieles evaluados fallan, el recorrido termina en el error."""
    monkeypatch.setattr(
        modulo_pago,
        "_EVALUADORES",
        {MetodoPago.PSE: modulo_pago._evaluar_pse},
    )
    with pytest.raises(MetodoPagoError, match="Pasto"):
        recomendar(_contexto(ciudad=PASTO, banco_pse=None))

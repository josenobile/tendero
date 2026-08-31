"""Pruebas del flete y de la asimetria del contra entrega."""

from __future__ import annotations

import pytest

from tendero.domain.documento import calcular_dv_nit, separar_dv
from tendero.domain.envio import (
    CIUDADES,
    REGIMEN_IVA_ESPECIAL,
    SIN_CONTRAENTREGA,
    TRANSPORTADORAS,
    Paquete,
    Zona,
    buscar_ciudades,
    cotizar,
    diagnostico_contraentrega,
    mejor_cotizacion,
    resolver_ciudad,
    tope_contraentrega,
)
from tendero.domain.errores import CiudadDesconocidaError

MEDELLIN = CIUDADES["05001"]
PASTO = CIUDADES["52001"]
LETICIA = CIUDADES["91001"]
SAN_ANDRES = CIUDADES["88001"]

CAJA = Paquete(peso_gramos=2400, largo_cm=30, ancho_cm=20, alto_cm=15)


def test_el_maestro_cubre_los_tres_tramos() -> None:
    """Sin las tres zonas la tarifa no discrimina nada."""
    zonas = {ciudad.zona for ciudad in CIUDADES.values()}
    assert zonas == {Zona.METROPOLITANA, Zona.INTERMEDIA, Zona.REMOTA}


def test_los_codigos_dane_tienen_cinco_digitos() -> None:
    """El codigo DANE de municipio es siempre de cinco digitos."""
    for codigo in CIUDADES:
        assert len(codigo) == 5
        assert codigo.isdigit()


def test_el_valle_de_aburra_esta_completo() -> None:
    """Los diez municipios del area metropolitana comparten tarifa local."""
    aburra = {
        c.nombre
        for c in CIUDADES.values()
        if c.departamento == "Antioquia" and c.zona is Zona.METROPOLITANA
    }
    assert aburra == {
        "Medellin",
        "Bello",
        "Envigado",
        "Itagui",
        "Sabaneta",
        "La Estrella",
        "Caldas",
        "Copacabana",
        "Girardota",
        "Barbosa",
    }


@pytest.mark.parametrize(
    ("consulta", "codigo"),
    [
        ("05001", "05001"),
        ("5001", "05001"),
        ("Medellin", "05001"),
        ("medellin", "05001"),
        ("MEDELLÍN", "05001"),
        ("Bogota D.C.", "11001"),
        ("Ibagué", "73001"),
        ("San Andres", "88001"),
    ],
)
def test_resolver_ciudad_tolera_como_escribe_la_gente(consulta: str, codigo: str) -> None:
    """El agente recibe el destino dictado, con tildes o sin ellas."""
    assert resolver_ciudad(consulta).codigo_dane == codigo


def test_resolver_ciudad_desconocida_sugiere() -> None:
    """Un destino ambiguo devuelve alternativas en vez de un error mudo."""
    with pytest.raises(CiudadDesconocidaError, match="no se reconoce"):
        resolver_ciudad("Springfield")


def test_resolver_ciudad_acepta_coincidencia_parcial_unica() -> None:
    """Si solo hay una ciudad que contiene el texto, se resuelve sola."""
    assert resolver_ciudad("Valledup").codigo_dane == "20001"


def test_buscar_ciudades_vacio() -> None:
    """Una busqueda en blanco no devuelve el maestro completo."""
    assert buscar_ciudades("   ") == ()


def test_buscar_ciudades_por_departamento() -> None:
    """Se puede buscar por departamento porque la etiqueta lo incluye."""
    resultados = buscar_ciudades("Antioquia")
    assert {c.nombre for c in resultados} >= {"Medellin", "Rionegro", "Apartado"}


def test_peso_volumetrico_usa_el_factor_seis_mil() -> None:
    """Treinta por veinte por quince son nueve mil centimetros cubicos."""
    assert CAJA.peso_volumetrico_gramos == 1500
    assert CAJA.peso_facturable_gramos == 2400


def test_una_caja_grande_y_liviana_se_cobra_por_volumen() -> None:
    """Una caja de almohadas ocupa camion aunque no pese."""
    almohadas = Paquete(peso_gramos=800, largo_cm=60, ancho_cm=40, alto_cm=40)
    assert almohadas.peso_volumetrico_gramos == 16000
    assert almohadas.peso_facturable_gramos == 16000


def test_piso_de_un_kilo() -> None:
    """Ninguna guia se cobra por debajo de un kilo."""
    sobre = Paquete(peso_gramos=50, largo_cm=10, ancho_cm=10, alto_cm=1)
    assert sobre.peso_facturable_gramos == 1000


@pytest.mark.parametrize(
    ("peso", "alto", "valor"),
    [(0, 10, 0), (-5, 10, 0), (100, 0, 0), (100, 10, -1)],
)
def test_paquete_rechaza_datos_imposibles(peso: int, alto: int, valor: int) -> None:
    """Un bulto sin peso o sin volumen no se puede cotizar."""
    with pytest.raises(ValueError, match=r"deben? ser|puede ser"):
        Paquete(peso_gramos=peso, alto_cm=alto, valor_declarado_centavos=valor)


def test_cotizacion_ordenada_de_menor_a_mayor() -> None:
    """La primera opcion es siempre la mas barata."""
    opciones = cotizar(MEDELLIN, CAJA)
    totales = [o.total_centavos for o in opciones]
    assert totales == sorted(totales)


def test_medellin_tiene_mensajeria_local_y_pasto_no() -> None:
    """El mensajero de barrio solo existe dentro del Valle de Aburra."""
    locales = {o.codigo_transportadora for o in cotizar(MEDELLIN, CAJA)}
    remotos = {o.codigo_transportadora for o in cotizar(PASTO, CAJA)}
    assert "rapidito_aburra" in locales
    assert "rapidito_aburra" not in remotos


def test_envia_no_llega_a_zona_remota() -> None:
    """La cobertura de cada operador es distinta y eso cambia el precio."""
    assert "envia" in {o.codigo_transportadora for o in cotizar(PASTO, CAJA)}
    assert "envia" not in {o.codigo_transportadora for o in cotizar(LETICIA, CAJA)}


def test_zona_mas_lejana_cuesta_mas() -> None:
    """El precio sube por tramo, no por kilometro."""
    metro = mejor_cotizacion(MEDELLIN, CAJA)
    intermedia = mejor_cotizacion(PASTO, CAJA)
    remota = mejor_cotizacion(LETICIA, CAJA)
    assert metro is not None
    assert intermedia is not None
    assert remota is not None
    assert metro.total_centavos < intermedia.total_centavos < remota.total_centavos


def test_destino_solo_aereo_lleva_recargo_y_mas_dias() -> None:
    """Sin carretera la carga viaja en avion y el plazo se alarga."""
    terrestre = mejor_cotizacion(PASTO, CAJA)
    aereo = mejor_cotizacion(SAN_ANDRES, CAJA)
    assert terrestre is not None
    assert aereo is not None
    assert aereo.recargo_aereo_centavos > 0
    assert terrestre.recargo_aereo_centavos == 0
    assert aereo.dias_habiles_maximo > terrestre.dias_habiles_maximo
    assert any("aerea" in nota for nota in aereo.notas)


def test_kilos_adicionales_se_cobran_hacia_arriba() -> None:
    """Un gramo por encima del kilo ya cuenta como kilo completo."""
    liviano = Paquete(peso_gramos=1000, largo_cm=10, ancho_cm=10, alto_cm=10)
    apenas_mas = Paquete(peso_gramos=1001, largo_cm=10, ancho_cm=10, alto_cm=10)
    uno = next(o for o in cotizar(PASTO, liviano) if o.codigo_transportadora == "interrapidisimo")
    dos = next(
        o for o in cotizar(PASTO, apenas_mas) if o.codigo_transportadora == "interrapidisimo"
    )
    assert uno.flete_centavos == 13_900_00
    assert dos.flete_centavos == 13_900_00 + 4_100_00


def test_la_mensajeria_local_incluye_cinco_kilos() -> None:
    """El mensajero de barrio cobra plano hasta cinco kilos; ahi si cambia."""

    def flete(gramos: int) -> int:
        caja = Paquete(peso_gramos=gramos, largo_cm=10, ancho_cm=10, alto_cm=10)
        opciones = cotizar(MEDELLIN, caja)
        local = next(o for o in opciones if o.codigo_transportadora == "rapidito_aburra")
        return local.flete_centavos

    assert flete(1000) == flete(5000) == 7_000_00
    assert flete(5001) == 7_000_00 + 1_500_00


def test_valor_declarado_cobra_manejo_con_minimo() -> None:
    """El manejo es un porcentaje del valor declarado, con piso."""
    barato = Paquete(peso_gramos=1000, valor_declarado_centavos=10_000_00)
    caro = Paquete(peso_gramos=1000, valor_declarado_centavos=5_000_000_00)
    sin_valor = Paquete(peso_gramos=1000)
    opcion_barata = next(o for o in cotizar(PASTO, barato) if o.codigo_transportadora == "envia")
    opcion_cara = next(o for o in cotizar(PASTO, caro) if o.codigo_transportadora == "envia")
    opcion_nula = next(o for o in cotizar(PASTO, sin_valor) if o.codigo_transportadora == "envia")
    assert opcion_nula.manejo_centavos == 0
    assert opcion_barata.manejo_centavos == 2_500_00
    assert opcion_cara.manejo_centavos == 50_000_00


@pytest.mark.parametrize("codigo", sorted(SIN_CONTRAENTREGA))
def test_ningun_destino_solo_aereo_admite_contraentrega(codigo: str) -> None:
    """Esta es la asimetria completa: sin carretera no hay recaudo."""
    ciudad = CIUDADES[codigo]
    disponible, motivo = diagnostico_contraentrega(ciudad)
    assert not disponible
    assert "aereo" in motivo
    assert cotizar(ciudad, CAJA, contraentrega=True, monto_a_recaudar_centavos=50_000_00) == ()


def test_contraentrega_disponible_en_ciudades_con_carretera() -> None:
    """Donde llega el camion si se puede pagar al mensajero."""
    for ciudad in (MEDELLIN, PASTO, CIUDADES["27001"]):
        disponible, motivo = diagnostico_contraentrega(ciudad)
        assert disponible, ciudad.nombre
        assert "disponible con" in motivo


def test_diagnostico_acepta_nombre_de_ciudad() -> None:
    """El agente puede preguntar por nombre sin resolver el codigo antes."""
    disponible, _ = diagnostico_contraentrega("Leticia")
    assert not disponible


def test_coordinadora_nunca_aparece_en_contraentrega() -> None:
    """Un operador sin recaudo se filtra, no se ofrece y luego falla."""
    opciones = cotizar(PASTO, CAJA, contraentrega=True, monto_a_recaudar_centavos=100_000_00)
    assert opciones
    assert "coordinadora" not in {o.codigo_transportadora for o in opciones}


def test_el_tope_de_recaudo_filtra_operadores() -> None:
    """Un pedido grande deja por fuera a quien tiene el tope mas bajo."""
    codigos = {
        o.codigo_transportadora
        for o in cotizar(PASTO, CAJA, contraentrega=True, monto_a_recaudar_centavos=1_800_000_00)
    }
    assert "envia" not in codigos
    assert "servientrega" in codigos


def test_pedido_por_encima_de_todos_los_topes_no_tiene_contraentrega() -> None:
    """Por encima de dos millones nadie recauda: el agente debe saberlo."""
    assert cotizar(PASTO, CAJA, contraentrega=True, monto_a_recaudar_centavos=3_000_000_00) == ()


def test_la_comision_de_recaudo_respeta_el_minimo() -> None:
    """En pedidos pequenos manda el minimo, no el porcentaje."""
    opcion = next(
        o
        for o in cotizar(PASTO, CAJA, contraentrega=True, monto_a_recaudar_centavos=20_000_00)
        if o.codigo_transportadora == "interrapidisimo"
    )
    assert opcion.recaudo_centavos == 6_000_00
    grande = next(
        o
        for o in cotizar(PASTO, CAJA, contraentrega=True, monto_a_recaudar_centavos=500_000_00)
        if o.codigo_transportadora == "interrapidisimo"
    )
    assert grande.recaudo_centavos == 20_000_00


def test_total_es_la_suma_del_desglose() -> None:
    """El total no puede tener sumandos ocultos."""
    paquete = Paquete(peso_gramos=3000, valor_declarado_centavos=300_000_00)
    for opcion in cotizar(PASTO, paquete, contraentrega=True, monto_a_recaudar_centavos=300_000_00):
        assert opcion.total_centavos == (
            opcion.flete_centavos
            + opcion.recargo_aereo_centavos
            + opcion.manejo_centavos
            + opcion.recaudo_centavos
        )


def test_regimen_especial_marca_los_destinos_correctos() -> None:
    """San Andres, Providencia, Amazonas, Guainia y Vaupes; Vichada no."""
    assert set(REGIMEN_IVA_ESPECIAL) == {"88001", "88564", "91001", "91540", "94001", "97001"}
    assert "99001" in SIN_CONTRAENTREGA
    assert "99001" not in REGIMEN_IVA_ESPECIAL


def test_las_cotizaciones_a_regimen_especial_lo_advierten() -> None:
    """La nota viaja con la cotizacion para que el precio se explique solo."""
    opcion = mejor_cotizacion(LETICIA, CAJA)
    assert opcion is not None
    assert any("regimen especial" in nota for nota in opcion.notas)


def test_los_nits_de_las_transportadoras_son_validos() -> None:
    """Prueba cruzada: los NIT del maestro pasan el algoritmo de la DIAN."""
    verificados = 0
    for operador in TRANSPORTADORAS:
        if operador.nit is None:
            continue
        base, dv = separar_dv(operador.nit)
        assert dv is not None
        assert calcular_dv_nit(base) == dv, operador.nombre
        verificados += 1
    assert verificados >= 3


def test_mejor_cotizacion_devuelve_none_si_nadie_sirve() -> None:
    """Sin opciones se devuelve None, no una excepcion."""
    assert (
        mejor_cotizacion(SAN_ANDRES, CAJA, contraentrega=True, monto_a_recaudar_centavos=10_000_00)
        is None
    )


def test_etiqueta_de_ciudad_incluye_departamento() -> None:
    """Hay varios municipios llamados Caldas: el departamento desambigua."""
    assert CIUDADES["05129"].etiqueta == "Caldas, Antioquia"


def test_tope_de_contraentrega_por_destino() -> None:
    """El techo lo pone el operador mas generoso que cubra la ciudad."""
    assert tope_contraentrega(MEDELLIN) == 2_000_000_00
    assert tope_contraentrega("Pasto") == 2_000_000_00
    assert tope_contraentrega(LETICIA) == 0


def test_una_consulta_ambigua_devuelve_alternativas() -> None:
    """Con varias coincidencias el error enumera opciones en vez de adivinar."""
    with pytest.raises(CiudadDesconocidaError, match="quiza:"):
        resolver_ciudad("Antioquia")


def test_ciudad_sin_ningun_operador_de_recaudo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarda de datos: si algun dia nadie recauda en una ciudad, se dice claro."""
    solo_coordinadora = tuple(t for t in TRANSPORTADORAS if t.codigo == "coordinadora")
    monkeypatch.setattr("tendero.domain.envio.TRANSPORTADORAS", solo_coordinadora)
    disponible, motivo = diagnostico_contraentrega(PASTO)
    assert not disponible
    assert "ninguna transportadora con recaudo" in motivo
    assert tope_contraentrega(PASTO) == 0

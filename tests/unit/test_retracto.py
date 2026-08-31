"""Pruebas del calendario colombiano y del derecho de retracto."""

from __future__ import annotations

from datetime import date

import pytest

from tendero.domain.retracto import (
    CATEGORIAS_SIN_RETRACTO,
    DIAS_HABILES_RETRACTO,
    DIAS_PARA_DEVOLVER_DINERO,
    Modalidad,
    aplica_retracto,
    dias_habiles_entre,
    es_dia_habil,
    es_festivo,
    festivos,
    pascua,
    sumar_dias_habiles,
    ventana_retracto,
)

FESTIVOS_2026: tuple[tuple[str, str], ...] = (
    ("2026-01-01", "Ano Nuevo"),
    ("2026-01-12", "Reyes Magos"),
    ("2026-03-23", "Dia de San Jose"),
    ("2026-04-02", "Jueves Santo"),
    ("2026-04-03", "Viernes Santo"),
    ("2026-05-01", "Dia del Trabajo"),
    ("2026-05-18", "Ascension del Senor"),
    ("2026-06-08", "Corpus Christi"),
    ("2026-06-15", "Sagrado Corazon de Jesus"),
    ("2026-06-29", "San Pedro y San Pablo"),
    ("2026-07-20", "Dia de la Independencia"),
    ("2026-08-07", "Batalla de Boyaca"),
    ("2026-08-17", "Asuncion de la Virgen"),
    ("2026-10-12", "Dia de la Raza"),
    ("2026-11-02", "Todos los Santos"),
    ("2026-11-16", "Independencia de Cartagena"),
    ("2026-12-08", "Inmaculada Concepcion"),
    ("2026-12-25", "Navidad"),
)
"""Los dieciocho festivos colombianos de 2026, verificados uno por uno."""

FESTIVOS_2025: tuple[str, ...] = (
    "2025-01-01",
    "2025-01-06",
    "2025-03-24",
    "2025-04-17",
    "2025-04-18",
    "2025-05-01",
    "2025-06-02",
    "2025-06-23",
    "2025-06-30",
    "2025-07-20",
    "2025-08-07",
    "2025-08-18",
    "2025-10-13",
    "2025-11-03",
    "2025-11-17",
    "2025-12-08",
    "2025-12-25",
)
"""2025 tuvo diecisiete fechas distintas: San Pedro y Sagrado Corazon coincidieron."""


@pytest.mark.parametrize(
    ("anio", "esperado"),
    [
        (2020, "2020-04-12"),
        (2021, "2021-04-04"),
        (2022, "2022-04-17"),
        (2023, "2023-04-09"),
        (2024, "2024-03-31"),
        (2025, "2025-04-20"),
        (2026, "2026-04-05"),
        (2027, "2027-03-28"),
    ],
)
def test_domingo_de_pascua(anio: int, esperado: str) -> None:
    """De esta fecha cuelgan cinco festivos: si falla, falla todo el calendario."""
    assert pascua(anio) == date.fromisoformat(esperado)


def test_la_pascua_siempre_cae_en_domingo() -> None:
    """Invariante estructural del algoritmo, verificada en dos siglos."""
    for anio in range(1900, 2101):
        assert pascua(anio).weekday() == 6


def test_calendario_2026_completo() -> None:
    """Fecha y nombre de los dieciocho festivos del ano de referencia."""
    obtenidos = tuple((f.fecha.isoformat(), f.nombre) for f in festivos(2026))
    assert obtenidos == FESTIVOS_2026


def test_2026_tiene_dieciocho_festivos() -> None:
    """Colombia tiene dieciocho festivos al ano; es el segundo pais con mas."""
    assert len(festivos(2026)) == 18


def test_calendario_2025_y_la_coincidencia_de_junio() -> None:
    """En 2025 San Pedro y Sagrado Corazon cayeron el mismo lunes."""
    fechas = sorted({f.fecha.isoformat() for f in festivos(2025)})
    assert tuple(fechas) == FESTIVOS_2025
    coincidentes = [f.nombre for f in festivos(2025) if f.fecha == date(2025, 6, 30)]
    assert sorted(coincidentes) == ["Sagrado Corazon de Jesus", "San Pedro y San Pablo"]
    assert len(festivos(2025)) == 18


@pytest.mark.parametrize(
    ("fecha", "nombre", "original"),
    [
        ("2026-01-12", "Reyes Magos", "2026-01-06"),
        ("2026-03-23", "Dia de San Jose", "2026-03-19"),
        ("2026-08-17", "Asuncion de la Virgen", "2026-08-15"),
        ("2026-11-02", "Todos los Santos", "2026-11-01"),
        ("2026-11-16", "Independencia de Cartagena", "2026-11-11"),
    ],
)
def test_ley_emiliani_corre_al_lunes(fecha: str, nombre: str, original: str) -> None:
    """La Ley 51 de 1983 mueve el festivo al lunes siguiente para hacer puente."""
    festivo = next(f for f in festivos(2026) if f.nombre == nombre)
    assert festivo.fecha == date.fromisoformat(fecha)
    assert festivo.fecha_original == date.fromisoformat(original)
    assert festivo.trasladado
    assert festivo.fecha.weekday() == 0
    assert "Ley 51" in festivo.fundamento


def test_un_trasladable_que_ya_cae_lunes_no_se_mueve() -> None:
    """En 2025 Reyes cayo lunes: no hay traslado que hacer."""
    reyes = next(f for f in festivos(2025) if f.nombre == "Reyes Magos")
    assert reyes.fecha == date(2025, 1, 6)
    assert not reyes.trasladado


@pytest.mark.parametrize(
    ("fecha", "nombre"),
    [
        ("2026-01-01", "Ano Nuevo"),
        ("2026-05-01", "Dia del Trabajo"),
        ("2026-07-20", "Dia de la Independencia"),
        ("2026-08-07", "Batalla de Boyaca"),
        ("2026-12-08", "Inmaculada Concepcion"),
        ("2026-12-25", "Navidad"),
    ],
)
def test_los_festivos_fijos_no_se_mueven(fecha: str, nombre: str) -> None:
    """Seis festivos caen donde caen aunque sea viernes o martes."""
    festivo = next(f for f in festivos(2026) if f.nombre == nombre)
    assert festivo.fecha == date.fromisoformat(fecha)
    assert not festivo.trasladado
    assert festivo.fundamento == "festivo de fecha fija"


def test_semana_santa_se_deriva_de_la_pascua() -> None:
    """Jueves y Viernes Santo son la Pascua menos tres y menos dos dias."""
    domingo = pascua(2026)
    jueves = next(f for f in festivos(2026) if f.nombre == "Jueves Santo")
    viernes = next(f for f in festivos(2026) if f.nombre == "Viernes Santo")
    assert (domingo - jueves.fecha).days == 3
    assert (domingo - viernes.fecha).days == 2
    assert not jueves.trasladado


@pytest.mark.parametrize(
    ("nombre", "delta"),
    [("Ascension del Senor", 43), ("Corpus Christi", 64), ("Sagrado Corazon de Jesus", 71)],
)
def test_moviles_trasladados_ya_caen_en_lunes(nombre: str, delta: int) -> None:
    """Los desplazamientos de 43, 64 y 71 dias ya incorporan el traslado."""
    festivo = next(f for f in festivos(2026) if f.nombre == nombre)
    assert (festivo.fecha - pascua(2026)).days == delta
    assert festivo.fecha.weekday() == 0
    assert festivo.trasladado


@pytest.mark.parametrize(
    ("fecha", "esperado"),
    [
        ("2026-04-01", True),
        ("2026-04-02", False),
        ("2026-04-04", False),
        ("2026-04-05", False),
        ("2026-04-06", True),
        ("2026-12-25", False),
    ],
)
def test_es_dia_habil(fecha: str, esperado: bool) -> None:
    """Habil es lunes a viernes que no sea festivo."""
    assert es_dia_habil(date.fromisoformat(fecha)) is esperado


def test_el_sabado_puede_declararse_habil() -> None:
    """Algunos contratos cuentan sabado; la regla es un parametro, no un supuesto."""
    sabado = date(2026, 4, 4)
    assert not es_dia_habil(sabado)
    assert es_dia_habil(sabado, sabado_habil=True)


def test_es_festivo() -> None:
    """Consulta directa contra el indice del ano."""
    assert es_festivo(date(2026, 8, 17))
    assert not es_festivo(date(2026, 8, 15))


def test_sumar_cero_dias_habiles_no_mueve_la_fecha() -> None:
    """El caso base del contador."""
    assert sumar_dias_habiles(date(2026, 4, 2), 0) == date(2026, 4, 2)


def test_sumar_dias_habiles_negativos_falla() -> None:
    """Un termino no corre hacia atras."""
    with pytest.raises(ValueError, match="negativos"):
        sumar_dias_habiles(date(2026, 4, 2), -1)


def test_semana_santa_estira_cinco_dias_habiles_a_ocho_de_calendario() -> None:
    """Entregado el Jueves Santo de 2026, el plazo vence el viernes siguiente."""
    ventana = ventana_retracto(date(2026, 4, 2))
    assert ventana.aplica
    assert ventana.inicio == date(2026, 4, 6)
    assert ventana.vence == date(2026, 4, 10)
    assert (ventana.vence - ventana.fecha_entrega).days == 8
    assert {f.nombre for f in ventana.festivos_intermedios} == {"Jueves Santo", "Viernes Santo"}


def test_el_plazo_puede_cruzar_el_ano() -> None:
    """Entregado en Nochebuena, el retracto vence en enero del ano siguiente."""
    ventana = ventana_retracto(date(2026, 12, 24))
    assert ventana.inicio == date(2026, 12, 28)
    assert ventana.vence == date(2027, 1, 4)
    assert es_festivo(date(2027, 1, 1))


def test_entrega_en_dia_habil_normal() -> None:
    """Sin festivos de por medio, cinco habiles son siete de calendario."""
    ventana = ventana_retracto(date(2026, 9, 1))
    assert ventana.inicio == date(2026, 9, 2)
    assert ventana.vence == date(2026, 9, 8)
    assert ventana.festivos_intermedios == ()


def test_entrega_en_sabado_empieza_a_contar_el_lunes() -> None:
    """El termino arranca el primer dia habil posterior a la entrega."""
    ventana = ventana_retracto(date(2026, 9, 5))
    assert ventana.inicio == date(2026, 9, 7)
    assert ventana.vence == date(2026, 9, 11)


def test_dias_habiles_entre() -> None:
    """Cuenta el intervalo abierto por la izquierda."""
    assert dias_habiles_entre(date(2026, 4, 1), date(2026, 4, 10)) == 5
    assert dias_habiles_entre(date(2026, 4, 10), date(2026, 4, 1)) == 0
    assert dias_habiles_entre(date(2026, 4, 1), date(2026, 4, 1)) == 0


def test_vigencia_y_dias_restantes() -> None:
    """El agente necesita saber cuantos dias le quedan al cliente hoy."""
    ventana = ventana_retracto(date(2026, 9, 1))
    assert ventana.vigente(date(2026, 9, 8))
    assert not ventana.vigente(date(2026, 9, 9))
    assert ventana.dias_habiles_restantes(date(2026, 9, 8)) == 1
    assert ventana.dias_habiles_restantes(date(2026, 9, 2)) == 5
    assert ventana.dias_habiles_restantes(date(2026, 9, 30)) == 0


def test_la_venta_en_mostrador_no_tiene_retracto() -> None:
    """El Art. 47 cubre venta a distancia; el mostrador queda por fuera."""
    for modalidad in (Modalidad.MOSTRADOR, Modalidad.RECOGIDA_EN_TIENDA):
        aplica, motivo = aplica_retracto(modalidad)
        assert not aplica
        assert "punto de venta" in motivo


@pytest.mark.parametrize(
    "modalidad",
    [Modalidad.DOMICILIO, Modalidad.TIENDA_VIRTUAL, Modalidad.WHATSAPP, Modalidad.TELEFONO],
)
def test_la_venta_a_distancia_si_tiene_retracto(modalidad: Modalidad) -> None:
    """Vender por WhatsApp es venta a distancia, con todo lo que eso implica."""
    aplica, _ = aplica_retracto(modalidad)
    assert aplica


def test_un_perecedero_no_se_devuelve() -> None:
    """El paragrafo del Art. 47 excluye lo que se deteriora rapido."""
    ventana = ventana_retracto(date(2026, 9, 1), exclusiones=frozenset({"perecedero"}))
    assert not ventana.aplica
    assert ventana.vence is None
    assert ventana.inicio is None
    assert "perecedero" in ventana.motivo
    assert ventana.dias_habiles_restantes(date(2026, 9, 2)) == 0
    assert not ventana.vigente(date(2026, 9, 2))


def test_exclusion_desconocida_falla_ruidosamente() -> None:
    """Inventar una causal de exclusion es un error de programa, no una politica."""
    with pytest.raises(ValueError, match="no reconocidas"):
        aplica_retracto(Modalidad.DOMICILIO, exclusiones=frozenset({"porque si"}))


def test_las_causales_son_las_del_paragrafo() -> None:
    """La lista cerrada evita que alguien invente motivos para no devolver."""
    assert set(CATEGORIAS_SIN_RETRACTO) == {
        "perecedero",
        "personalizado",
        "servicio_iniciado",
        "uso_personal_higienico",
        "apuestas_y_loterias",
    }


def test_constantes_legales() -> None:
    """Cinco dias habiles para retractarse, treinta calendario para devolver."""
    assert DIAS_HABILES_RETRACTO == 5
    assert DIAS_PARA_DEVOLVER_DINERO == 30
    ventana = ventana_retracto(date(2026, 9, 1))
    assert ventana.dias_para_devolver_dinero == 30
    assert ventana.dias_habiles == 5


def test_ventana_con_sabado_habil_vence_antes() -> None:
    """Contar sabados acorta el plazo en dias de calendario."""
    normal = ventana_retracto(date(2026, 9, 1))
    con_sabado = ventana_retracto(date(2026, 9, 1), sabado_habil=True)
    assert con_sabado.vence is not None
    assert normal.vence is not None
    assert con_sabado.vence < normal.vence

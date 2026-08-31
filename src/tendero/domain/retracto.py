"""Derecho de retracto y calendario de dias habiles colombiano.

El articulo 47 de la Ley 1480 de 2011 le da al consumidor cinco dias habiles
contados desde la entrega para retractarse, pero solo cuando la venta se hizo
por metodos no tradicionales o a distancia: quien compra en el mostrador de la
tienda no tiene retracto. El plazo tampoco se cuenta en dias corridos, y ahi
esta la trampa que ningun calendario generico resuelve.

Colombia tiene dieciocho festivos al ano y la Ley 51 de 1983, la ley Emiliani,
traslada doce de ellos al lunes siguiente para producir un puente. Otros cinco
se derivan de la Pascua: Jueves y Viernes Santo caen donde caen, mientras que
Ascension, Corpus Christi y Sagrado Corazon ya vienen trasladados al lunes, a
43, 64 y 71 dias de la Pascua respectivamente. Con Semana Santa de por medio,
cinco dias habiles pueden ser once dias de calendario.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Final

__all__ = [
    "CATEGORIAS_SIN_RETRACTO",
    "DIAS_HABILES_RETRACTO",
    "DIAS_PARA_DEVOLVER_DINERO",
    "Festivo",
    "Modalidad",
    "VentanaRetracto",
    "aplica_retracto",
    "dias_habiles_entre",
    "es_dia_habil",
    "es_festivo",
    "festivos",
    "pascua",
    "sumar_dias_habiles",
    "ventana_retracto",
]

DIAS_HABILES_RETRACTO: Final = 5
"""Art. 47 Ley 1480 de 2011."""

DIAS_PARA_DEVOLVER_DINERO: Final = 30
"""Dias calendario que tiene el vendedor para reintegrar el dinero (Art. 47)."""

_LUNES: Final = 0
_SABADO: Final = 5

_FIJOS: Final[tuple[tuple[int, int, str], ...]] = (
    (1, 1, "Ano Nuevo"),
    (5, 1, "Dia del Trabajo"),
    (7, 20, "Dia de la Independencia"),
    (8, 7, "Batalla de Boyaca"),
    (12, 8, "Inmaculada Concepcion"),
    (12, 25, "Navidad"),
)
"""Festivos que no se trasladan: caen el dia que caen."""

_TRASLADABLES: Final[tuple[tuple[int, int, str], ...]] = (
    (1, 6, "Reyes Magos"),
    (3, 19, "Dia de San Jose"),
    (6, 29, "San Pedro y San Pablo"),
    (8, 15, "Asuncion de la Virgen"),
    (10, 12, "Dia de la Raza"),
    (11, 1, "Todos los Santos"),
    (11, 11, "Independencia de Cartagena"),
)
"""Festivos que la Ley 51 de 1983 corre al lunes siguiente."""

_DESDE_PASCUA_FIJOS: Final[tuple[tuple[int, str], ...]] = (
    (-3, "Jueves Santo"),
    (-2, "Viernes Santo"),
)

_DESDE_PASCUA_TRASLADADOS: Final[tuple[tuple[int, str], ...]] = (
    (43, "Ascension del Senor"),
    (64, "Corpus Christi"),
    (71, "Sagrado Corazon de Jesus"),
)
"""Ya incluyen el traslado: 39, 60 y 68 dias liturgicos corridos al lunes."""


class Modalidad(StrEnum):
    """Como se celebro la venta; decide si el retracto existe."""

    DOMICILIO = "domicilio"
    TIENDA_VIRTUAL = "tienda_virtual"
    WHATSAPP = "whatsapp"
    TELEFONO = "telefono"
    MOSTRADOR = "mostrador"
    RECOGIDA_EN_TIENDA = "recogida_en_tienda"


_MODALIDADES_A_DISTANCIA: Final[frozenset[Modalidad]] = frozenset(
    {
        Modalidad.DOMICILIO,
        Modalidad.TIENDA_VIRTUAL,
        Modalidad.WHATSAPP,
        Modalidad.TELEFONO,
    }
)
"""Ventas por metodos no tradicionales o a distancia (Art. 47 Ley 1480)."""

CATEGORIAS_SIN_RETRACTO: Final[frozenset[str]] = frozenset(
    {
        "perecedero",
        "personalizado",
        "servicio_iniciado",
        "uso_personal_higienico",
        "apuestas_y_loterias",
    }
)
"""Excepciones del paragrafo del Art. 47: nada de esto se puede devolver."""


@dataclass(frozen=True, slots=True)
class Festivo:
    """Un dia festivo con su origen, util para explicarle el plazo al cliente."""

    fecha: date
    nombre: str
    trasladado: bool
    fecha_original: date

    @property
    def fundamento(self) -> str:
        """Norma que explica por que ese dia no cuenta."""
        return "Ley 51 de 1983 (traslado al lunes)" if self.trasladado else "festivo de fecha fija"


def pascua(anio: int) -> date:
    """Domingo de Pascua por el algoritmo gregoriano anonimo (Meeus).

    Todo el calendario movil colombiano cuelga de esta fecha, asi que se calcula
    en vez de tabularse: una tabla se queda corta el ano que nadie la actualiza.
    """
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ele = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ele) // 451
    mes, dia = divmod(h + ele - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _al_lunes_siguiente(fecha: date) -> date:
    """Corre la fecha al lunes siguiente; si ya es lunes, la deja igual."""
    return fecha + timedelta(days=(_LUNES - fecha.weekday()) % 7)


@lru_cache(maxsize=256)
def festivos(anio: int) -> tuple[Festivo, ...]:
    """Los dieciocho festivos colombianos del ano, ordenados por fecha."""
    domingo_pascua = pascua(anio)
    encontrados: list[Festivo] = [
        Festivo(
            fecha=date(anio, mes, dia),
            nombre=nombre,
            trasladado=False,
            fecha_original=date(anio, mes, dia),
        )
        for mes, dia, nombre in _FIJOS
    ]
    for mes, dia, nombre in _TRASLADABLES:
        original = date(anio, mes, dia)
        movido = _al_lunes_siguiente(original)
        encontrados.append(
            Festivo(
                fecha=movido,
                nombre=nombre,
                trasladado=movido != original,
                fecha_original=original,
            )
        )
    for delta, nombre in _DESDE_PASCUA_FIJOS:
        fecha = domingo_pascua + timedelta(days=delta)
        encontrados.append(
            Festivo(fecha=fecha, nombre=nombre, trasladado=False, fecha_original=fecha)
        )
    for delta, nombre in _DESDE_PASCUA_TRASLADADOS:
        fecha = domingo_pascua + timedelta(days=delta)
        encontrados.append(
            Festivo(
                fecha=fecha,
                nombre=nombre,
                trasladado=True,
                fecha_original=domingo_pascua + timedelta(days=delta - 4),
            )
        )
    return tuple(sorted(encontrados, key=lambda f: (f.fecha, f.nombre)))


@lru_cache(maxsize=256)
def _indice_festivos(anio: int) -> frozenset[date]:
    """Conjunto de fechas festivas del ano, para consulta en tiempo constante."""
    return frozenset(f.fecha for f in festivos(anio))


def es_festivo(dia: date) -> bool:
    """Cierto si la fecha es festivo nacional colombiano."""
    return dia in _indice_festivos(dia.year)


def es_dia_habil(dia: date, *, sabado_habil: bool = False) -> bool:
    """Cierto si el dia cuenta para un termino en dias habiles.

    Por defecto el sabado no cuenta: los terminos del consumidor se surten ante
    la Superintendencia de Industria y Comercio, que se rige por el calendario
    de dias habiles administrativos de lunes a viernes (Art. 62 Ley 4 de 1913 y
    Art. 118 del Codigo General del Proceso).
    """
    tope = _SABADO + 1 if sabado_habil else _SABADO
    return dia.weekday() < tope and not es_festivo(dia)


def sumar_dias_habiles(inicio: date, dias: int, *, sabado_habil: bool = False) -> date:
    """Devuelve la fecha del n-esimo dia habil posterior a ``inicio``.

    El dia de la entrega no se cuenta: el termino corre desde el dia habil
    siguiente, que es como la SIC computa los plazos del consumidor.
    """
    if dias < 0:
        msg = "no se pueden sumar dias habiles negativos"
        raise ValueError(msg)
    cursor = inicio
    restantes = dias
    while restantes > 0:
        cursor += timedelta(days=1)
        if es_dia_habil(cursor, sabado_habil=sabado_habil):
            restantes -= 1
    return cursor


def dias_habiles_entre(inicio: date, fin: date, *, sabado_habil: bool = False) -> int:
    """Cuenta dias habiles en el intervalo abierto por la izquierda."""
    if fin <= inicio:
        return 0
    total = 0
    cursor = inicio
    while cursor < fin:
        cursor += timedelta(days=1)
        if es_dia_habil(cursor, sabado_habil=sabado_habil):
            total += 1
    return total


def aplica_retracto(
    modalidad: Modalidad,
    *,
    exclusiones: frozenset[str] | None = None,
) -> tuple[bool, str]:
    """Decide si la venta admite retracto y explica el motivo.

    El motivo es parte del resultado porque la respuesta util para el cliente
    no es que no, sino por que no: una arepa no se devuelve porque es
    perecedera, no porque la tienda no quiera.
    """
    presentes = exclusiones or frozenset()
    desconocidas = presentes - CATEGORIAS_SIN_RETRACTO
    if desconocidas:
        msg = f"exclusiones de retracto no reconocidas: {sorted(desconocidas)}"
        raise ValueError(msg)
    if modalidad not in _MODALIDADES_A_DISTANCIA:
        return False, (
            "el retracto del Art. 47 de la Ley 1480 de 2011 solo cubre ventas por "
            "metodos no tradicionales o a distancia; esta se celebro en el punto de venta"
        )
    if presentes:
        motivos = ", ".join(sorted(presentes))
        return False, (f"el paragrafo del Art. 47 excluye del retracto: {motivos}")
    return True, "venta a distancia sin bienes exceptuados: el retracto aplica"


@dataclass(frozen=True, slots=True)
class VentanaRetracto:
    """Plazo de retracto ya resuelto contra el calendario real."""

    aplica: bool
    motivo: str
    fecha_entrega: date
    inicio: date | None
    vence: date | None
    dias_habiles: int
    festivos_intermedios: tuple[Festivo, ...]
    dias_para_devolver_dinero: int = DIAS_PARA_DEVOLVER_DINERO

    def vigente(self, hoy: date) -> bool:
        """Cierto si en ``hoy`` el cliente todavia puede retractarse."""
        return self.aplica and self.vence is not None and hoy <= self.vence

    def dias_habiles_restantes(self, hoy: date, *, sabado_habil: bool = False) -> int:
        """Cuantos dias habiles le quedan al cliente contados desde ``hoy``."""
        if not self.aplica or self.vence is None or hoy > self.vence:
            return 0
        return dias_habiles_entre(hoy, self.vence, sabado_habil=sabado_habil) + 1


def ventana_retracto(
    fecha_entrega: date,
    *,
    modalidad: Modalidad = Modalidad.DOMICILIO,
    exclusiones: frozenset[str] | None = None,
    sabado_habil: bool = False,
) -> VentanaRetracto:
    """Calcula el plazo de retracto de una entrega concreta."""
    aplica, motivo = aplica_retracto(modalidad, exclusiones=exclusiones)
    if not aplica:
        return VentanaRetracto(
            aplica=False,
            motivo=motivo,
            fecha_entrega=fecha_entrega,
            inicio=None,
            vence=None,
            dias_habiles=0,
            festivos_intermedios=(),
        )
    inicio = sumar_dias_habiles(fecha_entrega, 1, sabado_habil=sabado_habil)
    vence = sumar_dias_habiles(fecha_entrega, DIAS_HABILES_RETRACTO, sabado_habil=sabado_habil)
    intermedios = tuple(
        festivo
        for anio in range(fecha_entrega.year, vence.year + 1)
        for festivo in festivos(anio)
        if fecha_entrega <= festivo.fecha <= vence
    )
    return VentanaRetracto(
        aplica=True,
        motivo=motivo,
        fecha_entrega=fecha_entrega,
        inicio=inicio,
        vence=vence,
        dias_habiles=DIAS_HABILES_RETRACTO,
        festivos_intermedios=intermedios,
    )

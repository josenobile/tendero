"""Identidades tributarias colombianas para la factura electronica DIAN.

Toda venta facturada electronicamente en Colombia exige identificar al
adquiriente con un tipo de documento del listado del anexo tecnico de la DIAN y,
cuando es NIT, con su digito de verificacion. Un DV mal calculado hace que la
DIAN rechace el documento, asi que el algoritmo vive en el dominio y no en la
capa de red: es la regla que mas veces rompe una integracion nueva.

Vigencia: el PEP (Permiso Especial de Permanencia) fue sustituido en la practica
por el PPT (Permiso por Proteccion Temporal, Decreto 216 de 2021) para poblacion
migrante venezolana. Se conserva porque sigue apareciendo en bases de clientes
anteriores a 2021 y la DIAN mantiene su codigo 47.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from tendero.domain.errores import DocumentoInvalidoError

__all__ = [
    "DV_NIT_PESOS",
    "REGLAS",
    "Documento",
    "ReglaDocumento",
    "TipoDocumento",
    "calcular_dv_nit",
    "es_valido",
    "formatear_nit",
    "normalizar",
    "separar_dv",
    "validar",
    "verificar_dv_nit",
]

_SERIE_OFICIAL_DV: Final = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)
"""Serie completa de primos que la DIAN aplica de derecha a izquierda."""

DV_NIT_PESOS: Final = _SERIE_OFICIAL_DV[-9:]
"""(41, 37, 29, 23, 19, 17, 13, 7, 3): la cola usada por un NIT de 9 digitos."""

_MODULO_DV: Final = 11
_RESIDUOS_CERO: Final = frozenset({0, 1})

_SEPARADORES: Final = re.compile(r"[\s.,\-]")
_SOLO_DIGITOS: Final = re.compile(r"\A\d+\Z")
_ALFANUMERICO: Final = re.compile(r"\A[A-Z0-9]+\Z")
_NIT_CON_DV: Final = re.compile(r"\A\s*(?P<base>[\d.\s,]+?)\s*-\s*(?P<dv>\d)\s*\Z")

_PREFIJOS_PERSONA_JURIDICA: Final = frozenset({"8", "9"})
"""La DIAN asigna NIT que empiezan en 8 o 9 a personas juridicas.

Una persona natural usa como NIT su propia cedula, que empieza en otro digito.
La distincion decide si la factura lleva razon social o nombres y apellidos.
"""


class TipoDocumento(StrEnum):
    """Tipos aceptados como identificacion del adquiriente."""

    CC = "CC"
    CE = "CE"
    NIT = "NIT"
    PA = "PA"
    TI = "TI"
    PEP = "PEP"


@dataclass(frozen=True, slots=True)
class ReglaDocumento:
    """Restricciones de forma de un tipo de documento."""

    tipo: TipoDocumento
    codigo_dian: str
    nombre: str
    largo_minimo: int
    largo_maximo: int
    solo_digitos: bool
    requiere_dv: bool


REGLAS: Final[Mapping[TipoDocumento, ReglaDocumento]] = MappingProxyType(
    {
        TipoDocumento.CC: ReglaDocumento(
            tipo=TipoDocumento.CC,
            codigo_dian="13",
            nombre="Cedula de ciudadania",
            largo_minimo=4,
            largo_maximo=10,
            solo_digitos=True,
            requiere_dv=False,
        ),
        TipoDocumento.CE: ReglaDocumento(
            tipo=TipoDocumento.CE,
            codigo_dian="22",
            nombre="Cedula de extranjeria",
            largo_minimo=5,
            largo_maximo=8,
            solo_digitos=True,
            requiere_dv=False,
        ),
        TipoDocumento.NIT: ReglaDocumento(
            tipo=TipoDocumento.NIT,
            codigo_dian="31",
            nombre="NIT",
            largo_minimo=5,
            largo_maximo=15,
            solo_digitos=True,
            requiere_dv=True,
        ),
        TipoDocumento.PA: ReglaDocumento(
            tipo=TipoDocumento.PA,
            codigo_dian="41",
            nombre="Pasaporte",
            largo_minimo=5,
            largo_maximo=16,
            solo_digitos=False,
            requiere_dv=False,
        ),
        TipoDocumento.TI: ReglaDocumento(
            tipo=TipoDocumento.TI,
            codigo_dian="12",
            nombre="Tarjeta de identidad",
            largo_minimo=10,
            largo_maximo=11,
            solo_digitos=True,
            requiere_dv=False,
        ),
        TipoDocumento.PEP: ReglaDocumento(
            tipo=TipoDocumento.PEP,
            codigo_dian="47",
            nombre="Permiso Especial de Permanencia",
            largo_minimo=15,
            largo_maximo=15,
            solo_digitos=True,
            requiere_dv=False,
        ),
    }
)


def normalizar(valor: str) -> str:
    """Quita puntos, comas, guiones y espacios y pasa a mayusculas."""
    return _SEPARADORES.sub("", valor.strip().upper())


def separar_dv(valor: str) -> tuple[str, int | None]:
    """Parte ``890.903.938-8`` en base normalizada y digito de verificacion.

    Hay que separar antes de normalizar: si se quitan los guiones primero,
    ``8909039388`` es indistinguible de un NIT de diez digitos sin DV.
    """
    coincidencia = _NIT_CON_DV.match(valor)
    if coincidencia is None:
        return normalizar(valor), None
    return normalizar(coincidencia.group("base")), int(coincidencia.group("dv"))


def calcular_dv_nit(base: str) -> int:
    """Calcula el digito de verificacion DIAN de un NIT sin DV.

    Se multiplica cada digito, de derecha a izquierda, por la serie de primos
    oficial; la suma se toma modulo once y el residuo cero o uno produce un DV
    cero, cualquier otro produce once menos el residuo.
    """
    limpio = normalizar(base)
    if not _SOLO_DIGITOS.match(limpio):
        msg = f"el NIT solo admite digitos, se recibio {base!r}"
        raise DocumentoInvalidoError(msg)
    if len(limpio) > len(_SERIE_OFICIAL_DV):
        msg = f"NIT de {len(limpio)} digitos excede el maximo de la serie DIAN"
        raise DocumentoInvalidoError(msg)
    total = sum(
        int(digito) * peso
        for digito, peso in zip(reversed(limpio), reversed(_SERIE_OFICIAL_DV), strict=False)
    )
    residuo = total % _MODULO_DV
    if residuo in _RESIDUOS_CERO:
        return 0
    return _MODULO_DV - residuo


def verificar_dv_nit(base: str, dv: int) -> bool:
    """Indica si ``dv`` es el digito de verificacion que corresponde a ``base``."""
    return calcular_dv_nit(base) == dv


def formatear_nit(base: str, dv: int) -> str:
    """Devuelve el NIT en la presentacion de la camara de comercio."""
    limpio = normalizar(base)
    return f"{int(limpio):,}".replace(",", ".") + f"-{dv}"


@dataclass(frozen=True, slots=True)
class Documento:
    """Identidad tributaria validada de un adquiriente."""

    tipo: TipoDocumento
    numero: str
    dv: int | None = None

    def __post_init__(self) -> None:
        """Impide construir un documento que la DIAN rechazaria."""
        regla = REGLAS[self.tipo]
        numero = self.numero
        if numero != normalizar(numero):
            msg = f"el numero debe venir normalizado, se recibio {numero!r}"
            raise DocumentoInvalidoError(msg)
        if not numero:
            msg = f"{regla.nombre}: el numero no puede ir vacio"
            raise DocumentoInvalidoError(msg)
        patron = _SOLO_DIGITOS if regla.solo_digitos else _ALFANUMERICO
        if not patron.match(numero):
            forma = "solo digitos" if regla.solo_digitos else "letras y digitos"
            msg = f"{regla.nombre}: admite {forma}, se recibio {numero!r}"
            raise DocumentoInvalidoError(msg)
        if not regla.largo_minimo <= len(numero) <= regla.largo_maximo:
            msg = (
                f"{regla.nombre}: longitud {len(numero)} fuera del rango "
                f"{regla.largo_minimo}-{regla.largo_maximo}"
            )
            raise DocumentoInvalidoError(msg)
        if regla.requiere_dv:
            if self.dv is None:
                msg = f"{regla.nombre}: falta el digito de verificacion"
                raise DocumentoInvalidoError(msg)
            esperado = calcular_dv_nit(numero)
            if esperado != self.dv:
                msg = (
                    f"digito de verificacion incorrecto para el NIT {numero}: "
                    f"se recibio {self.dv}, corresponde {esperado}"
                )
                raise DocumentoInvalidoError(msg)
        elif self.dv is not None:
            msg = f"{regla.nombre}: no lleva digito de verificacion"
            raise DocumentoInvalidoError(msg)

    @classmethod
    def parse(cls, tipo: TipoDocumento | str, valor: str) -> Documento:
        """Construye un documento desde el texto tal como lo escribe una persona.

        Acepta ``890.903.938-8``, ``890903938-8`` y ``890903938``: en el ultimo
        caso calcula el DV en vez de rechazar, porque el cliente de una tienda
        casi nunca lo dicta.
        """
        try:
            tipo_doc = TipoDocumento(str(tipo).strip().upper())
        except ValueError as exc:
            admitidos = ", ".join(sorted(t.value for t in TipoDocumento))
            msg = f"tipo de documento desconocido {tipo!r}; admitidos: {admitidos}"
            raise DocumentoInvalidoError(msg) from exc
        regla = REGLAS[tipo_doc]
        if regla.requiere_dv:
            base, dv = separar_dv(valor)
            if dv is None:
                dv = calcular_dv_nit(base)
            return cls(tipo=tipo_doc, numero=base, dv=dv)
        return cls(tipo=tipo_doc, numero=normalizar(valor))

    @property
    def regla(self) -> ReglaDocumento:
        """Metadatos DIAN del tipo de este documento."""
        return REGLAS[self.tipo]

    @property
    def codigo_dian(self) -> str:
        """Codigo numerico del tipo en el anexo tecnico de facturacion."""
        return self.regla.codigo_dian

    @property
    def es_persona_juridica(self) -> bool:
        """Cierto si el NIT fue asignado a una empresa y no a una persona."""
        return self.tipo is TipoDocumento.NIT and self.numero[0] in _PREFIJOS_PERSONA_JURIDICA

    @property
    def formateado(self) -> str:
        """Presentacion legible para mostrarle el dato al cliente."""
        if self.tipo is TipoDocumento.NIT and self.dv is not None:
            return formatear_nit(self.numero, self.dv)
        if self.regla.solo_digitos:
            return f"{int(self.numero):,}".replace(",", ".")
        return self.numero

    def __str__(self) -> str:
        """Representa el documento como lo pide un formulario DIAN."""
        return f"{self.tipo.value} {self.formateado}"


def validar(tipo: TipoDocumento | str, valor: str) -> Documento:
    """Valida y normaliza; lanza ``DocumentoInvalidoError`` si no cumple."""
    return Documento.parse(tipo, valor)


def es_valido(tipo: TipoDocumento | str, valor: str) -> bool:
    """Version booleana de :func:`validar`, para ramas de decision."""
    try:
        validar(tipo, valor)
    except DocumentoInvalidoError:
        return False
    return True

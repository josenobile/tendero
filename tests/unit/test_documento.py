"""Pruebas de identidad tributaria, con el digito de verificacion DIAN al frente."""

from __future__ import annotations

import pytest

from tendero.domain.documento import (
    DV_NIT_PESOS,
    Documento,
    TipoDocumento,
    calcular_dv_nit,
    es_valido,
    formatear_nit,
    normalizar,
    separar_dv,
    validar,
    verificar_dv_nit,
)
from tendero.domain.errores import DocumentoInvalidoError

NITS_REALES: tuple[tuple[str, int, str], ...] = (
    ("890903938", 8, "Bancolombia"),
    ("860002964", 4, "Banco de Bogota"),
    ("800197268", 4, "DIAN"),
    ("890900608", 9, "Almacenes Exito"),
    ("860005224", 6, "Bavaria"),
    ("860512330", 3, "Servientrega"),
    ("830029788", 2, "Inter Rapidisimo"),
    ("860034313", 7, "entidad verificada"),
)
"""NITs colombianos reales; el digito es el que aparece en el RUT de cada uno."""


def _dv_referencia(base: str) -> int:
    """Implementacion independiente del DV, escrita desde el enunciado legal.

    Se formula distinto a proposito (lista literal de pesos, recorrido explicito)
    para que un error de transcripcion en el modulo no se repita aqui.
    """
    pesos = [41, 37, 29, 23, 19, 17, 13, 7, 3]
    digitos = [int(c) for c in base]
    total = 0
    for indice, digito in enumerate(reversed(digitos)):
        total += digito * pesos[len(pesos) - 1 - indice]
    residuo = total % 11
    if residuo in (0, 1):
        return 0
    return 11 - residuo


def test_los_pesos_publicados_son_los_del_enunciado_dian() -> None:
    """La cola de nueve pesos es la que se aplica a un NIT de nueve digitos."""
    assert DV_NIT_PESOS == (41, 37, 29, 23, 19, 17, 13, 7, 3)


@pytest.mark.parametrize(("base", "dv", "entidad"), NITS_REALES)
def test_dv_de_nits_colombianos_reales(base: str, dv: int, entidad: str) -> None:
    """El algoritmo reproduce el digito impreso en el RUT de empresas reales."""
    assert calcular_dv_nit(base) == dv, entidad
    assert verificar_dv_nit(base, dv)


@pytest.mark.parametrize(("base", "dv", "entidad"), NITS_REALES)
def test_dv_coincide_con_implementacion_independiente(base: str, dv: int, entidad: str) -> None:
    """Dos formulaciones distintas del mismo algoritmo tienen que coincidir."""
    assert _dv_referencia(base) == dv, entidad


def test_dv_coincide_en_un_barrido_amplio() -> None:
    """Barrido de NITs sinteticos contra la implementacion de referencia."""
    for numero in range(800_000_000, 800_002_000):
        base = str(numero)
        assert calcular_dv_nit(base) == _dv_referencia(base)


@pytest.mark.parametrize("base", ["890903937", "890903838", "899999068"])
def test_residuo_cero_o_uno_produce_digito_cero(base: str) -> None:
    """La regla del residuo es la parte que casi todas las integraciones fallan."""
    total = sum(int(d) * p for d, p in zip(base, DV_NIT_PESOS, strict=True))
    assert total % 11 in (0, 1)
    assert calcular_dv_nit(base) == 0


def test_dv_siempre_esta_entre_cero_y_nueve() -> None:
    """El digito de verificacion nunca puede ser diez."""
    for numero in range(900_000_000, 900_001_000):
        assert 0 <= calcular_dv_nit(str(numero)) <= 9


def test_dv_ignora_puntos_y_espacios() -> None:
    """El cliente dicta el NIT con puntos y el sistema no puede tropezar."""
    assert calcular_dv_nit("890.903.938") == 8
    assert calcular_dv_nit(" 890 903 938 ") == 8


def test_dv_rechaza_letras() -> None:
    """Un NIT con letras no es un NIT."""
    with pytest.raises(DocumentoInvalidoError, match="solo admite digitos"):
        calcular_dv_nit("89090393A")


def test_dv_rechaza_nit_mas_largo_que_la_serie() -> None:
    """La serie oficial de pesos cubre quince digitos, no mas."""
    with pytest.raises(DocumentoInvalidoError, match="excede el maximo"):
        calcular_dv_nit("1" * 16)


@pytest.mark.parametrize(
    ("crudo", "base", "dv"),
    [
        ("890.903.938-8", "890903938", 8),
        ("890903938-8", "890903938", 8),
        ("890903938", "890903938", None),
        (" 860 512 330 - 3 ", "860512330", 3),
    ],
)
def test_separar_dv(crudo: str, base: str, dv: int | None) -> None:
    """El guion se lee antes de normalizar o el DV se pierde entre los digitos."""
    assert separar_dv(crudo) == (base, dv)


def test_normalizar_sube_a_mayusculas() -> None:
    """Los pasaportes se comparan en mayusculas."""
    assert normalizar(" ab-123.456 ") == "AB123456"


def test_formatear_nit() -> None:
    """La presentacion es la de la camara de comercio."""
    assert formatear_nit("890903938", 8) == "890.903.938-8"


def test_parse_calcula_el_dv_cuando_el_cliente_no_lo_dicta() -> None:
    """Casi nadie recita su digito de verificacion; se calcula en vez de fallar."""
    documento = Documento.parse(TipoDocumento.NIT, "890903938")
    assert documento.dv == 8
    assert documento.formateado == "890.903.938-8"


def test_parse_rechaza_dv_equivocado_y_dice_cual_era() -> None:
    """El mensaje trae el digito correcto para que el agente pueda corregirlo."""
    with pytest.raises(DocumentoInvalidoError, match="corresponde 8"):
        Documento.parse(TipoDocumento.NIT, "890903938-1")


def test_nit_de_persona_juridica_frente_a_natural() -> None:
    """Los NIT que empiezan en 8 o 9 son de empresa; el resto es una cedula."""
    empresa = Documento.parse("NIT", "890.903.938-8")
    persona = Documento.parse("NIT", "43256789-8")
    assert empresa.es_persona_juridica
    assert not persona.es_persona_juridica


@pytest.mark.parametrize(
    ("tipo", "valor", "codigo"),
    [
        ("CC", "1.017.234.567", "13"),
        ("CC", "8123", "13"),
        ("CE", "123456", "22"),
        ("TI", "1012345678", "12"),
        ("PA", "ab-123456", "41"),
        ("PEP", "123456789012345", "47"),
        ("NIT", "890903938-8", "31"),
    ],
)
def test_documentos_validos_por_tipo(tipo: str, valor: str, codigo: str) -> None:
    """Cada tipo lleva el codigo del anexo tecnico de facturacion electronica."""
    documento = validar(tipo, valor)
    assert documento.codigo_dian == codigo
    assert es_valido(tipo, valor)


@pytest.mark.parametrize(
    ("tipo", "valor"),
    [
        ("CC", "123"),
        ("CC", "12345678901"),
        ("CC", "10A2345"),
        ("CE", "1234"),
        ("TI", "123456789"),
        ("PEP", "12345678901234"),
        ("PA", "AB!123"),
        ("PA", "AB12"),
        ("NIT", "1234"),
    ],
)
def test_documentos_invalidos_por_tipo(tipo: str, valor: str) -> None:
    """Longitud y alfabeto se validan por tipo, no en general."""
    assert not es_valido(tipo, valor)
    with pytest.raises(DocumentoInvalidoError):
        validar(tipo, valor)


def test_tipo_desconocido_lista_los_admitidos() -> None:
    """Si el agente inventa un tipo, la respuesta le dice cuales existen."""
    with pytest.raises(DocumentoInvalidoError, match="admitidos: CC, CE, NIT, PA, PEP, TI"):
        validar("DNI", "12345678")


def test_documento_no_admite_numero_sin_normalizar() -> None:
    """Construir el dataclass a mano tampoco puede saltarse la normalizacion."""
    with pytest.raises(DocumentoInvalidoError, match="normalizado"):
        Documento(tipo=TipoDocumento.CC, numero="1.017.234.567")


def test_documento_vacio() -> None:
    """Un numero vacio no identifica a nadie."""
    with pytest.raises(DocumentoInvalidoError, match="no puede ir vacio"):
        Documento(tipo=TipoDocumento.CC, numero="")


def test_nit_sin_dv_no_se_puede_construir_a_mano() -> None:
    """El NIT sin digito no sirve para facturar."""
    with pytest.raises(DocumentoInvalidoError, match="falta el digito"):
        Documento(tipo=TipoDocumento.NIT, numero="890903938")


def test_cedula_no_lleva_dv() -> None:
    """Solo el NIT tiene digito de verificacion."""
    with pytest.raises(DocumentoInvalidoError, match="no lleva digito"):
        Documento(tipo=TipoDocumento.CC, numero="1017234567", dv=3)


def test_representacion_textual() -> None:
    """La cadena es la que se imprime en la factura."""
    assert str(validar("NIT", "890903938-8")) == "NIT 890.903.938-8"
    assert str(validar("CC", "1017234567")) == "CC 1.017.234.567"
    assert str(validar("PA", "AB123456")) == "PA AB123456"


def test_documento_es_inmutable_y_hasheable() -> None:
    """Se usa como clave de cache y no puede mutar despues de validado."""
    documento = validar("CC", "1017234567")
    assert {documento} == {validar("CC", "1.017.234.567")}
    with pytest.raises(AttributeError):
        documento.numero = "otro"  # type: ignore[misc]

"""La capa HTTP, probada contra el cliente de pruebas de FastAPI, sin red.

Lo que se verifica aqui no es la regla colombiana --de eso se encargan las
pruebas del dominio-- sino que la traduccion no la deforme: que el destino
llegue al liquidador, que un error de negocio salga como 422 con su motivo
redactado y no como 500, y que cada ruta ``/api/<nombre>`` exista con el mismo
nombre que la herramienta WebMCP que la vitrina registra.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tendero import api
from tendero.api import ARCHIVO_INDEX, app
from tendero.domain import catalogo, envio, pago, retracto

HERRAMIENTAS = (
    "buscar_productos",
    "calcular_total_con_iva",
    "consultar_derecho_retracto",
    "cotizar_envio",
    "metodos_de_pago",
    "validar_documento_dian",
)
"""Las seis capacidades, con el nombre exacto que usan la ruta y la herramienta."""

SOLO_PAGINA = (
    "agregar_al_carrito",
    "quitar_del_carrito",
)
"""Las dos herramientas que solo registra la pagina: envuelven el carrito del
navegador, que no vive en el backend, asi que no tienen ruta."""

ASEO = [{"sku": "ASE-JAB-X3", "cantidad": 2}]
MERCADO = [
    {"sku": "FRU-PLA-LB", "cantidad": 2},
    {"sku": "LAC-LEC-1L", "cantidad": 3},
    {"sku": "CAF-TOS-250", "cantidad": 1},
    {"sku": "ASE-JAB-X3", "cantidad": 1},
    {"sku": "PRE-ALM-COR", "cantidad": 1},
]


@pytest.fixture(scope="module")
def cliente() -> Iterator[TestClient]:
    """Un solo cliente para todo el modulo: la app no tiene estado mutable."""
    with TestClient(app) as instancia:
        yield instancia


# --------------------------------------------------------------------------- #
# servicio
# --------------------------------------------------------------------------- #


def test_health_reporta_el_tamano_de_los_maestros(cliente: TestClient) -> None:
    """El latido sirve para verificar que el proceso cargo el dominio completo."""
    datos = cliente.get("/health").json()
    assert datos["estado"] == "ok"
    assert datos["productos"] == len(catalogo.CATALOGO)
    assert datos["ciudades"] == len(envio.CIUDADES)
    assert datos["sin_contraentrega"] == 7


def test_la_raiz_sirve_la_vitrina(cliente: TestClient) -> None:
    """La pagina que registra las herramientas se sirve desde la raiz."""
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "document.modelContext" in respuesta.text


def test_el_contexto_trae_todo_lo_que_la_vitrina_necesita(cliente: TestClient) -> None:
    """Una sola peticion tiene que bastar para pintar la pagina entera."""
    datos = cliente.get("/api/contexto").json()
    assert datos["comercio"]["documento"] == "NIT 900.123.456-8"
    assert len(datos["ciudades"]) == len(envio.CIUDADES)
    assert len(datos["tipos_documento"]) == 6
    assert datos["modalidades_venta"] == [m.value for m in retracto.Modalidad]
    assert datos["metodos_pago"] == [m.value for m in pago.MetodoPago]
    assert "476" in datos["nota_flete"]


@pytest.mark.parametrize("nombre", HERRAMIENTAS)
def test_cada_herramienta_tiene_su_ruta_homonima(cliente: TestClient, nombre: str) -> None:
    """La correspondencia ruta/herramienta es parte del contrato del proyecto."""
    esquema = cliente.get("/openapi.json").json()
    assert f"/api/{nombre}" in esquema["paths"]


# --------------------------------------------------------------------------- #
# buscar_productos
# --------------------------------------------------------------------------- #


def test_buscar_sin_consulta_devuelve_el_catalogo(cliente: TestClient) -> None:
    """Un agente que no sabe que pedir tiene que poder ver todo."""
    datos = cliente.post("/api/buscar_productos", json={}).json()
    assert datos["total"] == len(catalogo.CATALOGO)
    assert len(datos["productos"]) == 24


def test_buscar_tolera_la_falta_de_tildes(cliente: TestClient) -> None:
    """La gente escribe 'cafe', no 'café'."""
    datos = cliente.post("/api/buscar_productos", json={"consulta": "cafe"}).json()
    assert {p["sku"] for p in datos["productos"]} == {"CAF-TOS-250", "CAF-CHO-500"}


def test_buscar_por_categoria_ignora_la_consulta(cliente: TestClient) -> None:
    """La categoria es un filtro exacto y manda sobre el texto libre."""
    datos = cliente.post(
        "/api/buscar_productos", json={"categoria": "aseo", "consulta": "cafe"}
    ).json()
    assert {p["categoria"] for p in datos["productos"]} == {"aseo"}


def test_el_limite_se_acota_en_vez_de_rechazarse(cliente: TestClient) -> None:
    """Un agente que pide de mas quiere resultados, no un error de validacion."""
    datos = cliente.post("/api/buscar_productos", json={"limite": 5000}).json()
    assert len(datos["productos"]) == len(catalogo.CATALOGO)
    assert cliente.post("/api/buscar_productos", json={"limite": 0}).json()["productos"]


def test_el_precio_de_gondola_baja_en_un_destino_sin_iva(cliente: TestClient) -> None:
    """El mismo cafe cuesta menos en Leticia: Art. 270 de la Ley 223 de 1995."""
    medellin = cliente.post(
        "/api/buscar_productos", json={"consulta": "cafe tostado", "destino": "05001"}
    ).json()
    leticia = cliente.post(
        "/api/buscar_productos", json={"consulta": "cafe tostado", "destino": "Leticia"}
    ).json()
    assert medellin["productos"][0]["precio_publico"]["centavos"] == 14_900_00
    assert leticia["productos"][0]["precio_publico"]["centavos"] == 14_200_00
    assert "regimen especial" in leticia["nota"]


def test_el_producto_viaja_con_su_fundamento_legal(cliente: TestClient) -> None:
    """El agente tiene que poder citar la norma, no solo repetir un numero."""
    datos = cliente.post("/api/buscar_productos", json={"consulta": "leche"}).json()
    leche = datos["productos"][0]
    assert leche["regimen"] == "exento"
    assert leche["tarifa"] == "0,00 %"
    assert "477" in leche["fundamento"]
    assert "descontables" in leche["explicacion"]


# --------------------------------------------------------------------------- #
# cotizar_envio
# --------------------------------------------------------------------------- #


def test_cotizar_ordena_por_costo_y_marca_la_mejor(cliente: TestClient) -> None:
    """La primera opcion es la mas barata y es la que se devuelve como mejor."""
    datos = cliente.post("/api/cotizar_envio", json={"destino": "Pasto", "items": ASEO}).json()
    totales = [o["total"]["centavos"] for o in datos["opciones"]]
    assert totales == sorted(totales)
    assert datos["mejor"]["codigo_transportadora"] == datos["opciones"][0]["codigo_transportadora"]


def test_un_destino_sin_carretera_no_admite_contraentrega(cliente: TestClient) -> None:
    """Es la asimetria que el proyecto existe para exponer."""
    datos = cliente.post("/api/cotizar_envio", json={"destino": "91001", "items": ASEO}).json()
    assert datos["contraentrega_disponible"] is False
    assert "agente local" in datos["contraentrega_motivo"]
    assert datos["tope_contraentrega"]["centavos"] == 0
    assert any("carga aerea" in nota for nota in datos["opciones"][0]["notas"])


def test_un_carrito_de_solo_servicios_no_se_despacha(cliente: TestClient) -> None:
    """El almuerzo corrientazo se factura, pero no lo recoge una transportadora."""
    datos = cliente.post(
        "/api/cotizar_envio", json={"destino": "05001", "items": [{"sku": "PRE-ALM-COR"}]}
    ).json()
    assert datos["despachable"] is False
    assert datos["opciones"] == []
    assert "nada fisico que despachar" in datos["nota"]


def test_sin_declarar_valor_no_hay_comision_de_manejo(cliente: TestClient) -> None:
    """Declarar el valor es opcional y cuesta: la respuesta lo tiene que mostrar.

    Se cotiza a Pasto y no al Valle de Aburra a proposito: la mensajeria local
    no cobra manejo, asi que en el area metropolitana declarar el valor sale
    gratis y la prueba no distinguiria nada.
    """
    con = cliente.post(
        "/api/cotizar_envio", json={"destino": "Pasto", "items": ASEO, "declarar_valor": True}
    ).json()
    sin = cliente.post(
        "/api/cotizar_envio", json={"destino": "Pasto", "items": ASEO, "declarar_valor": False}
    ).json()
    assert con["valor_declarado"]["centavos"] > 0
    assert sin["valor_declarado"]["centavos"] == 0
    assert sin["mejor"]["manejo"]["centavos"] == 0
    assert con["mejor"]["total"]["centavos"] > sin["mejor"]["total"]["centavos"]


def test_contraentrega_filtra_las_transportadoras_que_no_recaudan(cliente: TestClient) -> None:
    """Coordinadora no recauda, asi que no puede aparecer en un contra entrega."""
    datos = cliente.post(
        "/api/cotizar_envio",
        json={"destino": "Bucaramanga", "items": ASEO, "contraentrega": True},
    ).json()
    assert "coordinadora" not in {o["codigo_transportadora"] for o in datos["opciones"]}
    assert all(o["recaudo"]["centavos"] > 0 for o in datos["opciones"])


def test_una_ciudad_desconocida_es_422_con_sugerencias(cliente: TestClient) -> None:
    """Un destino mal escrito es una peticion corregible, no una falla del servidor."""
    respuesta = cliente.post("/api/cotizar_envio", json={"destino": "Narnia", "items": ASEO})
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "CiudadDesconocidaError"
    assert "Narnia" in cuerpo["error"]


def test_un_sku_inexistente_es_422(cliente: TestClient) -> None:
    """Lo mismo con una referencia inventada por el agente."""
    respuesta = cliente.post(
        "/api/cotizar_envio", json={"destino": "05001", "items": [{"sku": "NO-EXISTE"}]}
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["tipo"] == "ProductoDesconocidoError"


# --------------------------------------------------------------------------- #
# validar_documento_dian
# --------------------------------------------------------------------------- #


def test_el_dv_se_calcula_cuando_el_cliente_no_lo_dicta(cliente: TestClient) -> None:
    """El cliente de una tienda casi nunca se sabe el digito de verificacion."""
    datos = cliente.post(
        "/api/validar_documento_dian", json={"tipo": "NIT", "numero": "890903938"}
    ).json()
    assert datos["valido"] is True
    assert datos["dv"] == 8
    assert datos["dv_calculado"] is True
    assert datos["formateado"] == "890.903.938-8"
    assert datos["es_persona_juridica"] is True
    assert datos["codigo_dian"] == "31"


def test_un_dv_dictado_correcto_no_se_marca_como_calculado(cliente: TestClient) -> None:
    """Distinguirlo importa: le dice al agente si confiar en lo que le dictaron."""
    datos = cliente.post(
        "/api/validar_documento_dian", json={"tipo": "NIT", "numero": "890.903.938-8"}
    ).json()
    assert datos["dv"] == 8
    assert datos["dv_calculado"] is False


def test_un_documento_invalido_responde_200_con_el_motivo(cliente: TestClient) -> None:
    """Validar es la funcion de la herramienta: un 'no' es una respuesta, no un error."""
    respuesta = cliente.post(
        "/api/validar_documento_dian", json={"tipo": "NIT", "numero": "890903938-1"}
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["valido"] is False
    assert "corresponde 8" in datos["mensaje"]
    assert datos["numero"] is None


def test_un_tipo_de_documento_desconocido_tambien_responde_200(cliente: TestClient) -> None:
    """El agente necesita la lista de admitidos, no un 500."""
    datos = cliente.post(
        "/api/validar_documento_dian", json={"tipo": "DNI", "numero": "1234567"}
    ).json()
    assert datos["valido"] is False
    assert "admitidos" in datos["mensaje"]


def test_una_cedula_no_lleva_digito_de_verificacion(cliente: TestClient) -> None:
    """Solo el NIT lo lleva; una CC con DV es un error de captura."""
    datos = cliente.post(
        "/api/validar_documento_dian", json={"tipo": "CC", "numero": "1.017.234.567"}
    ).json()
    assert datos["valido"] is True
    assert datos["dv"] is None
    assert datos["codigo_dian"] == "13"
    assert datos["es_persona_juridica"] is False


# --------------------------------------------------------------------------- #
# calcular_total_con_iva
# --------------------------------------------------------------------------- #


def test_un_carrito_de_tienda_atraviesa_cinco_tratamientos(cliente: TestClient) -> None:
    """Cinco lineas de mercado ya obligan a liquidar cuatro regimenes distintos."""
    datos = cliente.post(
        "/api/calcular_total_con_iva", json={"items": MERCADO, "destino": "05001"}
    ).json()
    aplicados = {linea["regimen_aplicado"] for linea in datos["lineas"]}
    assert aplicados == {"excluido", "exento", "gravado_5", "gravado_19", "inc_8"}
    tributos = {(s["tributo"], s["tarifa"]) for s in datos["subtotales"]}
    assert tributos == {
        ("IVA", "0,00 %"),
        ("IVA", "5,00 %"),
        ("IVA", "19,00 %"),
        ("INC", "8,00 %"),
    }


def test_el_impuesto_por_linea_suma_exactamente_el_total(cliente: TestClient) -> None:
    """La DIAN valida esa igualdad al centavo; medio centavo rechaza la factura."""
    datos = cliente.post("/api/calcular_total_con_iva", json={"items": MERCADO}).json()
    suma = sum(linea["impuesto"]["centavos"] for linea in datos["lineas"])
    assert suma == datos["iva"]["centavos"] + datos["inc"]["centavos"]
    assert datos["total"]["centavos"] == datos["base_gravable"]["centavos"] + suma


def test_exento_lleva_linea_de_impuesto_y_excluido_no(cliente: TestClient) -> None:
    """La diferencia que confundirla falsea el precio y la declaracion."""
    datos = cliente.post(
        "/api/calcular_total_con_iva",
        json={"items": [{"sku": "LAC-LEC-1L"}, {"sku": "FRU-PLA-LB"}]},
    ).json()
    leche, platano = datos["lineas"]
    assert leche["regimen_aplicado"] == "exento"
    assert leche["tributo"] == "IVA"
    assert leche["tarifa"] == "0,00 %"
    assert leche["da_derecho_a_descontables"] is True
    assert platano["regimen_aplicado"] == "excluido"
    assert platano["tributo"] is None
    assert platano["da_derecho_a_descontables"] is False
    assert datos["descontables"]["base_sin_derecho"]["centavos"] == 2_800_00


def test_el_destino_puede_apagar_el_iva_entero(cliente: TestClient) -> None:
    """Art. 423 ET y Art. 270 de la Ley 223 de 1995: el destino cambia el impuesto."""
    datos = cliente.post(
        "/api/calcular_total_con_iva", json={"items": MERCADO, "destino": "88001"}
    ).json()
    assert datos["iva"]["centavos"] == 0
    assert {linea["regimen_aplicado"] for linea in datos["lineas"]} == {"excluido", "inc_8"}
    assert any("423" in nota for nota in datos["notas"])
    ajustadas = [
        linea
        for linea in datos["lineas"]
        if linea["regimen_solicitado"] != linea["regimen_aplicado"]
    ]
    assert len(ajustadas) == 3  # la leche exenta, el cafe al 5 % y el jabon al 19 %
    assert all("423" in linea["motivo_ajuste"] for linea in ajustadas)
    # el platano ya venia excluido: no se ajusto nada y por eso no lleva motivo
    platano = next(linea for linea in datos["lineas"] if "Platano" in linea["descripcion"])
    assert platano["motivo_ajuste"] is None


def test_un_comercio_no_responsable_de_iva_no_lo_puede_cobrar(cliente: TestClient) -> None:
    """Art. 437 par. 3 ET: no puede cobrarlo ni discriminarlo en la factura."""
    datos = cliente.post(
        "/api/calcular_total_con_iva", json={"items": ASEO, "responsable_iva": False}
    ).json()
    assert datos["iva"]["centavos"] == 0
    assert any("437" in nota for nota in datos["notas"])


def test_los_impuestos_saludables_se_explican_pero_no_se_cobran(cliente: TestClient) -> None:
    """IBUA e ICUI son monofasicos: ya vienen dentro del costo de compra."""
    datos = cliente.post(
        "/api/calcular_total_con_iva", json={"items": [{"sku": "BEB-GAS-15"}]}
    ).json()
    assert datos["lleva_impuestos_saludables"] is True
    assert "513-2" in datos["nota_impuestos_saludables"]
    assert datos["lineas"][0]["tarifa"] == "19,00 %"


def test_una_cantidad_no_positiva_es_422(cliente: TestClient) -> None:
    """El dominio la rechaza y la traduccion la convierte en peticion corregible."""
    respuesta = cliente.post(
        "/api/calcular_total_con_iva", json={"items": [{"sku": "ASE-JAB-X3", "cantidad": 0}]}
    )
    assert respuesta.status_code == 422


# --------------------------------------------------------------------------- #
# consultar_derecho_retracto
# --------------------------------------------------------------------------- #


def test_semana_santa_estira_cinco_habiles_a_ocho_de_calendario(cliente: TestClient) -> None:
    """Entrega el Jueves Santo de 2026: el plazo vence el 10 de abril."""
    datos = cliente.post(
        "/api/consultar_derecho_retracto",
        json={"fecha_entrega": "2026-04-02", "modalidad": "whatsapp"},
    ).json()
    assert datos["aplica"] is True
    assert datos["vence"] == "2026-04-10"
    assert datos["dias_habiles"] == 5
    assert datos["dias_calendario"] == 8
    nombres = {f["nombre"] for f in datos["festivos_intermedios"]}
    assert {"Jueves Santo", "Viernes Santo"} <= nombres


def test_en_el_mostrador_no_hay_retracto(cliente: TestClient) -> None:
    """El Art. 47 solo cubre ventas a distancia o por metodos no tradicionales."""
    datos = cliente.post(
        "/api/consultar_derecho_retracto",
        json={"fecha_entrega": "2026-09-01", "modalidad": "mostrador"},
    ).json()
    assert datos["aplica"] is False
    assert datos["vence"] is None
    assert "punto de venta" in datos["motivo"]


def test_las_causales_del_carrito_se_detectan_solas(cliente: TestClient) -> None:
    """Una arepa no se devuelve porque es perecedera, y hay que poder decirlo."""
    datos = cliente.post(
        "/api/consultar_derecho_retracto",
        json={
            "fecha_entrega": "2026-09-01",
            "modalidad": "domicilio",
            "items": [{"sku": "PAN-ARE-X5"}],
        },
    ).json()
    assert datos["aplica"] is False
    assert datos["exclusiones_detectadas"] == ["perecedero"]
    assert "paragrafo" in datos["motivo"]


def test_con_hoy_se_devuelven_los_dias_que_quedan(cliente: TestClient) -> None:
    """Un agente que atiende un reclamo necesita saber si el plazo sigue vivo."""
    datos = cliente.post(
        "/api/consultar_derecho_retracto",
        json={"fecha_entrega": "2026-09-01", "modalidad": "tienda_virtual", "hoy": "2026-09-03"},
    ).json()
    assert datos["vigente"] is True
    assert datos["dias_habiles_restantes"] == 4
    assert datos["dias_para_devolver_dinero"] == 30


def test_sin_hoy_no_se_inventa_una_vigencia(cliente: TestClient) -> None:
    """El dominio no lee el reloj: sin fecha de referencia la respuesta es nula."""
    datos = cliente.post(
        "/api/consultar_derecho_retracto",
        json={"fecha_entrega": "2026-09-01", "modalidad": "telefono"},
    ).json()
    assert datos["vigente"] is None
    assert datos["dias_habiles_restantes"] is None


def test_una_modalidad_desconocida_lista_las_admitidas(cliente: TestClient) -> None:
    """El mensaje de error tiene que ser accionable sin consultar documentacion."""
    respuesta = cliente.post(
        "/api/consultar_derecho_retracto",
        json={"fecha_entrega": "2026-09-01", "modalidad": "telepatia"},
    )
    assert respuesta.status_code == 422
    assert "domicilio" in respuesta.json()["error"]


def test_una_exclusion_inventada_es_422(cliente: TestClient) -> None:
    """El catalogo de causales del paragrafo es cerrado."""
    respuesta = cliente.post(
        "/api/consultar_derecho_retracto",
        json={"fecha_entrega": "2026-09-01", "exclusiones": ["me_arrepenti"]},
    )
    assert respuesta.status_code == 422


# --------------------------------------------------------------------------- #
# metodos_de_pago
# --------------------------------------------------------------------------- #


def test_se_devuelven_los_cinco_rieles_con_su_motivo(cliente: TestClient) -> None:
    """Los que no aplican tambien viajan: el agente debe poder explicar el porque."""
    datos = cliente.post("/api/metodos_de_pago", json={"items": ASEO, "destino": "Pasto"}).json()
    assert len(datos["metodos"]) == len(pago.MetodoPago)
    assert all(m["motivos"] for m in datos["metodos"] if not m["disponible"])
    assert datos["recomendado"] in {m["metodo"] for m in datos["metodos"] if m["disponible"]}


def test_el_total_es_mercancia_mas_flete_sin_iva_sobre_el_flete(cliente: TestClient) -> None:
    """Art. 476 num. 2 ET: el transporte nacional de carga esta excluido del IVA."""
    datos = cliente.post("/api/metodos_de_pago", json={"items": ASEO, "destino": "Cali"}).json()
    desglose = datos["desglose"]
    assert desglose["flete"]["centavos"] > 0
    assert (
        desglose["total_pedido"]["centavos"]
        == desglose["mercancia"]["centavos"] + desglose["flete"]["centavos"]
    )
    assert "476" in desglose["nota_flete"]


def test_sin_flete_el_total_es_solo_la_mercancia(cliente: TestClient) -> None:
    """Para una recogida en tienda el flete no existe y no se puede cobrar."""
    datos = cliente.post(
        "/api/metodos_de_pago", json={"items": ASEO, "destino": "Cali", "incluir_flete": False}
    ).json()
    assert datos["desglose"]["flete"]["centavos"] == 0
    assert datos["desglose"]["total_pedido"] == datos["desglose"]["mercancia"]


def test_en_un_destino_sin_carretera_el_contraentrega_se_descarta(cliente: TestClient) -> None:
    """La restriccion logistica se propaga hasta el medio de pago."""
    datos = cliente.post("/api/metodos_de_pago", json={"items": ASEO, "destino": "Mitu"}).json()
    contra = next(m for m in datos["metodos"] if m["metodo"] == "contraentrega")
    assert contra["disponible"] is False
    assert "agente local" in " ".join(contra["motivos"])


def test_pse_no_arranca_sin_banco_y_arranca_con_uno_valido(cliente: TestClient) -> None:
    """PSE exige que el cliente elija su banco antes de iniciar el debito."""
    sin = cliente.post("/api/metodos_de_pago", json={"items": ASEO, "destino": "Cali"}).json()
    con = cliente.post(
        "/api/metodos_de_pago",
        json={"items": ASEO, "destino": "Cali", "banco_pse": "Bancolombia"},
    ).json()
    assert next(m for m in sin["metodos"] if m["metodo"] == "pse")["disponible"] is False
    assert next(m for m in con["metodos"] if m["metodo"] == "pse")["disponible"] is True
    assert "bancolombia" in con["bancos_pse"]


def test_nequi_se_cae_por_el_tope_de_deposito_de_bajo_monto(cliente: TestClient) -> None:
    """Decreto 2555 de 2010: ocho salarios minimos por operacion."""
    grande = [{"sku": "MAS-CON-2K", "cantidad": 500}]
    datos = cliente.post("/api/metodos_de_pago", json={"items": grande, "destino": "Cali"}).json()
    nequi = next(m for m in datos["metodos"] if m["metodo"] == "nequi")
    assert nequi["disponible"] is False
    assert "salarios minimos" in " ".join(nequi["motivos"])
    assert datos["parametros"]["tope_deposito_bajo_monto"]["centavos"] == 8 * 1_423_500_00


def test_la_tarjeta_reporta_retencion_comision_y_cuatro_por_mil(cliente: TestClient) -> None:
    """El costo real para el comercio no es solo la comision de la pasarela."""
    datos = cliente.post("/api/metodos_de_pago", json={"items": ASEO, "destino": "Cali"}).json()
    tarjeta = next(m for m in datos["metodos"] if m["metodo"] == "tarjeta")
    assert tarjeta["retencion"]["centavos"] > 0
    assert tarjeta["gmf"]["centavos"] > 0
    assert (
        tarjeta["costo_total_comercio"]["centavos"]
        == tarjeta["comision"]["centavos"]
        + tarjeta["retencion"]["centavos"]
        + tarjeta["gmf"]["centavos"]
    )
    assert tarjeta["cuotas_maximas"] == 36


def test_un_carrito_de_solo_servicios_no_admite_contraentrega(cliente: TestClient) -> None:
    """No hay bulto que entregar, asi que no hay a quien pagarle al recibir."""
    datos = cliente.post(
        "/api/metodos_de_pago", json={"items": [{"sku": "PRE-ALM-COR"}], "destino": "05001"}
    ).json()
    assert datos["desglose"]["flete"]["centavos"] == 0
    contra = next(m for m in datos["metodos"] if m["metodo"] == "contraentrega")
    assert contra["disponible"] is False


def test_un_pedido_sin_items_es_422(cliente: TestClient) -> None:
    """Un pedido sin valor no se puede cobrar por ningun riel."""
    respuesta = cliente.post("/api/metodos_de_pago", json={"items": [], "destino": "Cali"})
    assert respuesta.status_code == 422


# --------------------------------------------------------------------------- #
# la vitrina y la capa HTTP tienen que estar de acuerdo
# --------------------------------------------------------------------------- #


def _vitrina() -> str:
    """El HTML servido, leido una sola vez."""
    return ARCHIVO_INDEX.read_text(encoding="utf-8")


def test_la_vitrina_registra_las_seis_rutas_mas_las_dos_del_carrito() -> None:
    """El nombre de la herramienta y el de la ruta no pueden divergir."""
    html = _vitrina()
    declarados = set(re.findall(r'nombre: "(\w+)",\n    nivel:', html))
    assert declarados == set(HERRAMIENTAS) | set(SOLO_PAGINA)


def test_la_vitrina_apunta_a_las_rutas_reales(cliente: TestClient) -> None:
    """Cada ruta que el JavaScript llama tiene que existir en la aplicacion."""
    esquema = cliente.get("/openapi.json").json()
    for ruta in set(re.findall(r'"(/api/\w+)"', _vitrina())):
        assert ruta in esquema["paths"], ruta


def test_la_vitrina_usa_la_api_webmcp_esperada() -> None:
    """registerTool, el evento toolchange y la degradacion sin modelContext."""
    html = _vitrina()
    assert "document.modelContext" in html
    assert "mc.registerTool(" in html
    assert 'addEventListener("toolchange"' in html
    assert "aviso-sin-webmcp" in html


def test_toda_herramienta_declara_sus_anotaciones() -> None:
    """readOnlyHint y untrustedContentHint tienen que estar en las ocho."""
    html = _vitrina()
    total = len(HERRAMIENTAS) + len(SOLO_PAGINA)
    assert html.count("readOnlyHint:") == total
    assert html.count("untrustedContentHint:") == total


def test_la_superficie_es_escalonada_y_no_plana() -> None:
    """Si todas las herramientas viven en el nivel 0, no hay superficie dinamica."""
    niveles = [int(n) for n in re.findall(r"nivel: (\d),", _vitrina())]
    assert len(niveles) == len(HERRAMIENTAS) + len(SOLO_PAGINA)
    assert sorted(niveles) == [0, 0, 0, 0, 1, 1, 1, 2]


def test_la_vitrina_no_depende_de_ninguna_red_externa() -> None:
    """Un archivo autocontenido: sin CDN, sin fuentes remotas, sin build."""
    html = _vitrina()
    assert 'src="http' not in html
    assert 'href="http' not in html
    assert "<link" not in html


def test_el_arnes_de_pruebas_del_navegador_no_se_publica() -> None:
    """Los archivos del arnes headless no pueden quedar servidos en produccion."""
    sobrantes = sorted(p.name for p in ARCHIVO_INDEX.parent.glob("__*.html"))
    assert sobrantes == [], f"borrar del directorio estatico: {sobrantes}"


def test_los_esquemas_de_entrada_son_json_schema_valido() -> None:
    """Un esquema mal formado deja la herramienta inservible para el agente."""
    html = _vitrina()
    for bruto in re.findall(r'\{ type: "string", enum: \[([^\]]*)\]', html):
        assert bruto.strip()
    total = len(HERRAMIENTAS) + len(SOLO_PAGINA)
    # +1: el objeto anidado de cada linea de `lineas` en agregar_al_carrito
    assert html.count('type: "object"') == total + 1
    assert html.count("additionalProperties: false") == total + 1


def test_la_documentacion_declara_el_codigo_preexistente() -> None:
    """El concurso exige revelar que parte del codigo no es nueva."""
    doc = Path(__file__).resolve().parents[2] / "docs" / "NEW-VS-PREEXISTING.md"
    texto = doc.read_text(encoding="utf-8")
    assert "fastapi" in texto.lower()
    assert "MIT" in texto


def test_el_openapi_se_genera_sin_errores(cliente: TestClient) -> None:
    """Si el esquema no serializa, ningun cliente generado va a funcionar."""
    respuesta = cliente.get("/openapi.json")
    assert respuesta.status_code == 200
    esquema = json.loads(respuesta.text)
    assert esquema["info"]["title"] == "Tendero"


def test_la_app_arranca_aunque_falte_el_directorio_estatico(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Un despliegue que monte la API sin la vitrina no puede caerse al importar.

    El montaje de archivos estaticos es opcional: si el directorio no esta, la
    API sigue sirviendo las seis capacidades y solo se pierde la pagina.
    """
    monkeypatch.setattr(api, "DIRECTORIO_ESTATICOS", tmp_path / "no-existe")
    sin_vitrina = api.crear_app()
    with TestClient(sin_vitrina) as suelta:
        assert suelta.get("/health").json()["estado"] == "ok"
        assert suelta.post("/api/buscar_productos", json={"consulta": "cafe"}).status_code == 200
        assert suelta.get("/static/index.html").status_code == 404

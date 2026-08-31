"""Arnes diferencial: el JavaScript de la vitrina contra el Python del dominio.

El puerto de ``src/tendero/domain/`` a ``static/dominio.js`` mueve la logica de
negocio dentro de la pagina para que la vitrina se pueda publicar sin backend.
Eso solo vale si el JavaScript responde EXACTAMENTE lo mismo que el Python, que
es la especificacion: 363 pruebas, cobertura completa, y donde los dos difieran
el que esta mal es el JavaScript.

Este archivo no vuelve a probar las reglas colombianas --de eso se encarga
``tests/unit`` y ``tests/api``-- sino que las dos implementaciones coinciden. La
mecanica es:

1. se construye un corpus de casos concretos, sacados de lo que el Python ya
   afirma (cada NIT, cada ciudad, cada festivo, cada caso de IVA, cada ventana
   de retracto) y ensanchado con barridos donde un port se rompe callado;
2. cada caso se ejecuta en Python;
3. los MISMOS casos se mandan de una sola vez a ``node runner.mjs`` --un unico
   proceso, no uno por caso-- y se ejecutan contra ``static/dominio.js``;
4. se comparan valor a valor y se reporta cada divergencia con su entrada y las
   dos respuestas.

Se compara tambien el texto de los errores: el mensaje del dominio es parte del
contrato, porque el agente lo lee para corregir su llamada y la vitrina lo
pinta. Un mensaje distinto es una divergencia.

Uso:
    python3 tests/parity/test_parity.py      # informe legible
    pytest tests/parity/test_parity.py       # falla si hay una sola divergencia
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import cast

RAIZ = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve().parent / "runner.mjs"
NODE = shutil.which("node")
"""El interprete que ejecuta el lado JavaScript.

Sin ``node`` no hay comparacion posible. La prueba se SALTA en vez de fallar
--para que una imagen sin node no de un rojo enganoso-- pero el motivo queda
escrito: un salto silencioso convertiria este archivo en decoracion. El job
``parity`` de ``.gitlab-ci.yml`` instala node justamente para que corra.
"""
sys.path.insert(0, str(RAIZ / "src"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tendero.api import app  # noqa: E402
from tendero.domain import (  # noqa: E402
    catalogo,
    dinero,
    documento,
    envio,
    impuesto,
    pago,
    retracto,
)
from tendero.domain.errores import DominioError  # noqa: E402

CLIENTE = TestClient(app)

ZONAS_HORARIAS = (
    "UTC",
    "America/Bogota",  # donde vive el comercio: UTC-5
    "Pacific/Kiritimati",  # UTC+14, el extremo que rompe un port con hora local
    "Pacific/Midway",  # UTC-11
    "Asia/Kolkata",  # UTC+5:30, offset no entero
)
"""El JavaScript corre en el navegador del visitante, en cualquier parte.

Una fecha civil construida con ``new Date(a, m, d)`` --hora LOCAL-- nace a
medianoche local y al serializarla con ``toISOString()`` se corre un dia en
cualquier zona al ESTE de Greenwich. En Bogota (UTC-5) el error es invisible,
asi que probar solo aqui no demuestra nada: el corpus se corre entero contra
cada una de estas zonas y todas tienen que dar la misma respuesta que el
Python, que es naive y no depende de ninguna.
"""

CLASES_DOMINIO = {
    "DominioError",
    "DocumentoInvalidoError",
    "CiudadDesconocidaError",
    "ProductoDesconocidoError",
    "MetodoPagoError",
}


# --------------------------------------------------------------------------- #
# Utilidades comunes a los dos lados
# --------------------------------------------------------------------------- #

type Json = None | bool | int | float | str | Sequence[Json] | Mapping[str, Json]
"""Lo que sobrevive a un viaje por JSON, que es como los casos llegan a node.

Se escribe con ``Sequence``/``Mapping`` y no con ``list``/``dict`` porque son
covariantes: asi una ``list[int]`` del corpus entra sin copiarla. Lo que sale de
aqui se estrecha con los ayudantes de abajo, nunca se supone.
"""

type JsonObject = Mapping[str, Json]

type Resultado = Mapping[str, object]
"""La respuesta a un caso: ``{"valor": ...}`` o ``{"error": {...}}``.

El lado Python contesta con objetos del dominio --``Decimal``, tuplas-- que no
son JSON, asi que el valor viaja como ``object`` y se estrecha al leerlo.
"""


def _txt(v: object) -> str:
    """Estrecha a texto: el corpus escribio la entrada, aqui solo se reconoce."""
    if not isinstance(v, str):
        msg = f"se esperaba texto y llego {type(v).__name__}: {v!r}"
        raise TypeError(msg)
    return v


def _txt_opc(v: object) -> str | None:
    return None if v is None else _txt(v)


def _ent(v: object) -> int:
    if not isinstance(v, int):
        msg = f"se esperaba un entero y llego {type(v).__name__}: {v!r}"
        raise TypeError(msg)
    return v


def _ent_opc(v: object) -> int | None:
    return None if v is None else _ent(v)


def _si(v: object) -> bool:
    if not isinstance(v, bool):
        msg = f"se esperaba un booleano y llego {type(v).__name__}: {v!r}"
        raise TypeError(msg)
    return v


def _obj(v: object) -> JsonObject:
    if not isinstance(v, Mapping):
        msg = f"se esperaba un objeto y llego {type(v).__name__}: {v!r}"
        raise TypeError(msg)
    return v


def _lista(v: object) -> Sequence[Json]:
    if isinstance(v, str) or not isinstance(v, Sequence):
        msg = f"se esperaba una lista y llego {type(v).__name__}: {v!r}"
        raise TypeError(msg)
    return v


def _objetos(v: object) -> list[JsonObject]:
    return [_obj(x) for x in _lista(v)]


def _textos(v: object) -> list[str]:
    return [_txt(x) for x in _lista(v)]


def _enteros(v: object) -> list[int]:
    return [_ent(x) for x in _lista(v)]


def _modalidad(v: object) -> retracto.Modalidad:
    """La modalidad TAL CUAL la escribio el corpus, sin coercionarla al enum.

    ``Modalidad`` es un StrEnum: sus miembros son cadenas y el dominio resuelve
    la pertenencia por valor. Coercionar aqui --y no del otro lado-- compararia
    dos llamadas distintas, asi que el texto crudo pasa tal cual y el tipo se
    afirma sin tocar el valor.
    """
    return cast(retracto.Modalidad, _txt(v))


def _tarifa(num: int, den: int) -> Decimal:
    """La misma fraccion exacta que ``tarifa(num, den)`` en el JavaScript."""
    return Decimal(num) / Decimal(den)


def _pct(tar: Decimal) -> str:
    """``porcentaje()`` del JavaScript: dos decimales y coma."""
    return f"{tar * 100:.2f}".replace(".", ",")


def _iso(f: date | None) -> str | None:
    return f.isoformat() if f is not None else None


def _ciudad(x: object) -> envio.Ciudad | None:
    return None if x is None else envio.resolver_ciudad(_txt(x))


def _lineas(spec: object) -> list[impuesto.LineaVenta]:
    return [
        impuesto.LineaVenta(
            descripcion=_txt(x["descripcion"]),
            regimen=impuesto.Regimen(_txt(x["regimen"])),
            precio_unitario_centavos=_ent(x["precio"]),
            cantidad=_ent(x.get("cantidad", 1)),
            descuento_centavos=_ent(x.get("descuento", 0)),
        )
        for x in _objetos(spec)
    ]


def _paquete(a: JsonObject) -> envio.Paquete:
    return envio.Paquete(
        peso_gramos=_ent(a["peso"]),
        largo_cm=_ent(a.get("largo", 20)),
        ancho_cm=_ent(a.get("ancho", 20)),
        alto_cm=_ent(a.get("alto", 15)),
        valor_declarado_centavos=_ent(a.get("valor", 0)),
    )


def _contexto_pago(a: JsonObject) -> pago.ContextoPago:
    return pago.ContextoPago(
        total_centavos=_ent(a["total"]),
        ciudad=envio.resolver_ciudad(_txt(a["ciudad"])),
        base_sin_impuestos_centavos=_ent(a.get("base_sin_impuestos", 0)),
        comision_recaudo_centavos=_ent(a.get("comision_recaudo", 0)),
        contiene_servicios=_si(a.get("contiene_servicios", False)),
        banco_pse=_txt_opc(a.get("banco_pse")),
        cliente_tiene_bancolombia=_si(a.get("cliente_tiene_bancolombia", False)),
    )


# --------------------------------------------------------------------------- #
# Serializadores: cada uno emite la misma forma que su gemelo en runner.mjs
# --------------------------------------------------------------------------- #


def _ser_ciudad(c: envio.Ciudad) -> JsonObject:
    return {
        "codigo_dane": c.codigo_dane,
        "nombre": c.nombre,
        "departamento": c.departamento,
        "etiqueta": c.etiqueta,
        "zona": c.zona.value,
        "solo_aereo": c.solo_aereo,
        "regimen_iva_especial": c.regimen_iva_especial,
    }


def _ser_cotizacion(c: envio.Cotizacion) -> JsonObject:
    return {
        "transportadora": c.transportadora,
        "codigo_transportadora": c.codigo_transportadora,
        "ciudad": c.ciudad.codigo_dane,
        "peso_facturable_gramos": c.peso_facturable_gramos,
        "flete_centavos": c.flete_centavos,
        "recargo_aereo_centavos": c.recargo_aereo_centavos,
        "manejo_centavos": c.manejo_centavos,
        "recaudo_centavos": c.recaudo_centavos,
        "dias_habiles_minimo": c.dias_habiles_minimo,
        "dias_habiles_maximo": c.dias_habiles_maximo,
        "contraentrega": c.contraentrega,
        "notas": list(c.notas),
        "total_centavos": c.total_centavos,
    }


def _ser_linea(linea: impuesto.LineaLiquidada) -> JsonObject:
    return {
        "descripcion": linea.descripcion,
        "cantidad": linea.cantidad,
        "regimen_solicitado": linea.regimen_solicitado.value,
        "regimen_aplicado": linea.regimen_aplicado.value,
        "tributo": linea.tributo,
        "tarifa": _pct(linea.tarifa),
        "bruto_centavos": linea.bruto_centavos,
        "descuento_centavos": linea.descuento_centavos,
        "base_gravable_centavos": linea.base_gravable_centavos,
        "impuesto_centavos": linea.impuesto_centavos,
        "total_centavos": linea.total_centavos,
        "fundamento": linea.fundamento,
        "motivo_ajuste": linea.motivo_ajuste,
        "da_derecho_a_descontables": linea.da_derecho_a_descontables,
    }


def _ser_liquidacion(q: impuesto.Liquidacion) -> JsonObject:
    r = impuesto.resumen_descontables(q)
    return {
        "lineas": [_ser_linea(x) for x in q.lineas],
        "subtotales": [
            {
                "tributo": s.tributo,
                "tarifa": s.tarifa_porcentual,
                "base_centavos": s.base_centavos,
                "valor_centavos": s.valor_centavos,
            }
            for s in q.subtotales
        ],
        "bruto_centavos": q.bruto_centavos,
        "descuentos_centavos": q.descuentos_centavos,
        "base_gravable_centavos": q.base_gravable_centavos,
        "iva_centavos": q.iva_centavos,
        "inc_centavos": q.inc_centavos,
        "total_centavos": q.total_centavos,
        "notas": list(q.notas),
        "descontables": {
            "base_con_derecho_centavos": r.base_con_derecho_centavos,
            "base_sin_derecho_centavos": r.base_sin_derecho_centavos,
            "nota": r.nota,
        },
    }


def _ser_festivo(f: retracto.Festivo) -> JsonObject:
    return {
        "fecha": _iso(f.fecha),
        "nombre": f.nombre,
        "trasladado": f.trasladado,
        "fecha_original": _iso(f.fecha_original),
        "fundamento": f.fundamento,
    }


def _ser_evaluacion(e: pago.EvaluacionPago) -> JsonObject:
    return {
        "metodo": e.metodo.value,
        "nombre": e.nombre,
        "disponible": e.disponible,
        "motivos": list(e.motivos),
        "requisitos": list(e.requisitos),
        "recargo_cliente_centavos": e.recargo_cliente_centavos,
        "comision_centavos": e.comision_centavos,
        "retencion_centavos": e.retencion_centavos,
        "gmf_centavos": e.gmf_centavos,
        "costo_total_comercio_centavos": e.costo_total_comercio_centavos,
        "dias_habiles_liquidacion": e.dias_habiles_liquidacion,
        "cuotas_maximas": e.cuotas_maximas,
        "total_cliente_centavos": e.total_cliente_centavos,
        "neto_comercio_centavos": e.neto_comercio_centavos,
        "notas": list(e.notas),
    }


def _ser_producto(p: catalogo.Producto) -> JsonObject:
    return {
        "sku": p.sku,
        "nombre": p.nombre,
        "categoria": p.categoria.value,
        "regimen": p.regimen.value,
        "precio_base_centavos": p.precio_base_centavos,
        "peso_gramos": p.peso_gramos,
        "largo_cm": p.largo_cm,
        "ancho_cm": p.ancho_cm,
        "alto_cm": p.alto_cm,
        "fundamento": p.fundamento,
        "exclusiones_retracto": sorted(p.exclusiones_retracto),
        "es_servicio": p.es_servicio,
        "impuesto_saludable_incorporado": p.impuesto_saludable_incorporado,
    }


# --------------------------------------------------------------------------- #
# Tabla de operaciones del lado Python
# --------------------------------------------------------------------------- #


def _op_herramienta(a: JsonObject) -> Json:
    """Llama la ruta HTTP homonima: es la referencia que la pagina consumia."""
    respuesta = CLIENTE.post(f"/api/{_txt(a['nombre'])}", json=a["payload"])
    cuerpo = _obj(respuesta.json())
    if respuesta.status_code == 200:
        return cuerpo
    tipo = _txt(cuerpo.get("tipo", "Error"))
    raise _ErrorDeDominioTraducidoError(
        _txt(cuerpo.get("error", "")), tipo if tipo in CLASES_DOMINIO else "Error"
    )


class _ErrorDeDominioTraducidoError(Exception):
    """Error de negocio que ya llego traducido desde la capa HTTP."""

    def __init__(self, mensaje: str, clase: str) -> None:
        super().__init__(mensaje)
        self.clase = clase


def _op_tablas(_a: JsonObject) -> JsonObject:
    """Las tablas maestras completas: si un dato del catalogo cambia, se ve."""
    return {
        "dv_nit_pesos": list(documento.DV_NIT_PESOS),
        "tipos_documento": sorted(t.value for t in documento.TipoDocumento),
        "reglas": [
            {
                "tipo": r.tipo.value,
                "codigo_dian": r.codigo_dian,
                "nombre": r.nombre,
                "largo_minimo": r.largo_minimo,
                "largo_maximo": r.largo_maximo,
                "solo_digitos": r.solo_digitos,
                "requiere_dv": r.requiere_dv,
            }
            for r in documento.REGLAS.values()
        ],
        "ciudades": [_ser_ciudad(c) for c in envio.CIUDADES.values()],
        "sin_contraentrega": sorted(envio.SIN_CONTRAENTREGA),
        "regimen_iva_especial": sorted(envio.REGIMEN_IVA_ESPECIAL),
        "transportadoras": [
            {
                "codigo": t.codigo,
                "nombre": t.nombre,
                "nit": t.nit,
                "ofrece_contraentrega": t.ofrece_contraentrega,
                "comision_recaudo": _pct(t.comision_recaudo),
                "recaudo_minimo_centavos": t.recaudo_minimo_centavos,
                "recaudo_maximo_centavos": t.recaudo_maximo_centavos,
                "comision_manejo": _pct(t.comision_manejo),
                "manejo_minimo_centavos": t.manejo_minimo_centavos,
                "sin_cobertura": sorted(t.sin_cobertura),
                "tarifas": [
                    {
                        "zona": zona.value,
                        "base_centavos": z.base_centavos,
                        "kilos_incluidos": z.kilos_incluidos,
                        "adicional_por_kilo_centavos": z.adicional_por_kilo_centavos,
                        "dias_habiles_minimo": z.dias_habiles_minimo,
                        "dias_habiles_maximo": z.dias_habiles_maximo,
                    }
                    for zona, z in sorted(t.tarifas.items(), key=lambda kv: kv[0].value)
                ],
            }
            for t in envio.TRANSPORTADORAS
        ],
        "factor_volumetrico": envio.FACTOR_VOLUMETRICO_CM3_POR_KG,
        "peso_facturable_minimo": envio.PESO_FACTURABLE_MINIMO_GRAMOS,
        "flete_excluido_de_iva": envio.FLETE_EXCLUIDO_DE_IVA,
        "tratamientos": [
            {
                "regimen": regimen.value,
                "tributo": t.tributo,
                "tarifa": _pct(t.tarifa),
                "causa_impuesto": t.causa_impuesto,
                "da_derecho_a_descontables": t.da_derecho_a_descontables,
                "fundamento": t.fundamento,
                "explicacion": t.explicacion,
            }
            for regimen, t in impuesto.TRATAMIENTOS.items()
        ],
        "tarifas_iva": [
            _pct(impuesto.TARIFA_IVA_GENERAL),
            _pct(impuesto.TARIFA_IVA_REDUCIDA),
            _pct(impuesto.TARIFA_INC_RESTAURANTES),
        ],
        "impuestos_saludables": impuesto.IMPUESTOS_SALUDABLES,
        "categorias_sin_retracto": sorted(retracto.CATEGORIAS_SIN_RETRACTO),
        "dias_habiles_retracto": retracto.DIAS_HABILES_RETRACTO,
        "dias_para_devolver_dinero": retracto.DIAS_PARA_DEVOLVER_DINERO,
        "bancos_pse": sorted(pago.BANCOS_PSE),
        "metodos_pago": [m.value for m in pago.MetodoPago],
        "parametros": {
            "anio": pago.PARAMETROS_VIGENTES.anio,
            "uvt_centavos": pago.PARAMETROS_VIGENTES.uvt_centavos,
            "smmlv_centavos": pago.PARAMETROS_VIGENTES.smmlv_centavos,
            "tope_deposito_bajo_monto_centavos": (
                pago.PARAMETROS_VIGENTES.tope_deposito_bajo_monto_centavos
            ),
            "exencion_gmf_mensual_centavos": (
                pago.PARAMETROS_VIGENTES.exencion_gmf_mensual_centavos
            ),
        },
        "tarifa_gmf": _pct(pago.TARIFA_GMF),
        "tarifa_retefuente": _pct(pago.TARIFA_RETEFUENTE_TARJETAS),
        "uvt_exentas": pago.UVT_EXENTAS_GMF_MENSUALES,
        "smmlv_tope": pago.SMMLV_TOPE_DEPOSITO_BAJO_MONTO,
        "catalogo": [_ser_producto(p) for p in catalogo.productos()],
        "categorias": [c.value for c in catalogo.Categoria],
        "comercio": {
            "nombre": catalogo.COMERCIO.nombre,
            "documento": str(catalogo.COMERCIO.documento),
            "codigo_dian": catalogo.COMERCIO.documento.codigo_dian,
            "direccion": catalogo.COMERCIO.direccion,
            "ciudad_codigo_dane": catalogo.COMERCIO.ciudad_codigo_dane,
            "responsable_iva": catalogo.COMERCIO.responsable_iva,
            "correo": catalogo.COMERCIO.correo,
        },
        "multiplo_efectivo": dinero.MULTIPLO_EFECTIVO,
        "centavos_por_peso": dinero.CENTAVOS_POR_PESO,
    }


def _op_ventana(a: JsonObject) -> JsonObject:
    v = retracto.ventana_retracto(
        date.fromisoformat(_txt(a["fecha_entrega"])),
        modalidad=_modalidad(a.get("modalidad", "domicilio")),
        exclusiones=frozenset(_textos(a["exclusiones"])) if a.get("exclusiones") else None,
        sabado_habil=_si(a.get("sabado_habil", False)),
    )
    hoy = date.fromisoformat(_txt(a["hoy"])) if a.get("hoy") else None
    return {
        "aplica": v.aplica,
        "motivo": v.motivo,
        "fecha_entrega": _iso(v.fecha_entrega),
        "inicio": _iso(v.inicio),
        "vence": _iso(v.vence),
        "dias_habiles": v.dias_habiles,
        "festivos_intermedios": [_ser_festivo(f) for f in v.festivos_intermedios],
        "dias_para_devolver_dinero": v.dias_para_devolver_dinero,
        "vigente": v.vigente(hoy) if hoy else None,
        "dias_habiles_restantes": (
            v.dias_habiles_restantes(hoy, sabado_habil=_si(a.get("sabado_habil", False)))
            if hoy
            else None
        ),
    }


def _op_carrito(a: JsonObject) -> JsonObject:
    c = catalogo.armar_carrito(
        (_txt(i["sku"]), _ent(i.get("cantidad", 1))) for i in _objetos(a["items"])
    )
    base: JsonObject = {
        "peso_gramos": c.peso_gramos,
        "contiene_servicios": c.contiene_servicios,
        "exclusiones_retracto": sorted(c.exclusiones_retracto),
        "lleva_impuestos_saludables": c.lleva_impuestos_saludables,
        "tiene_despachables": c.tiene_despachables,
        "despachables": [[x.producto.sku, x.cantidad] for x in c.despachables],
        "cantidades": [x.cantidad for x in c.lineas_venta()],
        "brutos": [x.bruto_centavos for x in c.lineas_venta()],
    }
    if not c.tiene_despachables:
        return {**base, "paquete": None}
    p = c.paquete(valor_declarado_centavos=_ent(a.get("valor_declarado", 0)))
    return {
        **base,
        "paquete": {
            "peso_gramos": p.peso_gramos,
            "largo_cm": p.largo_cm,
            "ancho_cm": p.ancho_cm,
            "alto_cm": p.alto_cm,
            "valor_declarado_centavos": p.valor_declarado_centavos,
            "peso_volumetrico_gramos": p.peso_volumetrico_gramos,
            "peso_facturable_gramos": p.peso_facturable_gramos,
        },
    }


def _op_documento_validado(a: JsonObject) -> JsonObject:
    d = documento.validar(_txt(a["tipo"]), _txt(a["valor"]))
    return {
        "tipo": d.tipo.value,
        "numero": d.numero,
        "dv": d.dv,
        "codigo_dian": d.codigo_dian,
        "nombre_regla": d.regla.nombre,
        "es_persona_juridica": d.es_persona_juridica,
        "formateado": d.formateado,
        "texto": str(d),
    }


def _op_documento_crudo(a: JsonObject) -> JsonObject:
    d = documento.Documento(
        tipo=documento.TipoDocumento(_txt(a["tipo"])),
        numero=_txt(a["numero"]),
        dv=_ent_opc(a.get("dv")),
    )
    return {"tipo": d.tipo.value, "numero": d.numero, "dv": d.dv, "texto": str(d)}


OPS: dict[str, Callable[[JsonObject], object]] = {
    # dinero
    "aplicar_tarifa": lambda a: dinero.aplicar_tarifa(
        _ent(a["base"]), _tarifa(_ent(a["num"]), _ent(a["den"]))
    ),
    "redondear_a_pesos": lambda a: dinero.redondear_a_pesos(_ent(a["monto"])),
    "redondear_efectivo": lambda a: (
        dinero.redondear_efectivo(_ent(a["monto"]))
        if "multiplo" not in a
        else dinero.redondear_efectivo(_ent(a["monto"]), multiplo=_ent(a["multiplo"]))
    ),
    "formatear_cop": lambda a: dinero.formatear_cop(
        _ent(a["monto"]), con_centavos=_si(a.get("con_centavos", False))
    ),
    "a_pesos": lambda a: str(dinero.a_pesos(_ent(a["monto"]))),
    "de_pesos": lambda a: dinero.de_pesos(_txt(a["pesos"])),
    "reparto_proporcional": lambda a: list(
        dinero.reparto_proporcional(_ent(a["total"]), tuple(_enteros(a["pesos"])))
    ),
    "porcentaje": lambda a: _pct(_tarifa(_ent(a["num"]), _ent(a["den"]))),
    # documento
    "calcular_dv_nit": lambda a: documento.calcular_dv_nit(_txt(a["base"])),
    "verificar_dv_nit": lambda a: documento.verificar_dv_nit(_txt(a["base"]), _ent(a["dv"])),
    "separar_dv": lambda a: list(documento.separar_dv(_txt(a["valor"]))),
    "normalizar": lambda a: documento.normalizar(_txt(a["valor"])),
    "formatear_nit": lambda a: documento.formatear_nit(_txt(a["base"]), _ent(a["dv"])),
    "es_valido": lambda a: documento.es_valido(_txt(a["tipo"]), _txt(a["valor"])),
    "validar_documento": _op_documento_validado,
    "documento_crudo": _op_documento_crudo,
    # envio
    "resolver_ciudad": lambda a: _ser_ciudad(envio.resolver_ciudad(_txt(a["consulta"]))),
    "buscar_ciudades": lambda a: [c.codigo_dane for c in envio.buscar_ciudades(_txt(a["texto"]))],
    "diagnostico_contraentrega": lambda a: list(
        envio.diagnostico_contraentrega(_txt(a["destino"]))
    ),
    "tope_contraentrega": lambda a: envio.tope_contraentrega(_txt(a["destino"])),
    "paquete": lambda a: {
        "peso_volumetrico_gramos": _paquete(a).peso_volumetrico_gramos,
        "peso_facturable_gramos": _paquete(a).peso_facturable_gramos,
    },
    "cotizar": lambda a: [
        _ser_cotizacion(c)
        for c in envio.cotizar(
            _txt(a["destino"]),
            _paquete(a),
            contraentrega=_si(a.get("contraentrega", False)),
            monto_a_recaudar_centavos=_ent(a.get("monto", 0)),
        )
    ],
    "mejor_cotizacion": lambda a: (
        None
        if (
            m := envio.mejor_cotizacion(
                _txt(a["destino"]),
                _paquete(a),
                contraentrega=_si(a.get("contraentrega", False)),
                monto_a_recaudar_centavos=_ent(a.get("monto", 0)),
            )
        )
        is None
        else _ser_cotizacion(m)
    ),
    # impuesto
    "liquidar": lambda a: _ser_liquidacion(
        impuesto.liquidar(
            _lineas(a["lineas"]),
            destino=_ciudad(a.get("destino")),
            responsable_iva=_si(a.get("responsable_iva", True)),
        )
    ),
    "liquidar_linea": lambda a: _ser_linea(
        impuesto.liquidar_linea(
            _lineas([a["linea"]])[0],
            destino=_ciudad(a.get("destino")),
            responsable_iva=_si(a.get("responsable_iva", True)),
        )
    ),
    "linea_venta": lambda a: {"bruto_centavos": _lineas([a])[0].bruto_centavos},
    # retracto
    "pascua": lambda a: _iso(retracto.pascua(_ent(a["anio"]))),
    "festivos": lambda a: [_ser_festivo(f) for f in retracto.festivos(_ent(a["anio"]))],
    "es_festivo": lambda a: retracto.es_festivo(date.fromisoformat(_txt(a["fecha"]))),
    "es_dia_habil": lambda a: retracto.es_dia_habil(
        date.fromisoformat(_txt(a["fecha"])), sabado_habil=_si(a.get("sabado_habil", False))
    ),
    "sumar_dias_habiles": lambda a: _iso(
        retracto.sumar_dias_habiles(
            date.fromisoformat(_txt(a["inicio"])),
            _ent(a["dias"]),
            sabado_habil=_si(a.get("sabado_habil", False)),
        )
    ),
    "dias_habiles_entre": lambda a: retracto.dias_habiles_entre(
        date.fromisoformat(_txt(a["inicio"])),
        date.fromisoformat(_txt(a["fin"])),
        sabado_habil=_si(a.get("sabado_habil", False)),
    ),
    # Se pasa la modalidad como TEXTO CRUDO, igual que el JavaScript: `Modalidad`
    # es un StrEnum, asi que sus miembros son cadenas y la pertenencia al conjunto
    # de modalidades a distancia se resuelve por valor. Coercionar aqui al enum
    # -- y no del otro lado -- compararia dos llamadas distintas. El rechazo de
    # una modalidad inventada vive en la capa de herramienta, y alli se compara.
    "aplica_retracto": lambda a: list(
        retracto.aplica_retracto(
            _modalidad(a["modalidad"]),
            exclusiones=frozenset(_textos(a["exclusiones"])) if a.get("exclusiones") else None,
        )
    ),
    "ventana_retracto": _op_ventana,
    # pago
    "gmf": lambda a: pago.gmf(_ent(a["monto"])),
    "evaluar": lambda a: [_ser_evaluacion(e) for e in pago.evaluar(_contexto_pago(a))],
    "recomendar": lambda a: pago.recomendar(_contexto_pago(a)).metodo.value,
    # catalogo
    "obtener": lambda a: _ser_producto(catalogo.obtener(_txt(a["sku"]))),
    "buscar_catalogo": lambda a: [p.sku for p in catalogo.buscar(_txt(a["texto"]))],
    "por_categoria": lambda a: [
        p.sku for p in catalogo.por_categoria(catalogo.Categoria(_txt(a["categoria"])))
    ],
    "precio_al_publico": lambda a: catalogo.precio_al_publico(
        catalogo.obtener(_txt(a["sku"])),
        destino=_ciudad(a.get("destino")),
        responsable_iva=_si(a.get("responsable_iva", True)),
        redondear=_si(a.get("redondear", True)),
    ),
    "carrito": _op_carrito,
    # herramientas
    "herramienta": _op_herramienta,
    "contexto": lambda _a: _obj(CLIENTE.get("/api/contexto").json()),
    "salud": lambda _a: {
        k: v for k, v in _obj(CLIENTE.get("/health").json()).items() if k != "version"
    },
    "tablas": _op_tablas,
    "version": lambda _a: _txt(__import__("tendero").__version__),
}


# --------------------------------------------------------------------------- #
# Corpus de casos
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Caso:
    """Una entrada concreta que las dos implementaciones tienen que responder igual."""

    id: str
    op: str
    args: JsonObject
    grupo: str


_CASOS: list[Caso] = []
_VISTOS: set[str] = set()


def caso(grupo: str, op: str, **args: Json) -> None:
    """Registra un caso; el id se deriva de la entrada para que sea legible."""
    firma = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    ident = f"{op}:{firma}"
    if ident in _VISTOS:
        return
    _VISTOS.add(ident)
    _CASOS.append(Caso(id=ident, op=op, args=args, grupo=grupo))


# --- NIT y documentos (tests/unit/test_documento.py) ----------------------- #

NITS_REALES = (
    ("890903938", 8, "Bancolombia"),
    ("860002964", 4, "Banco de Bogota"),
    ("800197268", 4, "DIAN"),
    ("890900608", 9, "Almacenes Exito"),
    ("860005224", 6, "Bavaria"),
    ("860512330", 3, "Servientrega"),
    ("830029788", 2, "Inter Rapidisimo"),
    ("860034313", 7, "entidad verificada"),
)


def _casos_documento() -> None:
    grupo = "documento"
    for base, dv, _entidad in NITS_REALES:
        caso(grupo, "calcular_dv_nit", base=base)
        caso(grupo, "verificar_dv_nit", base=base, dv=dv)
        caso(grupo, "formatear_nit", base=base, dv=dv)
        caso(grupo, "validar_documento", tipo="NIT", valor=f"{base}-{dv}")
        caso(grupo, "validar_documento", tipo="NIT", valor=base)
    # el barrido de la prueba `test_dv_coincide_en_un_barrido_amplio`
    for numero in range(800_000_000, 800_002_000):
        caso(grupo, "calcular_dv_nit", base=str(numero))
    # el barrido de `test_dv_siempre_esta_entre_cero_y_nueve`
    for numero in range(900_000_000, 900_001_000):
        caso(grupo, "calcular_dv_nit", base=str(numero))
    # residuo cero o uno
    for base in ("890903937", "890903838", "899999068"):
        caso(grupo, "calcular_dv_nit", base=base)
    # puntuacion y basura
    for valor in (
        "890.903.938",
        " 890 903 938 ",
        "89090393A",
        "1" * 16,
        "",
        "0",
        "00890903938",
        "12345678901234",
        "123456789012345",
    ):
        caso(grupo, "calcular_dv_nit", base=valor)
    # NIT de los maestros del propio dominio
    for nit in ("860512330-3", "830029788-2", "901234567-7", "900123456-8"):
        caso(grupo, "separar_dv", valor=nit)
        caso(grupo, "validar_documento", tipo="NIT", valor=nit)
    for crudo in (
        "890.903.938-8",
        "890903938-8",
        "890903938",
        " 860 512 330 - 3 ",
        "43256789-8",
        "890903938-1",
        "no-1",
        "-8",
    ):
        caso(grupo, "separar_dv", valor=crudo)
    for valor in (" ab-123.456 ", "1.017.234.567", "AB123456", "  ", "a-b-c"):
        caso(grupo, "normalizar", valor=valor)
    validos = [
        ("CC", "1.017.234.567", "13"),
        ("CC", "8123", "13"),
        ("CE", "123456", "22"),
        ("TI", "1012345678", "12"),
        ("PA", "ab-123456", "41"),
        ("PEP", "123456789012345", "47"),
        ("NIT", "890903938-8", "31"),
        ("NIT", "890.903.938-8", "31"),
        ("NIT", "43256789-8", "31"),
        ("nit", "890903938", "31"),
        (" Cc ", "1017234567", "13"),
    ]
    invalidos = [
        ("CC", "123"),
        ("CC", "12345678901"),
        ("CC", "10A2345"),
        ("CE", "1234"),
        ("TI", "123456789"),
        ("PEP", "12345678901234"),
        ("PA", "AB!123"),
        ("PA", "AB12"),
        ("NIT", "1234"),
        ("NIT", "890903938-1"),
        ("DNI", "12345678"),
        ("", "1234"),
        ("CC", ""),
    ]
    for tipo, valor, _codigo in validos:
        caso(grupo, "validar_documento", tipo=tipo, valor=valor)
        caso(grupo, "es_valido", tipo=tipo, valor=valor)
    for tipo, valor in invalidos:
        caso(grupo, "validar_documento", tipo=tipo, valor=valor)
        caso(grupo, "es_valido", tipo=tipo, valor=valor)
    # construccion directa del dataclass, sin pasar por parse
    crudos: tuple[JsonObject, ...] = (
        {"tipo": "CC", "numero": "1.017.234.567"},
        {"tipo": "CC", "numero": ""},
        {"tipo": "NIT", "numero": "890903938"},
        {"tipo": "CC", "numero": "1017234567", "dv": 3},
        {"tipo": "NIT", "numero": "890903938", "dv": 8},
        {"tipo": "NIT", "numero": "890903938", "dv": 1},
        {"tipo": "PA", "numero": "AB123456"},
    )
    for args in crudos:
        caso(grupo, "documento_crudo", **args)


# --- dinero (tests/unit/test_dinero.py) ------------------------------------ #

TARIFAS_USADAS = (
    (19, 100),  # IVA general
    (5, 100),  # IVA reducido
    (8, 100),  # INC restaurantes
    (4, 1000),  # GMF
    (15, 1000),  # retefuente tarjetas
    (299, 10000),  # comision tarjeta
    (15, 1000),  # comision Nequi (0,015)
    (45, 1000),  # comision de recaudo
    (40, 1000),
    (10, 1000),  # comision de manejo
    (12, 1000),
    (65, 100),  # recargo aereo (1,65 - 1)
    (0, 1),
)


def _casos_dinero() -> None:
    grupo = "dinero"
    for base, num, den in (
        (18_800_00, 19, 100),
        (100_00, 5, 100),
        (0, 19, 100),
        (50, 19, 100),
        (150, 19, 100),
        (3_333_33, 19, 100),
    ):
        caso(grupo, "aplicar_tarifa", base=base, num=num, den=den)
    # barrido de redondeo: el medio centavo es donde un port se rompe callado
    for num, den in TARIFAS_USADAS:
        for base in range(0, 400):
            caso(grupo, "aplicar_tarifa", base=base, num=num, den=den)
        for base in (
            999_99,
            1_000_01,
            7_900_00,
            9_150_00,
            8_475_00,
            3_050_00,
            14_200_00,
            84_000_00,
            100_000_00,
            1_234_567,
            2_777_77,
            3_333_33,
            2_000_000_01,
            11_388_000_00,
        ):
            caso(grupo, "aplicar_tarifa", base=base, num=num, den=den)
        caso(grupo, "porcentaje", num=num, den=den)
    for monto in (1_234_49, 1_234_50, 0, -1_234_50, 49, 50, 51, -49, -50, -51):
        caso(grupo, "redondear_a_pesos", monto=monto)
    for monto in (9_401_00, 9_425_00, 9_424_00, 24_00, 0, 2_500, 2_499, 2_501, -9_425_00):
        caso(grupo, "redondear_efectivo", monto=monto)
    for monto in range(0, 300):
        caso(grupo, "redondear_efectivo", monto=monto * 37)
    caso(grupo, "redondear_efectivo", monto=1_000_00, multiplo=0)
    caso(grupo, "redondear_efectivo", monto=1_000_00, multiplo=-5)
    caso(grupo, "redondear_efectivo", monto=1_234_56, multiplo=100)
    for monto in (1_234_567_89, 0, -9_400_00, 999_00, 5, -5, 100_00, -1):
        caso(grupo, "formatear_cop", monto=monto)
        caso(grupo, "formatear_cop", monto=monto, con_centavos=True)
        caso(grupo, "a_pesos", monto=monto)
    for texto_pesos in ("4300.50", "9400.37", "0", "0.005", "-1.235", "1234567.89", "12", "0.4"):
        caso(grupo, "de_pesos", pesos=texto_pesos)
    for total, pesos in (
        (10_000_00, [1, 1, 1]),
        (900_00, [2, 1]),
        (1_000_00, []),
        (1_000_00, [0, 0]),
        (7, [1, 1, 1]),
        (100, [3, 5, 7, 11]),
        (-1_000_00, [1, 1, 1]),
    ):
        caso(grupo, "reparto_proporcional", total=total, pesos=pesos)


# --- calendario y retracto (tests/unit/test_retracto.py) ------------------- #


def _casos_retracto() -> None:
    grupo = "retracto"
    for anio in range(1900, 2101):
        caso(grupo, "pascua", anio=anio)
    for anio in range(2015, 2041):
        caso(grupo, "festivos", anio=anio)
    for fecha in (
        "2026-04-01",
        "2026-04-02",
        "2026-04-03",
        "2026-04-04",
        "2026-04-05",
        "2026-04-06",
        "2026-12-25",
        "2026-08-15",
        "2026-08-17",
        "2027-01-01",
    ):
        caso(grupo, "es_festivo", fecha=fecha)
        caso(grupo, "es_dia_habil", fecha=fecha)
        caso(grupo, "es_dia_habil", fecha=fecha, sabado_habil=True)
    # cada dia de 2026 y 2027: festivo, habil y habil-con-sabado
    dia = date(2026, 1, 1)
    while dia <= date(2027, 12, 31):
        texto = dia.isoformat()
        caso(grupo, "es_festivo", fecha=texto)
        caso(grupo, "es_dia_habil", fecha=texto)
        caso(grupo, "es_dia_habil", fecha=texto, sabado_habil=True)
        # la ventana de retracto de CADA entrega del bienio: es la unica forma
        # de garantizar que ningun cruce de festivo se salte
        caso(grupo, "ventana_retracto", fecha_entrega=texto)
        caso(grupo, "ventana_retracto", fecha_entrega=texto, sabado_habil=True)
        dia += timedelta(days=1)
    for inicio, dias in (
        ("2026-04-02", 0),
        ("2026-04-02", 1),
        ("2026-04-02", 5),
        ("2026-04-02", -1),
        ("2026-12-24", 5),
        ("2026-12-31", 5),
        ("2026-09-05", 5),
        ("2025-12-30", 20),
    ):
        caso(grupo, "sumar_dias_habiles", inicio=inicio, dias=dias)
        caso(grupo, "sumar_dias_habiles", inicio=inicio, dias=dias, sabado_habil=True)
    for inicio, fin in (
        ("2026-04-01", "2026-04-10"),
        ("2026-04-10", "2026-04-01"),
        ("2026-04-01", "2026-04-01"),
        ("2026-09-01", "2026-09-08"),
        ("2026-12-24", "2027-01-04"),
    ):
        caso(grupo, "dias_habiles_entre", inicio=inicio, fin=fin)
        caso(grupo, "dias_habiles_entre", inicio=inicio, fin=fin, sabado_habil=True)
    modalidades = [m.value for m in retracto.Modalidad]
    exclusiones = [
        None,
        ["perecedero"],
        ["personalizado", "perecedero"],
        sorted(retracto.CATEGORIAS_SIN_RETRACTO),
        ["porque si"],
        ["me_arrepenti"],
    ]
    for modalidad in [*modalidades, "telepatia", "MOSTRADOR"]:
        for exc in exclusiones:
            caso(grupo, "aplica_retracto", modalidad=modalidad, exclusiones=exc)
    # las ventanas concretas que el Python afirma
    for entrega in (
        "2026-04-01",
        "2026-04-02",
        "2026-09-01",
        "2026-09-05",
        "2026-12-24",
        "2026-12-31",
        "2027-04-01",
    ):
        for modalidad in modalidades:
            caso(grupo, "ventana_retracto", fecha_entrega=entrega, modalidad=modalidad)
        for exc in (["perecedero"], ["servicio_iniciado", "perecedero"]):
            caso(grupo, "ventana_retracto", fecha_entrega=entrega, exclusiones=exc)
        for hoy in ("2026-09-02", "2026-09-08", "2026-09-09", "2026-09-30", "2027-01-04"):
            caso(grupo, "ventana_retracto", fecha_entrega=entrega, hoy=hoy)


# --- IVA (tests/unit/test_impuesto.py) ------------------------------------- #

DESTINOS_CLAVE = (None, "05001", "88001", "88564", "91001", "91540", "94001", "97001", "99001")


def _casos_impuesto() -> None:
    grupo = "impuesto"
    regimenes = [r.value for r in impuesto.Regimen]
    # una linea de cada regimen contra cada destino clave y los dos regimenes
    # del vendedor: la matriz completa de las dos causales que apagan el IVA
    for regimen in regimenes:
        for destino in DESTINOS_CLAVE:
            for responsable in (True, False):
                caso(
                    grupo,
                    "liquidar_linea",
                    linea={
                        "descripcion": "Prueba",
                        "regimen": regimen,
                        "precio": 10_000_00,
                        "cantidad": 1,
                    },
                    destino=destino,
                    responsable_iva=responsable,
                )
    # redondeo sobre importes que no dividen exacto
    for precio in (
        1,
        3,
        7,
        50,
        150,
        333,
        999,
        1_00,
        3_333_33,
        7_900_00,
        9_150_00,
        8_475_00,
        4_550_00,
        14_800_00,
        2_777_77,
    ):
        for regimen in regimenes:
            for cantidad in (1, 3, 7):
                caso(
                    grupo,
                    "liquidar_linea",
                    linea={
                        "descripcion": "Redondeo",
                        "regimen": regimen,
                        "precio": precio,
                        "cantidad": cantidad,
                    },
                )
    # descuentos
    for descuento in (0, 1, 5_000_00, 20_000_00):
        caso(
            grupo,
            "liquidar_linea",
            linea={
                "descripcion": "Jabon",
                "regimen": "gravado_19",
                "precio": 10_000_00,
                "cantidad": 2,
                "descuento": descuento,
            },
        )
    # lineas imposibles
    for precio, cantidad, descuento in (
        (10_000_00, 0, 0),
        (10_000_00, -1, 0),
        (-1, 1, 0),
        (10_000_00, 1, -1),
        (10_000_00, 1, 10_000_01),
    ):
        caso(
            grupo,
            "linea_venta",
            descripcion="Prueba",
            regimen="gravado_19",
            precio=precio,
            cantidad=cantidad,
            descuento=descuento,
        )
    # carritos completos
    mezclas: list[Sequence[JsonObject]] = [
        [],
        [
            {"descripcion": "Leche", "regimen": "exento", "precio": 4_300_00},
            {"descripcion": "Platano", "regimen": "excluido", "precio": 2_800_00},
        ],
        [
            {"descripcion": "Jabon", "regimen": "gravado_19", "precio": 7_900_00, "cantidad": 3},
            {"descripcion": "Cafe", "regimen": "gravado_5", "precio": 14_200_00, "cantidad": 2},
            {"descripcion": "Leche", "regimen": "exento", "precio": 4_300_00, "cantidad": 5},
            {"descripcion": "Papa", "regimen": "excluido", "precio": 2_200_00, "cantidad": 7},
            {"descripcion": "Corrientazo", "regimen": "inc_8", "precio": 14_800_00},
        ],
        [
            {"descripcion": "Jabon", "regimen": "gravado_19", "precio": 10_000_00},
            {"descripcion": "Detergente", "regimen": "gravado_19", "precio": 10_000_00},
            {"descripcion": "Cafe", "regimen": "gravado_5", "precio": 10_000_00},
            {"descripcion": "Corrientazo", "regimen": "inc_8", "precio": 10_000_00},
        ],
        [
            {"descripcion": "Leche", "regimen": "exento", "precio": 10_000_00},
            {"descripcion": "Jabon", "regimen": "gravado_19", "precio": 10_000_00},
            {"descripcion": "Papa", "regimen": "excluido", "precio": 30_000_00},
        ],
    ]
    for lineas in mezclas:
        for destino in DESTINOS_CLAVE:
            caso(grupo, "liquidar", lineas=lineas, destino=destino)
        caso(grupo, "liquidar", lineas=lineas, responsable_iva=False)


# --- flete y contraentrega (tests/unit/test_envio.py) ---------------------- #


def _casos_envio() -> None:
    grupo = "envio"
    codigos = list(envio.CIUDADES)
    nombres = [c.nombre for c in envio.CIUDADES.values()]
    consultas = [
        "05001",
        "5001",
        "Medellin",
        "medellin",
        "MEDELLÍN",
        "Bogota D.C.",
        "Ibagué",
        "San Andres",
        "Valledup",
        "Springfield",
        "Antioquia",
        "  Cali  ",
        "Narnia",
        "quibdo",
        "QUIBDÓ",
        "puerto",
        "",
    ]
    for consulta in [*codigos, *nombres, *consultas]:
        caso(grupo, "resolver_ciudad", consulta=consulta)
    for texto in ["Antioquia", "   ", "an", "puerto", "san", "valle", "Amazonas", "z"]:
        caso(grupo, "buscar_ciudades", texto=texto)
    # el veredicto de contraentrega para TODOS los destinos del maestro
    for codigo in codigos:
        caso(grupo, "diagnostico_contraentrega", destino=codigo)
        caso(grupo, "tope_contraentrega", destino=codigo)
    caso(grupo, "diagnostico_contraentrega", destino="Leticia")
    caso(grupo, "tope_contraentrega", destino="Pasto")
    # pesos y volumenes
    for peso, largo, ancho, alto, valor in (
        (2400, 30, 20, 15, 0),
        (800, 60, 40, 40, 0),
        (50, 10, 10, 1, 0),
        (1000, 10, 10, 10, 0),
        (1001, 10, 10, 10, 0),
        (5000, 10, 10, 10, 0),
        (5001, 10, 10, 10, 0),
        (1000, 20, 20, 15, 10_000_00),
        (1000, 20, 20, 15, 5_000_000_00),
        (0, 20, 20, 10, 0),
        (-5, 20, 20, 10, 0),
        (100, 20, 20, 0, 0),
        (100, 20, 20, 10, -1),
        (999, 13, 17, 19, 0),
        (3000, 33, 21, 11, 300_000_00),
    ):
        caso(grupo, "paquete", peso=peso, largo=largo, ancho=ancho, alto=alto, valor=valor)
    # la cotizacion completa para cada destino del maestro
    paquetes = (
        {"peso": 2400, "largo": 30, "ancho": 20, "alto": 15, "valor": 0},
        {"peso": 1000, "largo": 10, "ancho": 10, "alto": 10, "valor": 10_000_00},
        {"peso": 5001, "largo": 10, "ancho": 10, "alto": 10, "valor": 5_000_000_00},
    )
    for codigo in codigos:
        for p in paquetes:
            caso(grupo, "cotizar", destino=codigo, **p)
            caso(grupo, "mejor_cotizacion", destino=codigo, **p)
        for monto in (20_000_00, 50_000_00, 500_000_00, 1_800_000_00, 3_000_000_00):
            caso(
                grupo,
                "cotizar",
                destino=codigo,
                **paquetes[0],
                contraentrega=True,
                monto=monto,
            )
    caso(grupo, "cotizar", destino="Narnia", peso=1000)


# --- rieles de pago (tests/unit/test_pago.py) ------------------------------ #


def _casos_pago() -> None:
    grupo = "pago"
    tope = pago.PARAMETROS_VIGENTES.tope_deposito_bajo_monto_centavos
    for monto in (0, 1, 100, 1_000_00, 1_000_000_00, 2_000_000_01, 999_99):
        caso(grupo, "gmf", monto=monto)
    contextos: list[JsonObject] = []
    for ciudad in ("05001", "52001", "91001", "88001", "27001", "99001", "76001"):
        for total in (
            1_000_00,
            1_500_00,
            2_000_00,
            100_000_00,
            tope,
            tope + 1,
            2_000_000_00,
            2_000_000_01,
            11_388_000_00,
        ):
            contextos.append({"total": total, "ciudad": ciudad})
    bancos = (None, "Bancolombia", "DAVIVIENDA", "  Banco de Bogota ", "Nequi", "Banco Imaginario")
    for banco in bancos:
        contextos.append({"total": 100_000_00, "ciudad": "05001", "banco_pse": banco})
    for base in (0, 84_000_00, 100_000_00):
        contextos.append({"total": 100_000_00, "ciudad": "05001", "base_sin_impuestos": base})
    for recaudo in (0, 6_000_00, 6_037_00, 60_000_00):
        contextos.append({"total": 100_000_00, "ciudad": "52001", "comision_recaudo": recaudo})
    contextos.append({"total": 100_000_00, "ciudad": "05001", "contiene_servicios": True})
    contextos.append({"total": 100_000_00, "ciudad": "05001", "cliente_tiene_bancolombia": True})
    contextos.append(
        {
            "total": 100_000_00,
            "ciudad": "05001",
            "base_sin_impuestos": 84_000_00,
            "comision_recaudo": 6_000_00,
            "banco_pse": "Bancolombia",
            "cliente_tiene_bancolombia": True,
        }
    )
    for c in contextos:
        caso(grupo, "evaluar", **c)
        caso(grupo, "recomendar", **c)


# --- catalogo (tests/unit/test_catalogo.py) -------------------------------- #


def _casos_catalogo() -> None:
    grupo = "catalogo"
    skus = list(catalogo.CATALOGO)
    for sku in [*skus, " ase-jab-x3 ", "XXX-000", "", "ase-jab-x3"]:
        caso(grupo, "obtener", sku=sku)
    for sku in skus:
        for destino in (None, "05001", "88001", "91001", "99001"):
            for responsable in (True, False):
                for redondear in (True, False):
                    caso(
                        grupo,
                        "precio_al_publico",
                        sku=sku,
                        destino=destino,
                        responsable_iva=responsable,
                        redondear=redondear,
                    )
    for texto in ("cafe", "CAFÉ", "platano", "Salchichon", "fruver", "  ", "a", "aseo", "z"):
        caso(grupo, "buscar_catalogo", texto=texto)
    for categoria in [c.value for c in catalogo.Categoria]:
        caso(grupo, "por_categoria", categoria=categoria)
    carritos: tuple[Sequence[JsonObject], ...] = (
        [{"sku": "FRU-PLA-LB", "cantidad": 2}, {"sku": "LAC-LEC-1L", "cantidad": 3}],
        [{"sku": "PRE-ALM-COR"}, {"sku": "ASE-JAB-X3"}],
        [{"sku": "ASE-JAB-X3", "cantidad": 2}],
        [{"sku": "BEB-GAS-15"}],
        [{"sku": "ASE-PAP-X4", "cantidad": 2}, {"sku": "LAC-LEC-1L"}],
        [{"sku": "PRE-ALM-COR", "cantidad": 2}],
        [{"sku": "ASE-JAB-X3", "cantidad": 1}, {"sku": "PRE-ALM-COR", "cantidad": 2}],
        [{"sku": "MAS-CON-2K", "cantidad": 500}],
        [{"sku": "FRU-PLA-LB", "cantidad": 0}],
        [{"sku": "NO-EXISTE"}],
        [],
    )
    for items in carritos:
        caso(grupo, "carrito", items=items)
        caso(grupo, "carrito", items=items, valor_declarado=25_000_00)


# --- las seis herramientas, de punta a punta ------------------------------- #

ASEO: list[JsonObject] = [{"sku": "ASE-JAB-X3", "cantidad": 2}]
MERCADO: list[JsonObject] = [
    {"sku": "FRU-PLA-LB", "cantidad": 2},
    {"sku": "LAC-LEC-1L", "cantidad": 3},
    {"sku": "CAF-TOS-250", "cantidad": 1},
    {"sku": "ASE-JAB-X3", "cantidad": 1},
    {"sku": "PRE-ALM-COR", "cantidad": 1},
]
GRANDE: list[JsonObject] = [{"sku": "MAS-CON-2K", "cantidad": 500}]


def _casos_herramientas() -> None:
    grupo = "herramientas"
    caso(grupo, "contexto")
    caso(grupo, "salud")
    caso(grupo, "tablas")
    caso(grupo, "version")

    # 1. buscar_productos
    payloads_buscar: tuple[JsonObject, ...] = (
        {},
        {"consulta": "cafe"},
        {"consulta": "CAFÉ"},
        {"consulta": "leche"},
        {"categoria": "aseo", "consulta": "cafe"},
        {"categoria": "comida_preparada"},
        {"categoria": "no_existe"},
        {"limite": 5000},
        {"limite": 0},
        {"limite": 3},
        {"consulta": "cafe tostado", "destino": "05001"},
        {"consulta": "cafe tostado", "destino": "Leticia"},
        {"destino": "88001"},
        {"destino": "99001"},
        {"destino": "Narnia"},
        {"consulta": "zzz"},
    )
    for payload_buscar in payloads_buscar:
        caso(grupo, "herramienta", nombre="buscar_productos", payload=payload_buscar)

    # 2. cotizar_envio
    for destino in [*envio.CIUDADES, "Pasto", "Narnia", "Bucaramanga"]:
        caso(
            grupo,
            "herramienta",
            nombre="cotizar_envio",
            payload={"destino": destino, "items": ASEO},
        )
        caso(
            grupo,
            "herramienta",
            nombre="cotizar_envio",
            payload={"destino": destino, "items": ASEO, "contraentrega": True},
        )
    payloads_cotizar: tuple[JsonObject, ...] = (
        {"destino": "Pasto", "items": ASEO, "declarar_valor": False},
        {"destino": "05001", "items": [{"sku": "PRE-ALM-COR"}]},
        {"destino": "05001", "items": [{"sku": "NO-EXISTE"}]},
        {"destino": "05001", "items": []},
        {"destino": "05001", "items": MERCADO},
        {"destino": "91001", "items": MERCADO, "contraentrega": True},
        {"destino": "Cali", "items": GRANDE, "contraentrega": True},
    )
    for payload_cotizar in payloads_cotizar:
        caso(grupo, "herramienta", nombre="cotizar_envio", payload=payload_cotizar)

    # 3. validar_documento_dian
    for tipo, numero in (
        *[("NIT", b) for b, _dv, _e in NITS_REALES],
        *[("NIT", f"{b}-{dv}") for b, dv, _e in NITS_REALES],
        ("NIT", "890.903.938-8"),
        ("NIT", "890903938-1"),
        ("DNI", "1234567"),
        ("CC", "1.017.234.567"),
        ("CC", "123"),
        ("CE", "123456"),
        ("TI", "1012345678"),
        ("PA", "ab-123456"),
        ("PEP", "123456789012345"),
        ("NIT", "43256789"),
        ("nit", " 890 903 938 "),
        ("CC", ""),
    ):
        caso(
            grupo,
            "herramienta",
            nombre="validar_documento_dian",
            payload={"tipo": tipo, "numero": numero},
        )

    # 4. calcular_total_con_iva
    canastas: tuple[Sequence[JsonObject], ...] = (
        ASEO,
        MERCADO,
        [{"sku": "BEB-GAS-15"}],
        [{"sku": "LAC-LEC-1L"}, {"sku": "FRU-PLA-LB"}],
    )
    for items in canastas:
        for destino_opcional in (None, "05001", "88001", "91001", "99001"):
            caso(
                grupo,
                "herramienta",
                nombre="calcular_total_con_iva",
                payload={"items": items, "destino": destino_opcional},
            )
        caso(
            grupo,
            "herramienta",
            nombre="calcular_total_con_iva",
            payload={"items": items, "responsable_iva": False},
        )
    payloads_iva: tuple[JsonObject, ...] = (
        {"items": [{"sku": "ASE-JAB-X3", "cantidad": 0}]},
        {"items": [{"sku": "NO-EXISTE"}]},
        {"items": []},
        {"items": ASEO, "destino": "Narnia"},
    )
    for payload_iva in payloads_iva:
        caso(grupo, "herramienta", nombre="calcular_total_con_iva", payload=payload_iva)

    _casos_herramientas_retracto_y_pago()


def _casos_herramientas_retracto_y_pago() -> None:
    """Segunda mitad de la superficie: retracto y rieles de pago."""
    grupo = "herramientas"
    # 5. consultar_derecho_retracto
    entregas = ("2026-04-02", "2026-04-01", "2026-09-01", "2026-09-05", "2026-12-24", "2027-03-25")
    for entrega in entregas:
        for modalidad in [m.value for m in retracto.Modalidad]:
            caso(
                grupo,
                "herramienta",
                nombre="consultar_derecho_retracto",
                payload={"fecha_entrega": entrega, "modalidad": modalidad},
            )
        caso(
            grupo,
            "herramienta",
            nombre="consultar_derecho_retracto",
            payload={"fecha_entrega": entrega, "modalidad": "domicilio", "hoy": "2026-09-03"},
        )
        caso(
            grupo,
            "herramienta",
            nombre="consultar_derecho_retracto",
            payload={
                "fecha_entrega": entrega,
                "modalidad": "domicilio",
                "items": [{"sku": "PAN-ARE-X5"}],
            },
        )
    payloads_retracto: tuple[JsonObject, ...] = (
        {"fecha_entrega": "2026-09-01", "modalidad": "telepatia"},
        {"fecha_entrega": "2026-09-01", "modalidad": "MOSTRADOR"},
        {"fecha_entrega": "2026-09-01", "modalidad": "  Domicilio  "},
        {"fecha_entrega": "2026-09-01", "modalidad": "WHATSAPP"},
        {"fecha_entrega": "2026-09-01", "modalidad": ""},
        {"fecha_entrega": "2026-09-01", "exclusiones": ["me_arrepenti"]},
        {"fecha_entrega": "2026-09-01", "exclusiones": ["perecedero"]},
        {"fecha_entrega": "2026-09-01", "items": [{"sku": "PRE-ALM-COR"}]},
        {"fecha_entrega": "2026-09-01", "items": [{"sku": "NO-EXISTE"}]},
        {"fecha_entrega": "2026-04-02", "modalidad": "whatsapp", "hoy": "2026-04-10"},
        {"fecha_entrega": "2026-04-02", "modalidad": "whatsapp", "hoy": "2026-04-11"},
    )
    for payload_retracto in payloads_retracto:
        caso(grupo, "herramienta", nombre="consultar_derecho_retracto", payload=payload_retracto)
    # una entrega por semana durante dos anos: cruces de festivo exhaustivos
    dia = date(2026, 1, 1)
    while dia <= date(2027, 12, 31):
        caso(
            grupo,
            "herramienta",
            nombre="consultar_derecho_retracto",
            payload={"fecha_entrega": dia.isoformat(), "modalidad": "domicilio"},
        )
        dia += timedelta(days=7)

    # 6. metodos_de_pago
    canastas_pago: tuple[Sequence[JsonObject], ...] = (
        ASEO,
        MERCADO,
        GRANDE,
        [{"sku": "PRE-ALM-COR"}],
    )
    for destino in ("05001", "Cali", "Pasto", "Mitu", "Leticia", "88001", "99001", "27001"):
        for items in canastas_pago:
            caso(
                grupo,
                "herramienta",
                nombre="metodos_de_pago",
                payload={"items": items, "destino": destino},
            )
        caso(
            grupo,
            "herramienta",
            nombre="metodos_de_pago",
            payload={"items": ASEO, "destino": destino, "incluir_flete": False},
        )
        caso(
            grupo,
            "herramienta",
            nombre="metodos_de_pago",
            payload={"items": ASEO, "destino": destino, "banco_pse": "Bancolombia"},
        )
        caso(
            grupo,
            "herramienta",
            nombre="metodos_de_pago",
            payload={"items": ASEO, "destino": destino, "cliente_tiene_bancolombia": True},
        )
    payloads_pago: tuple[JsonObject, ...] = (
        {"items": [], "destino": "Cali"},
        {"items": ASEO, "destino": "Narnia"},
        {"items": [{"sku": "NO-EXISTE"}], "destino": "Cali"},
        {"items": ASEO, "destino": "Cali", "banco_pse": "Banco Imaginario"},
    )
    for payload_pago in payloads_pago:
        caso(grupo, "herramienta", nombre="metodos_de_pago", payload=payload_pago)


def _casos_escala() -> None:
    """Pedidos absurdamente grandes: hasta donde el entero de JavaScript es exacto.

    El dinero son centavos enteros y IEEE-754 representa exactamente todo entero
    por debajo de 2^53 (9.007.199.254.740.992 centavos, unos noventa billones de
    pesos), asi que dentro de ese rango el JavaScript no puede desviarse del
    Python, que usa enteros arbitrarios. Se comprueba en vez de suponerlo. El
    primer desacuerdo medido aparece con bases de dieciocho digitos --del orden
    de mil billones de pesos-- muy por encima de cualquier venta concebible; el
    limite esta declarado en la cabecera de dominio.js y aqui se acota.
    """
    grupo = "escala"
    for cantidad in (500, 5_000, 50_000, 500_000, 5_000_000, 50_000_000):
        caso(
            grupo,
            "herramienta",
            nombre="calcular_total_con_iva",
            payload={"items": [{"sku": "MAS-CON-2K", "cantidad": cantidad}]},
        )
        caso(
            grupo,
            "herramienta",
            nombre="metodos_de_pago",
            payload={"items": [{"sku": "MAS-CON-2K", "cantidad": cantidad}], "destino": "Cali"},
        )
    base = 999_999_999_97
    for _ in range(4):  # hasta ~1e14 centavos, dentro del rango exacto
        for num, den in ((19, 100), (5, 100), (8, 100), (4, 1000), (15, 1000)):
            caso(grupo, "aplicar_tarifa", base=base, num=num, den=den)
        caso(grupo, "redondear_efectivo", monto=base)
        caso(grupo, "formatear_cop", monto=base)
        caso(grupo, "gmf", monto=base)
        base = base * 10 + 7


def construir_casos() -> list[Caso]:
    """El corpus completo, en el orden en que se registra."""
    if _CASOS:
        return _CASOS
    _casos_documento()
    _casos_dinero()
    _casos_retracto()
    _casos_impuesto()
    _casos_envio()
    _casos_pago()
    _casos_catalogo()
    _casos_herramientas()
    _casos_escala()
    return _CASOS


# --------------------------------------------------------------------------- #
# Ejecucion y comparacion
# --------------------------------------------------------------------------- #


def ejecutar_python(casos: list[Caso]) -> dict[str, Resultado]:
    """Resultado de referencia: el Python es la especificacion."""
    salida: dict[str, Resultado] = {}
    for c in casos:
        try:
            salida[c.id] = {"valor": OPS[c.op](c.args)}
        except _ErrorDeDominioTraducidoError as exc:
            salida[c.id] = {"error": {"clase": exc.clase, "mensaje": str(exc)}}
        except Exception as exc:  # el error tambien es contrato: se compara, no se traga
            clase = type(exc).__name__ if isinstance(exc, DominioError) else "Error"
            salida[c.id] = {"error": {"clase": clase, "mensaje": str(exc)}}
    return salida


def ejecutar_node(
    casos: list[Caso], modulo: str | None = None, zona: str | None = None
) -> dict[str, Json]:
    """Un solo proceso node para todos los casos: por caso costaria minutos."""
    entrada = json.dumps(
        {"casos": [{"id": c.id, "op": c.op, "args": c.args} for c in casos]},
        ensure_ascii=False,
    )
    entorno = {**os.environ}
    if modulo is not None:
        entorno["DOMINIO_JS"] = modulo
    if zona is not None:
        entorno["TZ"] = zona
    if NODE is None:
        msg = "no hay 'node' en el PATH: el lado JavaScript no se puede ejecutar"
        raise RuntimeError(msg)
    proceso = subprocess.run(
        [NODE, str(RUNNER)],
        input=entrada.encode("utf-8"),
        capture_output=True,
        check=False,
        cwd=str(RAIZ),
        env=entorno,
    )
    if proceso.returncode != 0:
        detalle = proceso.stderr.decode("utf-8", "replace")[-4000:]
        msg = f"node fallo con codigo {proceso.returncode}:\n{detalle}"
        raise RuntimeError(msg)
    salida = _obj(json.loads(proceso.stdout.decode("utf-8")))
    return dict(_obj(salida["resultados"]))


def _normalizar(valor: object) -> object:
    """Lleva los dos lados a una forma comparable sin perder informacion.

    Solo se colapsa lo que JSON no distingue y el dominio tampoco: una tupla
    de Python y un array de JavaScript son el mismo dato. Los numeros no se
    tocan: el dinero son centavos enteros y una diferencia de un centavo tiene
    que salir como divergencia.
    """
    if isinstance(valor, tuple):
        return [_normalizar(x) for x in valor]
    if isinstance(valor, list):
        return [_normalizar(x) for x in valor]
    if isinstance(valor, dict):
        return {k: _normalizar(v) for k, v in valor.items()}
    if isinstance(valor, Decimal):
        return str(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return valor


def _diferencias(esperado: object, obtenido: object, ruta: str = "") -> list[str]:
    """Enumera las rutas concretas donde los dos valores no coinciden."""
    if isinstance(esperado, dict) and isinstance(obtenido, dict):
        fallos = []
        for clave in sorted(set(esperado) | set(obtenido)):
            if clave not in esperado:
                fallos.append(f"{ruta}.{clave}: sobra en JS = {obtenido[clave]!r}")
            elif clave not in obtenido:
                fallos.append(f"{ruta}.{clave}: falta en JS (Python = {esperado[clave]!r})")
            else:
                fallos.extend(_diferencias(esperado[clave], obtenido[clave], f"{ruta}.{clave}"))
        return fallos
    if isinstance(esperado, list) and isinstance(obtenido, list):
        if len(esperado) != len(obtenido):
            return [f"{ruta}: longitud Python={len(esperado)} JS={len(obtenido)}"]
        fallos = []
        for i, (a, b) in enumerate(zip(esperado, obtenido, strict=True)):
            fallos.extend(_diferencias(a, b, f"{ruta}[{i}]"))
        return fallos
    if esperado != obtenido:
        return [f"{ruta or '<valor>'}: Python={esperado!r} JS={obtenido!r}"]
    return []


@dataclass(frozen=True, slots=True)
class Divergencia:
    """Un caso donde el JavaScript no responde lo que responde el Python."""

    caso: Caso
    detalles: list[str]
    python: object
    js: object
    zona: str = "UTC"


@dataclass(frozen=True, slots=True)
class Comparacion:
    """Corpus, divergencias y las dos respuestas crudas, para poder exhibirlas."""

    casos: list[Caso]
    divergencias: list[Divergencia]
    python: dict[str, Resultado]
    js: dict[str, Json]

    def respuesta(self, op: str, **args: Json) -> tuple[Resultado, Resultado]:
        """Las dos respuestas a un caso concreto del corpus, Python y JavaScript."""
        firma = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        ident = f"{op}:{firma}"
        if ident not in self.python:
            msg = f"ese caso no esta en el corpus: {ident}"
            raise KeyError(msg)
        return self.python[ident], _obj(self.js[ident])


def comparar(modulo: str | None = None, zonas: tuple[str, ...] = ZONAS_HORARIAS) -> Comparacion:
    """Corre los dos lados y devuelve el corpus y las divergencias encontradas.

    El lado Python se calcula una sola vez --``datetime.date`` es naive y no
    depende del reloj-- y el lado JavaScript se recorre entero contra cada zona
    horaria de :data:`ZONAS_HORARIAS`.
    """
    casos = construir_casos()
    esperados = ejecutar_python(casos)
    divergencias: list[Divergencia] = []
    obtenidos: dict[str, Json] = {}
    for zona in zonas:
        obtenidos = ejecutar_node(casos, modulo, zona)
        for c in casos:
            py = _normalizar(esperados[c.id])
            crudo = obtenidos.get(c.id)
            if crudo is None:
                divergencias.append(
                    Divergencia(c, ["el runner de node no devolvio el caso"], py, None, zona)
                )
                continue
            if isinstance(crudo, Mapping) and "__arnes__" in crudo:
                divergencias.append(Divergencia(c, [str(crudo["__arnes__"])], py, crudo, zona))
                continue
            js = _normalizar(crudo)
            detalles = _diferencias(py, js)
            if detalles:
                divergencias.append(Divergencia(c, detalles, py, js, zona))
    return Comparacion(casos, divergencias, esperados, obtenidos)


# --------------------------------------------------------------------------- #
# Prueba de mutacion: la garantia de que este arnes puede fallar
# --------------------------------------------------------------------------- #

MUTANTES: dict[str, tuple[str, str]] = {
    "DV: serie de primos invertida": (
        "const _SERIE_OFICIAL_DV = Object.freeze("
        "[71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]);",
        "const _SERIE_OFICIAL_DV = Object.freeze("
        "[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]);",
    ),
    "DV: el residuo 1 deja de dar cero": (
        "const _RESIDUOS_CERO = new Set([0, 1]);",
        "const _RESIDUOS_CERO = new Set([0]);",
    ),
    "Pascua: Meeus con +115 en vez de +114": (
        "const bruto = h + ele - 7 * m + 114;",
        "const bruto = h + ele - 7 * m + 115;",
    ),
    "Emiliani: ningun festivo se corre al lunes": (
        "  return sumar_dias(f, _mod(_LUNES - _dia_semana(f), 7));",
        "  return f;",
    ),
    "Emiliani: Corpus Christi a 63 dias de Pascua": (
        '[64, "Corpus Christi"]',
        '[63, "Corpus Christi"]',
    ),
    "Fechas: hora local en vez de UTC": (
        "  return new Date(Date.UTC(anio, mes - 1, dia));",
        "  return new Date(anio, mes - 1, dia);",
    ),
    "Redondeo: HALF_UP cambiado por truncamiento": (
        "return signo * Math.floor((2 * a + d) / (2 * d));",
        "return signo * Math.floor(a / d);",
    ),
    "IVA: tarifa general al 18 por ciento": (
        "export const TARIFA_IVA_GENERAL = tarifa(19, 100);",
        "export const TARIFA_IVA_GENERAL = tarifa(18, 100);",
    ),
    "Contraentrega: Leticia deja de ser solo aereo": (
        '_c("91001", "Leticia", "Amazonas", _R, { aereo: true, iva_especial: true })',
        '_c("91001", "Leticia", "Amazonas", _R, { aereo: false, iva_especial: true })',
    ),
    "Retracto: seis dias habiles en vez de cinco": (
        "export const DIAS_HABILES_RETRACTO = 5;",
        "export const DIAS_HABILES_RETRACTO = 6;",
    ),
    "Habil: el sabado pasa a contar por defecto": (
        "const tope = sabado_habil ? _SABADO + 1 : _SABADO;",
        "const tope = sabado_habil ? _SABADO + 1 : _SABADO + 1;",
    ),
    "Efectivo: redondeo a 100 pesos en vez de 50": (
        "export const MULTIPLO_EFECTIVO = 50 * CENTAVOS_POR_PESO;",
        "export const MULTIPLO_EFECTIVO = 100 * CENTAVOS_POR_PESO;",
    ),
    "Nequi: tope de nueve salarios minimos": (
        "export const SMMLV_TOPE_DEPOSITO_BAJO_MONTO = 8;",
        "export const SMMLV_TOPE_DEPOSITO_BAJO_MONTO = 9;",
    ),
    "Flete: kilos adicionales redondeados hacia abajo": (
        "const kilos = Math.ceil(peso_gramos / _GRAMOS_POR_KILO);",
        "const kilos = Math.floor(peso_gramos / _GRAMOS_POR_KILO);",
    ),
}
"""Defectos plausibles de un port, uno por regla que el proyecto existe para hacer bien.

Un arnes diferencial en verde no prueba nada si no puede ponerse en rojo: puede
estar comparando la nada. Cada uno de estos mutantes se inyecta en una COPIA de
``static/dominio.js`` --el archivo real no se toca-- y el corpus tiene que
detectarlo. El de la hora local es el que justifica el barrido de zonas: en
Bogota (UTC-5) es invisible.
"""

_ZONAS_MUTACION = ("UTC", "Pacific/Kiritimati")


def _mutantes_sobrevivientes() -> list[str]:
    """Corre cada mutante y devuelve los que el corpus NO detecta."""
    fuente = (RAIZ / "static" / "dominio.js").read_text(encoding="utf-8")
    casos = construir_casos()
    esperados = ejecutar_python(casos)
    sobrevivientes: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "mutante.js"
        for nombre, (viejo, nuevo) in MUTANTES.items():
            if viejo not in fuente:
                sobrevivientes.append(f"{nombre} (el patron ya no existe en dominio.js)")
                continue
            destino.write_text(fuente.replace(viejo, nuevo, 1), encoding="utf-8")
            detectado = False
            for zona in _ZONAS_MUTACION:
                try:
                    obtenidos = ejecutar_node(casos, str(destino), zona)
                except RuntimeError:
                    detectado = True  # el mutante ni siquiera carga
                    break
                for c in casos:
                    js = obtenidos.get(c.id)
                    if js is None or (isinstance(js, Mapping) and "__arnes__" in js):
                        detectado = True
                        break
                    if _diferencias(_normalizar(esperados[c.id]), _normalizar(js)):
                        detectado = True
                        break
                if detectado:
                    break
            if not detectado:
                sobrevivientes.append(nombre)
    return sobrevivientes


# --------------------------------------------------------------------------- #
# Interfaz pytest
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(NODE is None, reason="se necesita 'node' para ejecutar static/dominio.js")
def test_el_javascript_coincide_con_el_python() -> None:
    """Cero divergencias entre ``static/dominio.js`` y ``src/tendero/domain``."""
    resultado = comparar()
    casos, divergencias = resultado.casos, resultado.divergencias
    assert casos, "el corpus de paridad quedo vacio"
    if divergencias:
        lineas = [f"{len(divergencias)} divergencias de {len(casos)} casos comparados:"]
        for d in divergencias[:40]:
            lineas.append(
                f"\n  [TZ={d.zona}] caso: {d.caso.op} {json.dumps(d.caso.args, ensure_ascii=False)}"
            )
            lineas.extend(f"    {x}" for x in d.detalles[:8])
        raise AssertionError("\n".join(lineas))


@pytest.mark.skipif(NODE is None, reason="se necesita 'node' para ejecutar static/dominio.js")
def test_el_arnes_detecta_un_javascript_roto() -> None:
    """Cada defecto plausible inyectado en el JavaScript tiene que salir en rojo."""
    sobrevivientes = _mutantes_sobrevivientes()
    assert not sobrevivientes, (
        "el corpus no distingue estos JavaScript rotos del correcto, "
        f"asi que no cubre la regla: {sobrevivientes}"
    )


# --------------------------------------------------------------------------- #
# Informe por consola
# --------------------------------------------------------------------------- #


def _evidencia(r: Comparacion) -> None:
    """Exhibe, lado a lado, las cinco comprobaciones que un port suele fallar.

    No vuelve a calcular nada: lee las respuestas que ya se compararon, para que
    lo impreso sea exactamente lo que el arnes verifico.
    """
    ok = "coinciden"

    print("\n1. Digito de verificacion DIAN de cada NIT de la suite de Python")
    for base, dv, entidad in NITS_REALES:
        py, js = r.respuesta("calcular_dv_nit", base=base)
        marca = ok if py == js else "!!! DIVERGEN !!!"
        print(f"   {base}-{dv}  {entidad:22s} python={py['valor']} js={js['valor']}  {marca}")

    for anio in (2026, 2027):
        py, js = r.respuesta("festivos", anio=anio)
        festivos_py = _objetos(py["valor"])
        festivos_js = _objetos(js["valor"])
        print(
            f"\n2. Calendario colombiano completo de {anio} "
            f"({len(festivos_py)} festivos) — {ok if py == js else '!!! DIVERGEN !!!'}"
        )
        for f_py, f_js in zip(festivos_py, festivos_js, strict=True):
            traslado = f"  <- {f_py['fecha_original']} (Ley 51)" if f_py["trasladado"] else ""
            igual = "=" if f_py == f_js else "!"
            print(f"   {igual} {f_py['fecha']}  {_txt(f_py['nombre']):28s}{traslado}")

    print("\n3. Ventana de retracto que cruza el puente de Semana Santa")
    for entrega in ("2026-04-01", "2026-04-02", "2026-12-24"):
        py, js = r.respuesta("ventana_retracto", fecha_entrega=entrega)
        v = _obj(py["valor"])
        festivos = _objetos(v["festivos_intermedios"])
        nombres = ", ".join(_txt(f["nombre"]) for f in festivos) or "ninguno"
        marca = ok if py == js else "!!! DIVERGEN !!!"
        print(
            f"   entrega {entrega} -> inicia {v['inicio']}, vence {v['vence']} "
            f"({(date.fromisoformat(_txt(v['vence'])) - date.fromisoformat(entrega)).days} "
            f"dias de calendario para 5 habiles); festivos: {nombres}  {marca}"
        )

    print("\n4. Contra entrega: destino remoto contra area metropolitana")
    for codigo in ("05001", "11001", "52001", "91001", "97001", "88001", "99001"):
        py, js = r.respuesta("diagnostico_contraentrega", destino=codigo)
        tope_py, tope_js = r.respuesta("tope_contraentrega", destino=codigo)
        ciudad = envio.CIUDADES[codigo]
        disponible, motivo = _lista(py["valor"])
        marca = ok if (py == js and tope_py == tope_js) else "!!! DIVERGEN !!!"
        print(
            f"   {ciudad.etiqueta:36s} zona={ciudad.zona.value:14s} "
            f"contraentrega={'SI' if disponible else 'NO':2s} "
            f"tope={dinero.formatear_cop(_ent(tope_py['valor'])):>14s}  {marca}"
        )
        print(f"       motivo: {_txt(motivo)[:110]}")

    print("\n5. Redondeo del IVA sobre importes que no dividen exacto")
    for importe, num, den in (
        (50, 19, 100),
        (150, 19, 100),
        (999_99, 19, 100),
        (3_333_33, 19, 100),
        (2_777_77, 8, 100),
        (1_234_567, 5, 100),
        (84_000_00, 15, 1000),
    ):
        py, js = r.respuesta("aplicar_tarifa", base=importe, num=num, den=den)
        exacto = Decimal(importe) * Decimal(num) / Decimal(den)
        marca = ok if py == js else "!!! DIVERGEN !!!"
        print(
            f"   {importe:>10d} x {num}/{den:<5d} = {exacto!s:>14s} -> "
            f"python={_ent(py['valor']):<10d} js={_ent(js['valor']):<10d} {marca}"
        )


def main() -> int:
    """Informe legible: total comparado, divergencias y las cinco verificaciones."""
    if NODE is None:
        print("no hay 'node' en el PATH: sin el no se puede ejecutar static/dominio.js")
        return 2
    resultado = comparar()
    casos, divergencias = resultado.casos, resultado.divergencias
    por_grupo: dict[str, int] = {}
    for c in casos:
        por_grupo[c.grupo] = por_grupo.get(c.grupo, 0) + 1
    print(
        f"casos comparados: {len(casos)}  x {len(ZONAS_HORARIAS)} zonas horarias "
        f"= {len(casos) * len(ZONAS_HORARIAS)} comparaciones"
    )
    for grupo, total in sorted(por_grupo.items()):
        print(f"  {grupo:16s} {total}")
    print(f"\ndivergencias: {len(divergencias)}")
    for d in divergencias[:60]:
        print(f"\n  [TZ={d.zona}] {d.caso.op}  {json.dumps(d.caso.args, ensure_ascii=False)[:200]}")
        for detalle in d.detalles[:10]:
            print(f"    {detalle[:400]}")
    if len(divergencias) > 60:
        print(f"\n  ... y {len(divergencias) - 60} mas")
    con_valor = sum(1 for c in casos if "valor" in resultado.python[c.id])
    print(
        f"\ncasos que devuelven un valor: {con_valor}; "
        f"casos que ejercitan un error del dominio: {len(casos) - con_valor}"
    )
    print("\n" + "=" * 78)
    print("VERIFICACIONES DIRIGIDAS")
    print("=" * 78)
    _evidencia(resultado)
    return 1 if divergencias else 0


if __name__ == "__main__":
    raise SystemExit(main())

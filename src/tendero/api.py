"""HTTP delgado sobre el dominio: traduce peticiones a llamadas y respuestas a JSON.

Este modulo no decide nada. Ninguna tarifa, ningun tope, ninguna causal de
exclusion y ningun redondeo viven aqui: cada cifra que sale por la red la
calculo ``tendero.domain``. Lo unico que hace este archivo es resolver texto a
objetos del dominio, serializar el resultado y mapear cada error de negocio al
codigo HTTP que le permite al agente reintentar solo lo que fallo.

La unica aritmetica del modulo es sumar mercancia mas flete para armar el total
que se cobra, y esa suma es legitima sin volver a liquidar impuesto porque el
transporte nacional de carga esta excluido del IVA (``FLETE_EXCLUIDO_DE_IVA``).

Cada ruta ``POST /api/<nombre>`` corresponde uno a uno con una de las seis
herramientas que ``static/index.html`` registra via ``document.modelContext``.
Esa correspondencia es deliberada: quien lee el repositorio puede ver que la
herramienta del navegador y el endpoint son la misma capacidad.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from tendero import __version__
from tendero.domain import catalogo, dinero, documento, envio, impuesto, pago, retracto
from tendero.domain.errores import DominioError

__all__ = [
    "ARCHIVO_INDEX",
    "DIRECTORIO_ESTATICOS",
    "app",
    "crear_app",
]


def _resolver_estaticos() -> Path:
    """Ubicar la vitrina tanto en el repo como dentro de la imagen instalada.

    ``parents[2]`` resuelve a la raiz del repo en desarrollo, pero cuando el paquete
    queda instalado en ``site-packages`` apunta fuera de el: el servicio desplegado
    respondia HTTP 500 con ``/usr/local/lib/python3.12/static/index.html does not
    exist``. Se prueban los candidatos en orden y gana el primero que exista, de modo
    que un cambio de layout de despliegue no vuelva a romper la pagina.
    """
    if crudo := os.environ.get("TENDERO_STATIC_DIR"):
        return Path(crudo).resolve()
    aqui = Path(__file__).resolve()
    candidatos = (
        aqui.parents[2] / "static",  # repo: src/tendero/api.py -> ./static
        aqui.parent / "static",  # instalado como package data
        Path.cwd() / "static",  # WORKDIR de la imagen
    )
    for candidato in candidatos:
        if (candidato / "index.html").is_file():
            return candidato
    # Ninguno existe: se devuelve el del repo para que el error nombre la ruta
    # esperada en vez de una cadena vacia.
    return candidatos[0]


DIRECTORIO_ESTATICOS: Final = _resolver_estaticos()
"""Carpeta con la vitrina; se sirve tal cual, sin build ni empaquetador."""

ARCHIVO_INDEX: Final = DIRECTORIO_ESTATICOS / "index.html"

_CODIGO_DOMINIO: Final = 422
_LIMITE_BUSQUEDA_MAXIMO: Final = 100
_LIMITE_BUSQUEDA_POR_DEFECTO: Final = 24


# --------------------------------------------------------------------------- #
# Serializacion comun
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Monto:
    """Dinero en la unica forma en que el dominio lo maneja, mas su texto.

    Se envian las dos: el entero para que el agente pueda comparar y sumar, y el
    texto ya formateado en la convencion colombiana para que la pagina lo pinte
    sin reimplementar el formateo en JavaScript.
    """

    centavos: int
    texto: str


def _monto(valor: int) -> Monto:
    """Empaqueta un entero de centavos del dominio."""
    return Monto(centavos=valor, texto=dinero.formatear_cop(valor))


def _pct(tarifa: Decimal) -> str:
    """Tarifa como la imprime una factura colombiana: coma decimal."""
    return f"{tarifa * 100:.2f}".replace(".", ",") + " %"


@dataclass(frozen=True, slots=True)
class CiudadDTO:
    """Municipio DANE con los dos atributos que cambian la venta."""

    codigo_dane: str
    nombre: str
    departamento: str
    etiqueta: str
    zona: str
    solo_aereo: bool
    regimen_iva_especial: bool


def _ciudad_dto(ciudad: envio.Ciudad) -> CiudadDTO:
    """Serializa una ciudad del dominio."""
    return CiudadDTO(
        codigo_dane=ciudad.codigo_dane,
        nombre=ciudad.nombre,
        departamento=ciudad.departamento,
        etiqueta=ciudad.etiqueta,
        zona=ciudad.zona.value,
        solo_aereo=ciudad.solo_aereo,
        regimen_iva_especial=ciudad.regimen_iva_especial,
    )


@dataclass(frozen=True, slots=True)
class ItemPeticion:
    """Una referencia del carrito tal como la manda la pagina o el agente."""

    sku: str
    cantidad: int = 1


def _carrito(items: Sequence[ItemPeticion]) -> catalogo.Carrito:
    """Arma el carrito del dominio; los SKU malos los rechaza el dominio."""
    return catalogo.armar_carrito((item.sku, item.cantidad) for item in items)


def _ciudad(consulta: str | None) -> envio.Ciudad | None:
    """Resuelve un destino opcional escrito por una persona o por un agente."""
    if consulta is None or not consulta.strip():
        return None
    return envio.resolver_ciudad(consulta)


# --------------------------------------------------------------------------- #
# Contexto de arranque
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TipoDocumentoDTO:
    """Tipo de identificacion admitido, con su codigo del anexo DIAN."""

    tipo: str
    codigo_dian: str
    nombre: str
    largo_minimo: int
    largo_maximo: int
    solo_digitos: bool
    requiere_dv: bool


@dataclass(frozen=True, slots=True)
class ProductoDTO:
    """Referencia del catalogo con su tratamiento tributario explicito."""

    sku: str
    nombre: str
    categoria: str
    regimen: str
    tributo: str | None
    tarifa: str
    fundamento: str
    explicacion: str
    precio_base: Monto
    precio_publico: Monto
    peso_gramos: int
    es_servicio: bool
    exclusiones_retracto: list[str]
    impuesto_saludable_incorporado: bool


def _producto_dto(producto: catalogo.Producto, destino: envio.Ciudad | None) -> ProductoDTO:
    """Serializa una referencia con el precio que le toca a ese destino."""
    tratamiento = impuesto.TRATAMIENTOS[producto.regimen]
    return ProductoDTO(
        sku=producto.sku,
        nombre=producto.nombre,
        categoria=producto.categoria.value,
        regimen=producto.regimen.value,
        tributo=tratamiento.tributo,
        tarifa=_pct(tratamiento.tarifa),
        fundamento=producto.fundamento,
        explicacion=tratamiento.explicacion,
        precio_base=_monto(producto.precio_base_centavos),
        precio_publico=_monto(catalogo.precio_al_publico(producto, destino=destino)),
        peso_gramos=producto.peso_gramos,
        es_servicio=producto.es_servicio,
        exclusiones_retracto=sorted(producto.exclusiones_retracto),
        impuesto_saludable_incorporado=producto.impuesto_saludable_incorporado,
    )


@dataclass(frozen=True, slots=True)
class ComercioDTO:
    """Encabezado del vendedor, como va en la factura electronica."""

    nombre: str
    documento: str
    codigo_dian: str
    direccion: str
    ciudad: str
    responsable_iva: bool
    correo: str


@dataclass(frozen=True, slots=True)
class ContextoRespuesta:
    """Todo lo que la vitrina necesita para pintarse en una sola peticion."""

    comercio: ComercioDTO
    categorias: list[str]
    ciudades: list[CiudadDTO]
    tipos_documento: list[TipoDocumentoDTO]
    modalidades_venta: list[str]
    exclusiones_retracto: list[str]
    metodos_pago: list[str]
    nota_flete: str
    nota_impuestos_saludables: str


@dataclass(frozen=True, slots=True)
class SaludRespuesta:
    """Latido del servicio, con el tamano de los maestros que sirve."""

    estado: str
    version: str
    productos: int
    ciudades: int
    transportadoras: int
    sin_contraentrega: int


# --------------------------------------------------------------------------- #
# 1. buscar_productos
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BusquedaPeticion:
    """Consulta al catalogo, opcionalmente valorada contra un destino."""

    consulta: str = ""
    categoria: str | None = None
    destino: str | None = None
    limite: int = _LIMITE_BUSQUEDA_POR_DEFECTO


@dataclass(frozen=True, slots=True)
class BusquedaRespuesta:
    """Resultado del catalogo con el destino que fijo los precios."""

    consulta: str
    destino: CiudadDTO | None
    total: int
    productos: list[ProductoDTO]
    nota: str


# --------------------------------------------------------------------------- #
# 2. cotizar_envio
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EnvioPeticion:
    """Pedido a despachar hacia un destino concreto."""

    destino: str
    items: list[ItemPeticion] = field(default_factory=list)
    contraentrega: bool = False
    declarar_valor: bool = True


@dataclass(frozen=True, slots=True)
class OpcionEnvioDTO:
    """Una transportadora concreta, con el costo ya desglosado."""

    transportadora: str
    codigo_transportadora: str
    flete: Monto
    recargo_aereo: Monto
    manejo: Monto
    recaudo: Monto
    total: Monto
    dias_habiles_minimo: int
    dias_habiles_maximo: int
    contraentrega: bool
    notas: list[str]


def _opcion_dto(cotizacion: envio.Cotizacion) -> OpcionEnvioDTO:
    """Serializa una cotizacion del dominio."""
    return OpcionEnvioDTO(
        transportadora=cotizacion.transportadora,
        codigo_transportadora=cotizacion.codigo_transportadora,
        flete=_monto(cotizacion.flete_centavos),
        recargo_aereo=_monto(cotizacion.recargo_aereo_centavos),
        manejo=_monto(cotizacion.manejo_centavos),
        recaudo=_monto(cotizacion.recaudo_centavos),
        total=_monto(cotizacion.total_centavos),
        dias_habiles_minimo=cotizacion.dias_habiles_minimo,
        dias_habiles_maximo=cotizacion.dias_habiles_maximo,
        contraentrega=cotizacion.contraentrega,
        notas=list(cotizacion.notas),
    )


@dataclass(frozen=True, slots=True)
class EnvioRespuesta:
    """Cotizacion completa, incluido el veredicto sobre el contra entrega."""

    destino: CiudadDTO
    despachable: bool
    peso_facturable_gramos: int
    valor_declarado: Monto
    contraentrega_disponible: bool
    contraentrega_motivo: str
    tope_contraentrega: Monto
    opciones: list[OpcionEnvioDTO]
    mejor: OpcionEnvioDTO | None
    nota: str


# --------------------------------------------------------------------------- #
# 3. validar_documento_dian
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DocumentoPeticion:
    """Identificacion del comprador tal como la dicta."""

    tipo: str
    numero: str


@dataclass(frozen=True, slots=True)
class DocumentoRespuesta:
    """Veredicto DIAN sobre una identificacion, valido o no."""

    valido: bool
    tipo: str
    nombre_tipo: str | None
    codigo_dian: str | None
    numero: str | None
    dv: int | None
    dv_calculado: bool
    formateado: str | None
    es_persona_juridica: bool
    mensaje: str


# --------------------------------------------------------------------------- #
# 4. calcular_total_con_iva
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LiquidacionPeticion:
    """Carrito a liquidar contra un destino y un regimen del vendedor."""

    items: list[ItemPeticion]
    destino: str | None = None
    responsable_iva: bool = True


@dataclass(frozen=True, slots=True)
class LineaDTO:
    """Linea de factura con el regimen que se pidio y el que quedo."""

    descripcion: str
    cantidad: int
    regimen_solicitado: str
    regimen_aplicado: str
    tributo: str | None
    tarifa: str
    bruto: Monto
    descuento: Monto
    base_gravable: Monto
    impuesto: Monto
    total: Monto
    fundamento: str
    motivo_ajuste: str | None
    da_derecho_a_descontables: bool


@dataclass(frozen=True, slots=True)
class SubtotalDTO:
    """Bloque ``TaxSubtotal`` de la representacion UBL de la DIAN."""

    tributo: str
    tarifa: str
    base: Monto
    valor: Monto


@dataclass(frozen=True, slots=True)
class DescontablesDTO:
    """Cuanto de la venta conserva el derecho a impuestos descontables."""

    base_con_derecho: Monto
    base_sin_derecho: Monto
    nota: str


@dataclass(frozen=True, slots=True)
class LiquidacionRespuesta:
    """Factura liquidada linea por linea, como la valida la DIAN."""

    destino: CiudadDTO | None
    responsable_iva: bool
    lineas: list[LineaDTO]
    subtotales: list[SubtotalDTO]
    bruto: Monto
    descuentos: Monto
    base_gravable: Monto
    iva: Monto
    inc: Monto
    total: Monto
    notas: list[str]
    descontables: DescontablesDTO
    lleva_impuestos_saludables: bool
    nota_impuestos_saludables: str | None


def _liquidacion_dto(
    liquidacion: impuesto.Liquidacion,
    carrito: catalogo.Carrito,
    destino: envio.Ciudad | None,
    *,
    responsable_iva: bool,
) -> LiquidacionRespuesta:
    """Serializa una liquidacion del dominio con su resumen de descontables."""
    resumen = impuesto.resumen_descontables(liquidacion)
    saludables = carrito.lleva_impuestos_saludables
    return LiquidacionRespuesta(
        destino=_ciudad_dto(destino) if destino else None,
        responsable_iva=responsable_iva,
        lineas=[
            LineaDTO(
                descripcion=linea.descripcion,
                cantidad=linea.cantidad,
                regimen_solicitado=linea.regimen_solicitado.value,
                regimen_aplicado=linea.regimen_aplicado.value,
                tributo=linea.tributo,
                tarifa=_pct(linea.tarifa),
                bruto=_monto(linea.bruto_centavos),
                descuento=_monto(linea.descuento_centavos),
                base_gravable=_monto(linea.base_gravable_centavos),
                impuesto=_monto(linea.impuesto_centavos),
                total=_monto(linea.total_centavos),
                fundamento=linea.fundamento,
                motivo_ajuste=linea.motivo_ajuste,
                da_derecho_a_descontables=linea.da_derecho_a_descontables,
            )
            for linea in liquidacion.lineas
        ],
        subtotales=[
            SubtotalDTO(
                tributo=subtotal.tributo,
                tarifa=subtotal.tarifa_porcentual + " %",
                base=_monto(subtotal.base_centavos),
                valor=_monto(subtotal.valor_centavos),
            )
            for subtotal in liquidacion.subtotales
        ],
        bruto=_monto(liquidacion.bruto_centavos),
        descuentos=_monto(liquidacion.descuentos_centavos),
        base_gravable=_monto(liquidacion.base_gravable_centavos),
        iva=_monto(liquidacion.iva_centavos),
        inc=_monto(liquidacion.inc_centavos),
        total=_monto(liquidacion.total_centavos),
        notas=list(liquidacion.notas),
        descontables=DescontablesDTO(
            base_con_derecho=_monto(resumen.base_con_derecho_centavos),
            base_sin_derecho=_monto(resumen.base_sin_derecho_centavos),
            nota=resumen.nota,
        ),
        lleva_impuestos_saludables=saludables,
        nota_impuestos_saludables=impuesto.IMPUESTOS_SALUDABLES if saludables else None,
    )


# --------------------------------------------------------------------------- #
# 5. consultar_derecho_retracto
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RetractoPeticion:
    """Entrega concreta contra la que se cuenta el plazo del Art. 47."""

    fecha_entrega: date
    modalidad: str = retracto.Modalidad.DOMICILIO.value
    items: list[ItemPeticion] = field(default_factory=list)
    exclusiones: list[str] = field(default_factory=list)
    hoy: date | None = None


@dataclass(frozen=True, slots=True)
class FestivoDTO:
    """Festivo que cae dentro del plazo y por eso lo alarga."""

    fecha: date
    nombre: str
    trasladado: bool
    fecha_original: date
    fundamento: str


@dataclass(frozen=True, slots=True)
class RetractoRespuesta:
    """Ventana de retracto resuelta contra el calendario real."""

    aplica: bool
    motivo: str
    modalidad: str
    fecha_entrega: date
    inicio: date | None
    vence: date | None
    dias_habiles: int
    dias_calendario: int
    festivos_intermedios: list[FestivoDTO]
    exclusiones_detectadas: list[str]
    dias_para_devolver_dinero: int
    vigente: bool | None
    dias_habiles_restantes: int | None


# --------------------------------------------------------------------------- #
# 6. metodos_de_pago
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PagoPeticion:
    """Pedido evaluado contra los cinco rieles de pago del comercio."""

    items: list[ItemPeticion]
    destino: str
    banco_pse: str | None = None
    cliente_tiene_bancolombia: bool = False
    incluir_flete: bool = True


@dataclass(frozen=True, slots=True)
class MetodoPagoDTO:
    """Veredicto sobre un riel, con lo que le queda al comercio."""

    metodo: str
    nombre: str
    disponible: bool
    motivos: list[str]
    requisitos: list[str]
    recargo_cliente: Monto
    comision: Monto
    retencion: Monto
    gmf: Monto
    costo_total_comercio: Monto
    total_cliente: Monto
    neto_comercio: Monto
    dias_habiles_liquidacion: int
    cuotas_maximas: int
    notas: list[str]


def _metodo_dto(evaluacion: pago.EvaluacionPago) -> MetodoPagoDTO:
    """Serializa la evaluacion de un riel."""
    return MetodoPagoDTO(
        metodo=evaluacion.metodo.value,
        nombre=evaluacion.nombre,
        disponible=evaluacion.disponible,
        motivos=list(evaluacion.motivos),
        requisitos=list(evaluacion.requisitos),
        recargo_cliente=_monto(evaluacion.recargo_cliente_centavos),
        comision=_monto(evaluacion.comision_centavos),
        retencion=_monto(evaluacion.retencion_centavos),
        gmf=_monto(evaluacion.gmf_centavos),
        costo_total_comercio=_monto(evaluacion.costo_total_comercio_centavos),
        total_cliente=_monto(evaluacion.total_cliente_centavos),
        neto_comercio=_monto(evaluacion.neto_comercio_centavos),
        dias_habiles_liquidacion=evaluacion.dias_habiles_liquidacion,
        cuotas_maximas=evaluacion.cuotas_maximas,
        notas=list(evaluacion.notas),
    )


@dataclass(frozen=True, slots=True)
class ParametrosDTO:
    """Valores que el Gobierno reajusta por decreto cada diciembre."""

    anio: int
    uvt: Monto
    smmlv: Monto
    tope_deposito_bajo_monto: Monto
    exencion_gmf_mensual: Monto


@dataclass(frozen=True, slots=True)
class DesgloseDTO:
    """De donde sale el total que se cobra: mercancia mas flete."""

    mercancia: Monto
    flete: Monto
    total_pedido: Monto
    nota_flete: str


@dataclass(frozen=True, slots=True)
class PagoRespuesta:
    """Los cinco rieles evaluados contra este pedido y este destino."""

    destino: CiudadDTO
    desglose: DesgloseDTO
    metodos: list[MetodoPagoDTO]
    recomendado: str | None
    parametros: ParametrosDTO
    bancos_pse: list[str]


# --------------------------------------------------------------------------- #
# Aplicacion
# --------------------------------------------------------------------------- #


def _error_dominio(_peticion: Request, exc: Exception) -> Response:
    """Traduce un error de negocio a 422 con el texto que escribio el dominio.

    Se responde 422 y no 500 porque nada fallo: el agente pidio algo que las
    reglas colombianas no permiten, y el cuerpo trae el motivo redactado para
    que pueda corregir la llamada sin adivinar.
    """
    return JSONResponse(
        status_code=_CODIGO_DOMINIO,
        content={"error": str(exc), "tipo": type(exc).__name__},
    )


def crear_app() -> FastAPI:
    """Construye la aplicacion; separada del modulo para poder instanciarla en pruebas."""
    aplicacion = FastAPI(
        title="Tendero",
        version=__version__,
        description=(
            "Las seis capacidades que una venta colombiana necesita y que un "
            "catalogo de herramientas pensado para Estados Unidos no tiene. "
            "Cada ruta POST /api/<nombre> es la misma capacidad que la vitrina "
            "registra como herramienta WebMCP con ese nombre."
        ),
    )
    aplicacion.add_exception_handler(DominioError, _error_dominio)
    aplicacion.add_exception_handler(ValueError, _error_dominio)
    _registrar_rutas(aplicacion)
    if DIRECTORIO_ESTATICOS.is_dir():
        aplicacion.mount(
            "/static",
            StaticFiles(directory=DIRECTORIO_ESTATICOS),
            name="static",
        )
    return aplicacion


def _registrar_rutas(aplicacion: FastAPI) -> None:  # noqa: PLR0915
    """Cuelga las rutas; una funcion sola porque cada ruta es una traduccion."""

    @aplicacion.get("/health", response_model=SaludRespuesta, tags=["servicio"])
    def salud() -> SaludRespuesta:
        """Latido con el tamano de los maestros que este proceso tiene cargados."""
        return SaludRespuesta(
            estado="ok",
            version=__version__,
            productos=len(catalogo.CATALOGO),
            ciudades=len(envio.CIUDADES),
            transportadoras=len(envio.TRANSPORTADORAS),
            sin_contraentrega=len(envio.SIN_CONTRAENTREGA),
        )

    @aplicacion.get("/api/contexto", response_model=ContextoRespuesta, tags=["catalogo"])
    def contexto() -> ContextoRespuesta:
        """Maestros de arranque: comercio, ciudades, tipos de documento y modalidades."""
        return ContextoRespuesta(
            comercio=ComercioDTO(
                nombre=catalogo.COMERCIO.nombre,
                documento=str(catalogo.COMERCIO.documento),
                codigo_dian=catalogo.COMERCIO.documento.codigo_dian,
                direccion=catalogo.COMERCIO.direccion,
                ciudad=envio.CIUDADES[catalogo.COMERCIO.ciudad_codigo_dane].etiqueta,
                responsable_iva=catalogo.COMERCIO.responsable_iva,
                correo=catalogo.COMERCIO.correo,
            ),
            categorias=[c.value for c in catalogo.Categoria],
            ciudades=[_ciudad_dto(ciudad) for ciudad in envio.CIUDADES.values()],
            tipos_documento=[
                TipoDocumentoDTO(
                    tipo=regla.tipo.value,
                    codigo_dian=regla.codigo_dian,
                    nombre=regla.nombre,
                    largo_minimo=regla.largo_minimo,
                    largo_maximo=regla.largo_maximo,
                    solo_digitos=regla.solo_digitos,
                    requiere_dv=regla.requiere_dv,
                )
                for regla in documento.REGLAS.values()
            ],
            modalidades_venta=[m.value for m in retracto.Modalidad],
            exclusiones_retracto=sorted(retracto.CATEGORIAS_SIN_RETRACTO),
            metodos_pago=[m.value for m in pago.MetodoPago],
            nota_flete=envio.FLETE_EXCLUIDO_DE_IVA,
            nota_impuestos_saludables=impuesto.IMPUESTOS_SALUDABLES,
        )

    @aplicacion.post("/api/buscar_productos", response_model=BusquedaRespuesta, tags=["tools"])
    def buscar_productos(peticion: BusquedaPeticion) -> BusquedaRespuesta:
        """Busca en el catalogo y valora cada referencia contra el destino."""
        destino = _ciudad(peticion.destino)
        if peticion.categoria:
            encontrados: Iterable[catalogo.Producto] = catalogo.por_categoria(
                catalogo.Categoria(peticion.categoria)
            )
        elif peticion.consulta.strip():
            encontrados = catalogo.buscar(peticion.consulta)
        else:
            encontrados = catalogo.productos()
        listado = list(encontrados)
        limite = max(1, min(peticion.limite, _LIMITE_BUSQUEDA_MAXIMO))
        nota = (
            f"precios sin IVA por destino: {destino.etiqueta} tiene regimen especial"
            if destino is not None and destino.regimen_iva_especial
            else "precios de gondola con impuesto incluido, redondeados a la moneda de 50 pesos"
        )
        return BusquedaRespuesta(
            consulta=peticion.categoria or peticion.consulta,
            destino=_ciudad_dto(destino) if destino else None,
            total=len(listado),
            productos=[_producto_dto(p, destino) for p in listado[:limite]],
            nota=nota,
        )

    @aplicacion.post("/api/cotizar_envio", response_model=EnvioRespuesta, tags=["tools"])
    def cotizar_envio(peticion: EnvioPeticion) -> EnvioRespuesta:
        """Cotiza el despacho y dice si ese destino admite contra entrega."""
        ciudad = envio.resolver_ciudad(peticion.destino)
        carrito = _carrito(peticion.items)
        disponible, motivo = envio.diagnostico_contraentrega(ciudad)
        tope = envio.tope_contraentrega(ciudad)
        if not carrito.tiene_despachables:
            return EnvioRespuesta(
                destino=_ciudad_dto(ciudad),
                despachable=False,
                peso_facturable_gramos=0,
                valor_declarado=_monto(0),
                contraentrega_disponible=disponible,
                contraentrega_motivo=motivo,
                tope_contraentrega=_monto(tope),
                opciones=[],
                mejor=None,
                nota=(
                    "el pedido no tiene nada fisico que despachar: agrega una "
                    "referencia con bulto o entregalo en el mostrador"
                ),
            )
        liquidacion = impuesto.liquidar(carrito.lineas_venta(), destino=ciudad)
        declarado = liquidacion.total_centavos if peticion.declarar_valor else 0
        paquete = carrito.paquete(valor_declarado_centavos=declarado)
        opciones = envio.cotizar(
            ciudad,
            paquete,
            contraentrega=peticion.contraentrega,
            monto_a_recaudar_centavos=liquidacion.total_centavos,
        )
        return EnvioRespuesta(
            destino=_ciudad_dto(ciudad),
            despachable=True,
            peso_facturable_gramos=paquete.peso_facturable_gramos,
            valor_declarado=_monto(declarado),
            contraentrega_disponible=disponible,
            contraentrega_motivo=motivo,
            tope_contraentrega=_monto(tope),
            opciones=[_opcion_dto(o) for o in opciones],
            mejor=_opcion_dto(opciones[0]) if opciones else None,
            nota=envio.FLETE_EXCLUIDO_DE_IVA,
        )

    @aplicacion.post(
        "/api/validar_documento_dian", response_model=DocumentoRespuesta, tags=["tools"]
    )
    def validar_documento_dian(peticion: DocumentoPeticion) -> DocumentoRespuesta:
        """Valida la identificacion del comprador contra las reglas del anexo DIAN."""
        dictado = documento.separar_dv(peticion.numero)[1]
        try:
            identidad = documento.validar(peticion.tipo, peticion.numero)
        except DominioError as exc:
            return DocumentoRespuesta(
                valido=False,
                tipo=peticion.tipo.strip().upper(),
                nombre_tipo=None,
                codigo_dian=None,
                numero=None,
                dv=None,
                dv_calculado=False,
                formateado=None,
                es_persona_juridica=False,
                mensaje=str(exc),
            )
        calculado = identidad.regla.requiere_dv and dictado is None
        mensaje = (
            f"{identidad.regla.nombre}: identificacion valida; la DIAN la recibe con el codigo "
            f"{identidad.codigo_dian} del anexo tecnico"
        )
        if calculado:
            mensaje += f". El digito de verificacion no venia dictado y se calculo: {identidad.dv}"
        return DocumentoRespuesta(
            valido=True,
            tipo=identidad.tipo.value,
            nombre_tipo=identidad.regla.nombre,
            codigo_dian=identidad.codigo_dian,
            numero=identidad.numero,
            dv=identidad.dv,
            dv_calculado=calculado,
            formateado=identidad.formateado,
            es_persona_juridica=identidad.es_persona_juridica,
            mensaje=mensaje,
        )

    @aplicacion.post(
        "/api/calcular_total_con_iva", response_model=LiquidacionRespuesta, tags=["tools"]
    )
    def calcular_total_con_iva(peticion: LiquidacionPeticion) -> LiquidacionRespuesta:
        """Liquida el carrito linea por linea con el regimen que le toca a cada una."""
        destino = _ciudad(peticion.destino)
        carrito = _carrito(peticion.items)
        liquidacion = impuesto.liquidar(
            carrito.lineas_venta(),
            destino=destino,
            responsable_iva=peticion.responsable_iva,
        )
        return _liquidacion_dto(
            liquidacion, carrito, destino, responsable_iva=peticion.responsable_iva
        )

    @aplicacion.post(
        "/api/consultar_derecho_retracto", response_model=RetractoRespuesta, tags=["tools"]
    )
    def consultar_derecho_retracto(peticion: RetractoPeticion) -> RetractoRespuesta:
        """Calcula el plazo del Art. 47 contra el calendario colombiano real."""
        try:
            modalidad = retracto.Modalidad(peticion.modalidad.strip().lower())
        except ValueError as exc:
            admitidas = ", ".join(m.value for m in retracto.Modalidad)
            msg = f"modalidad de venta desconocida {peticion.modalidad!r}; admitidas: {admitidas}"
            raise ValueError(msg) from exc
        carrito = _carrito(peticion.items)
        exclusiones = carrito.exclusiones_retracto | frozenset(peticion.exclusiones)
        ventana = retracto.ventana_retracto(
            peticion.fecha_entrega, modalidad=modalidad, exclusiones=exclusiones
        )
        calendario = (ventana.vence - ventana.fecha_entrega).days if ventana.vence else 0
        return RetractoRespuesta(
            aplica=ventana.aplica,
            motivo=ventana.motivo,
            modalidad=modalidad.value,
            fecha_entrega=ventana.fecha_entrega,
            inicio=ventana.inicio,
            vence=ventana.vence,
            dias_habiles=ventana.dias_habiles,
            dias_calendario=calendario,
            festivos_intermedios=[
                FestivoDTO(
                    fecha=f.fecha,
                    nombre=f.nombre,
                    trasladado=f.trasladado,
                    fecha_original=f.fecha_original,
                    fundamento=f.fundamento,
                )
                for f in ventana.festivos_intermedios
            ],
            exclusiones_detectadas=sorted(exclusiones),
            dias_para_devolver_dinero=ventana.dias_para_devolver_dinero,
            vigente=ventana.vigente(peticion.hoy) if peticion.hoy else None,
            dias_habiles_restantes=(
                ventana.dias_habiles_restantes(peticion.hoy) if peticion.hoy else None
            ),
        )

    @aplicacion.post("/api/metodos_de_pago", response_model=PagoRespuesta, tags=["tools"])
    def metodos_de_pago(peticion: PagoPeticion) -> PagoRespuesta:
        """Evalua los cinco rieles contra el destino, el monto y el carrito."""
        ciudad = envio.resolver_ciudad(peticion.destino)
        carrito = _carrito(peticion.items)
        liquidacion = impuesto.liquidar(carrito.lineas_venta(), destino=ciudad)
        flete = 0
        recaudo = 0
        if peticion.incluir_flete and carrito.tiene_despachables:
            paquete = carrito.paquete(valor_declarado_centavos=liquidacion.total_centavos)
            terrestre = envio.mejor_cotizacion(ciudad, paquete)
            flete = terrestre.total_centavos if terrestre else 0
            con_recaudo = envio.mejor_cotizacion(
                ciudad,
                paquete,
                contraentrega=True,
                monto_a_recaudar_centavos=liquidacion.total_centavos + flete,
            )
            recaudo = con_recaudo.recaudo_centavos if con_recaudo else 0
        total = liquidacion.total_centavos + flete
        contexto_pago = pago.ContextoPago(
            total_centavos=total,
            ciudad=ciudad,
            base_sin_impuestos_centavos=liquidacion.base_gravable_centavos,
            comision_recaudo_centavos=recaudo,
            contiene_servicios=carrito.contiene_servicios,
            banco_pse=peticion.banco_pse,
            cliente_tiene_bancolombia=peticion.cliente_tiene_bancolombia,
        )
        evaluaciones = pago.evaluar(contexto_pago)
        disponibles = [e for e in evaluaciones if e.disponible]
        parametros = contexto_pago.parametros
        return PagoRespuesta(
            destino=_ciudad_dto(ciudad),
            desglose=DesgloseDTO(
                mercancia=_monto(liquidacion.total_centavos),
                flete=_monto(flete),
                total_pedido=_monto(total),
                nota_flete=envio.FLETE_EXCLUIDO_DE_IVA,
            ),
            metodos=[_metodo_dto(e) for e in evaluaciones],
            recomendado=disponibles[0].metodo.value if disponibles else None,
            parametros=ParametrosDTO(
                anio=parametros.anio,
                uvt=_monto(parametros.uvt_centavos),
                smmlv=_monto(parametros.smmlv_centavos),
                tope_deposito_bajo_monto=_monto(parametros.tope_deposito_bajo_monto_centavos),
                exencion_gmf_mensual=_monto(parametros.exencion_gmf_mensual_centavos),
            ),
            bancos_pse=sorted(pago.BANCOS_PSE),
        )

    @aplicacion.get("/", include_in_schema=False)
    def vitrina() -> FileResponse:
        """Sirve la vitrina; es el archivo que registra las herramientas WebMCP."""
        return FileResponse(ARCHIVO_INDEX, media_type="text/html")


app: Final = crear_app()
"""Instancia que sirve ``uvicorn tendero.api:app``."""

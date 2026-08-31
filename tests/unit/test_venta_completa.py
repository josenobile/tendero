"""Ventas completas de punta a punta, que es donde las reglas se cruzan.

Cada prueba es un pedido real de la tienda: catalogo, impuesto, flete, pago y
retracto resueltos juntos. Son los escenarios que las herramientas WebMCP
exponen al agente, y sirven para verificar que las reglas de un modulo se
propagan a los otros: que un destino sin carretera apague a la vez el IVA, el
contra entrega y el plazo de despacho.
"""

from __future__ import annotations

from datetime import date

from tendero.domain.catalogo import COMERCIO, armar_carrito
from tendero.domain.documento import validar
from tendero.domain.envio import CIUDADES, cotizar, diagnostico_contraentrega, mejor_cotizacion
from tendero.domain.impuesto import liquidar, resumen_descontables
from tendero.domain.pago import ContextoPago, MetodoPago, evaluar, recomendar
from tendero.domain.retracto import Modalidad, ventana_retracto

MEDELLIN = CIUDADES["05001"]
PASTO = CIUDADES["52001"]
LETICIA = CIUDADES["91001"]
SAN_ANDRES = CIUDADES["88001"]


def test_mercado_a_domicilio_en_medellin() -> None:
    """El caso base: cinco lineas, tres regimenes, mensajero local y retracto vivo."""
    cliente = validar("CC", "1.017.234.567")
    carrito = armar_carrito(
        {"FRU-PLA-LB": 2, "LAC-LEC-1L": 3, "CAF-TOS-250": 1, "ASE-JAB-X3": 1, "ABA-ARR-500": 2}
    )
    liquidacion = liquidar(carrito.lineas_venta(), destino=MEDELLIN)

    assert cliente.codigo_dian == "13"
    assert liquidacion.iva_centavos == 710_00 + 1_501_00
    assert liquidacion.total_centavos == liquidacion.base_gravable_centavos + 2_211_00

    envio = mejor_cotizacion(
        MEDELLIN, carrito.paquete(valor_declarado_centavos=liquidacion.total_centavos)
    )
    assert envio is not None
    assert envio.codigo_transportadora == "rapidito_aburra"
    assert envio.dias_habiles_maximo <= 2

    ventana = ventana_retracto(
        date(2026, 9, 1), modalidad=Modalidad.DOMICILIO, exclusiones=carrito.exclusiones_retracto
    )
    assert not ventana.aplica
    assert "perecedero" in ventana.motivo


def test_pedido_no_perecedero_conserva_el_retracto() -> None:
    """Un pedido de aseo si se puede devolver, y el plazo salta la Semana Santa."""
    carrito = armar_carrito({"ASE-JAB-X3": 2, "ASE-DET-1K": 1, "MAS-CON-2K": 1})
    assert carrito.exclusiones_retracto == frozenset()

    ventana = ventana_retracto(date(2026, 4, 1), modalidad=Modalidad.WHATSAPP)
    assert ventana.aplica
    assert ventana.vence == date(2026, 4, 10)
    assert {f.nombre for f in ventana.festivos_intermedios} == {"Jueves Santo", "Viernes Santo"}


def test_pedido_a_leticia_apaga_iva_contraentrega_y_alarga_el_plazo() -> None:
    """Un solo destino cambia el impuesto, el medio de pago y la logistica."""
    carrito = armar_carrito({"ASE-JAB-X3": 4, "ASE-DET-1K": 2})
    liquidacion = liquidar(carrito.lineas_venta(), destino=LETICIA)

    assert liquidacion.iva_centavos == 0
    assert liquidacion.total_centavos == liquidacion.base_gravable_centavos
    assert "Leticia" in liquidacion.notas[0]

    disponible, motivo = diagnostico_contraentrega(LETICIA)
    assert not disponible
    assert "aereo" in motivo

    envio = mejor_cotizacion(
        LETICIA, carrito.paquete(valor_declarado_centavos=liquidacion.total_centavos)
    )
    terrestre = mejor_cotizacion(
        PASTO, carrito.paquete(valor_declarado_centavos=liquidacion.total_centavos)
    )
    assert envio is not None
    assert terrestre is not None
    assert envio.recargo_aereo_centavos > 0
    assert envio.dias_habiles_maximo > terrestre.dias_habiles_maximo

    rieles = {
        e.metodo: e
        for e in evaluar(
            ContextoPago(
                total_centavos=liquidacion.total_centavos,
                ciudad=LETICIA,
                base_sin_impuestos_centavos=liquidacion.base_gravable_centavos,
            )
        )
    }
    assert not rieles[MetodoPago.CONTRAENTREGA].disponible
    assert rieles[MetodoPago.NEQUI].disponible


def test_mismo_carrito_cuesta_menos_en_san_andres_que_en_medellin() -> None:
    """El precio final depende del departamento de destino, no solo del flete."""
    carrito = armar_carrito({"ASE-JAB-X3": 5, "BEB-GAS-15": 6})
    continente = liquidar(carrito.lineas_venta(), destino=MEDELLIN)
    archipielago = liquidar(carrito.lineas_venta(), destino=SAN_ANDRES)
    assert continente.total_centavos > archipielago.total_centavos
    assert archipielago.iva_centavos == 0
    assert continente.base_gravable_centavos == archipielago.base_gravable_centavos


def test_contraentrega_a_pasto_de_punta_a_punta() -> None:
    """El recaudo cotizado con la transportadora alimenta el medio de pago."""
    carrito = armar_carrito({"ASE-DET-1K": 3, "MAS-CON-2K": 2})
    liquidacion = liquidar(carrito.lineas_venta(), destino=PASTO)
    paquete = carrito.paquete(valor_declarado_centavos=liquidacion.total_centavos)

    opciones = cotizar(
        PASTO,
        paquete,
        contraentrega=True,
        monto_a_recaudar_centavos=liquidacion.total_centavos,
    )
    assert opciones
    elegida = opciones[0]
    assert elegida.recaudo_centavos > 0

    contexto = ContextoPago(
        total_centavos=liquidacion.total_centavos,
        ciudad=PASTO,
        base_sin_impuestos_centavos=liquidacion.base_gravable_centavos,
        comision_recaudo_centavos=elegida.recaudo_centavos,
    )
    contraentrega = next(e for e in evaluar(contexto) if e.metodo is MetodoPago.CONTRAENTREGA)
    assert contraentrega.disponible
    assert contraentrega.total_cliente_centavos > liquidacion.total_centavos
    assert contraentrega.dias_habiles_liquidacion == 8


def test_almuerzo_en_el_local_paga_consumo_y_no_tiene_retracto() -> None:
    """Comer en la tienda no es venta a distancia ni causa IVA."""
    carrito = armar_carrito({"PRE-ALM-COR": 2})
    liquidacion = liquidar(carrito.lineas_venta(), destino=MEDELLIN)
    assert liquidacion.iva_centavos == 0
    assert liquidacion.inc_centavos == 2_368_00

    ventana = ventana_retracto(date(2026, 9, 1), modalidad=Modalidad.MOSTRADOR)
    assert not ventana.aplica
    assert "punto de venta" in ventana.motivo

    contexto = ContextoPago(
        total_centavos=liquidacion.total_centavos, ciudad=MEDELLIN, contiene_servicios=True
    )
    contraentrega = next(e for e in evaluar(contexto) if e.metodo is MetodoPago.CONTRAENTREGA)
    assert not contraentrega.disponible


def test_una_canasta_mixta_pierde_descontables_en_la_parte_excluida() -> None:
    """El fruver no deja recuperar el IVA de insumos y eso hay que verlo."""
    carrito = armar_carrito({"FRU-PLA-LB": 10, "ASE-JAB-X3": 1})
    liquidacion = liquidar(carrito.lineas_venta(), destino=MEDELLIN)
    resumen = resumen_descontables(liquidacion)
    assert resumen.base_sin_derecho_centavos == 28_000_00
    assert resumen.base_con_derecho_centavos == 7_900_00
    assert "Art. 488" in resumen.nota


def test_la_factura_declara_al_vendedor_y_al_comprador() -> None:
    """Sin las dos identidades validas la DIAN no acepta el documento."""
    comprador = validar("NIT", "890.903.938-8")
    assert COMERCIO.documento.dv is not None
    assert comprador.dv == 8
    assert COMERCIO.responsable_iva


def test_un_pedido_grande_deja_de_caber_en_nequi_pero_sigue_teniendo_riel() -> None:
    """El techo de un deposito de bajo monto no puede dejar la venta sin cobrar."""
    carrito = armar_carrito({"MAS-CON-2K": 500})
    liquidacion = liquidar(carrito.lineas_venta(), destino=MEDELLIN)
    contexto = ContextoPago(
        total_centavos=liquidacion.total_centavos,
        ciudad=MEDELLIN,
        base_sin_impuestos_centavos=liquidacion.base_gravable_centavos,
        comision_recaudo_centavos=60_000_00,
    )
    rieles = {e.metodo: e for e in evaluar(contexto)}
    assert liquidacion.total_centavos > 11_388_000_00
    assert not rieles[MetodoPago.NEQUI].disponible
    assert not rieles[MetodoPago.CONTRAENTREGA].disponible
    assert recomendar(contexto).disponible

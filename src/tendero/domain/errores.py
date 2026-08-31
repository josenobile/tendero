"""Errores del dominio.

Se separan del resto para que la capa WebMCP pueda mapear cada uno a un mensaje
accionable para el agente: un fallo de validacion de documento no es lo mismo
que una ciudad sin cobertura, y el agente debe poder reintentar solo el primero.
"""

from __future__ import annotations

__all__ = [
    "CiudadDesconocidaError",
    "DocumentoInvalidoError",
    "DominioError",
    "MetodoPagoError",
    "ProductoDesconocidoError",
]


class DominioError(Exception):
    """Raiz de todos los errores de negocio; nunca se lanza directamente."""


class DocumentoInvalidoError(DominioError):
    """El documento no cumple las reglas DIAN de tipo, longitud o digito."""


class CiudadDesconocidaError(DominioError):
    """El destino no esta en el maestro de ciudades DANE soportadas."""


class ProductoDesconocidoError(DominioError):
    """El SKU no existe en el catalogo del comercio."""


class MetodoPagoError(DominioError):
    """El medio de pago solicitado no aplica al pedido evaluado."""

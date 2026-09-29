"""
Modelos de datos del pipeline de cuadre de pedidos.

Idea clave: separamos claramente "lo que se extrajo de un documento"
de "lo que concluimos al comparar documentos". Son responsabilidades
distintas y por eso van en módulos distintos (extractor.py vs comparator.py).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TipoDocumento(str, Enum):
    FACTURA = "factura"
    ALBARAN = "albaran"
    PACKING_LIST = "packing_list"


class Severidad(str, Enum):
    """
    Niveles de gravedad de una discrepancia. Esto es lo que permite
    ordenar el resumen y decidir el semáforo final.
    """
    CRITICA = "critica"   # dinero o cantidad no cuadra de verdad -> bloquea
    ALTA = "alta"         # probable error, hay que verificar antes de cerrar
    MEDIA = "media"       # desviación menor, informativa pero a vigilar
    INFO = "info"         # diferencia de formato/nombre, no es un error real


@dataclass
class ProductoExtraido:
    nombre: Optional[str] = None
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    precio_unitario: Optional[float] = None
    base_imponible: Optional[float] = None
    iva_pct: Optional[float] = None
    importe_total: Optional[float] = None


@dataclass
class DocumentoExtraido:
    """
    Salida normalizada de la extracción, venga de un LLM, de OCR+regex
    o de un parser específico. Todo lo demás del pipeline trabaja
    contra esta estructura, no contra el documento original.
    """
    tipo: TipoDocumento
    numero_pedido: Optional[str] = None
    proveedor: Optional[str] = None
    fecha: Optional[str] = None  # formato ISO YYYY-MM-DD
    producto: ProductoExtraido = field(default_factory=ProductoExtraido)
    campos_no_legibles: List[str] = field(default_factory=list)
    confianza: str = "alta"  # alta | media | baja


@dataclass
class Discrepancia:
    campo: str
    severidad: Severidad
    mensaje: str
    valores: dict  # {"factura": ..., "albaran": ..., "packing_list": ...}
    accion_sugerida: str

"""
Contrato de la API REST.

Son modelos distintos de los dataclasses de models.py a propósito:
models.py es el lenguaje interno del pipeline; esto es lo que se
promete a los clientes (el dashboard). Así podemos cambiar el
pipeline sin romper el frontend, y viceversa.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models import Discrepancia, Semaforo, Severidad


class EstadoRevision(str, Enum):
    AUTO_APROBADO = "AUTO_APROBADO"             # semáforo verde, nadie tiene que mirarlo
    PENDIENTE_REVISION = "PENDIENTE_REVISION"   # 🔴/🟠 en cola para un humano
    RESUELTO = "RESUELTO"                       # un operador ya tomó una decisión


class AccionOperador(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class DiscrepancyModel(BaseModel):
    campo: str
    severidad: Severidad
    mensaje: str
    # valor_esperado / valor_encontrado es la vista "A vs B" que pinta la UI.
    # `valores` conserva el dato completo por documento para no perder nada.
    valor_esperado: Any = None
    valor_encontrado: Any = None
    valores: Dict[str, Any] = Field(default_factory=dict)
    accion_sugerida: str

    @classmethod
    def from_discrepancia(cls, d: Discrepancia) -> "DiscrepancyModel":
        valores = dict(d.valores)
        # Referencia: la factura en comparaciones entre documentos, o el
        # valor recalculado en las validaciones aritméticas internas.
        clave_ref = next((k for k in ("factura", "calculado") if k in valores), None)
        if clave_ref is None and valores:
            clave_ref = next(iter(valores))
        resto = {k: v for k, v in valores.items() if k != clave_ref}
        return cls(
            campo=d.campo,
            severidad=d.severidad,
            mensaje=d.mensaje,
            valor_esperado=valores.get(clave_ref) if clave_ref else None,
            valor_encontrado=next(iter(resto.values())) if len(resto) == 1 else resto or None,
            valores=valores,
            accion_sugerida=d.accion_sugerida,
        )


class DocumentoResumen(BaseModel):
    tipo: str
    proveedor: Optional[str]
    producto: Optional[str]
    cantidad: Optional[float]
    fecha: Optional[str]
    confianza: str


class ReviewRecord(BaseModel):
    action_taken: AccionOperador
    user_notes: Optional[str]
    operator_id: str
    timestamp: datetime


class OrderAnalysisResponse(BaseModel):
    analysis_id: int
    order_id: str
    status_semaforo: Semaforo
    estado_revision: EstadoRevision
    decision_final: Optional[AccionOperador] = None
    proveedor: Optional[str]
    similitud_proveedor: Optional[float] = Field(
        None, description="Peor similitud fuzzy entre los nombres de proveedor (0-1)."
    )
    documentos: List[DocumentoResumen]
    total_discrepancies: int
    items_discrepancias: List[DiscrepancyModel]
    resumen_texto: str
    timestamp: datetime


class OrderAnalysisDetail(OrderAnalysisResponse):
    historial_revisiones: List[ReviewRecord] = Field(default_factory=list)


class UserFeedbackUpdate(BaseModel):
    # order_id también viaja en la URL; si viene en el body debe coincidir.
    order_id: Optional[str] = None
    action_taken: AccionOperador
    user_notes: Optional[str] = Field(None, max_length=2000)
    operator_id: str = Field(..., min_length=1, max_length=100)


class ProveedorIncidencias(BaseModel):
    proveedor: str
    incidencias: int


class MetricsResponse(BaseModel):
    total_pedidos: int
    pct_auto_aprobacion: float
    en_cola: int
    resueltos_hoy: int
    top_proveedores: List[ProveedorIncidencias]

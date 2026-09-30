"""
API REST sobre el pipeline de cuadre de pedidos.

Esta capa NO contiene lógica de negocio: recibe documentos, llama a
pipeline.analizar() (el mismo código que usa el script de consola),
persiste el resultado y expone la cola de revisión humana.

Arranque (desde la raíz del repo):
    uvicorn api.main:app --reload
Documentación interactiva: http://localhost:8000/docs
"""

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api import store
from api.schemas import (
    EstadoRevision,
    MetricsResponse,
    OrderAnalysisDetail,
    OrderAnalysisResponse,
    UserFeedbackUpdate,
)
from models import Severidad, TipoDocumento
from pipeline import analizar, documentos_de_ejemplo

# .txt va al extractor regex (sin red); PDF/JPEG van a Claude con visión.
EXTENSIONES_PERMITIDAS = {".txt", ".pdf", ".jpg", ".jpeg"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init_db()
    yield


app = FastAPI(title="LogiCheck AI — Cuadre de pedidos", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("LOGICHECK_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _guardar_subida(upload: UploadFile, destino_dir: Path, tipo: TipoDocumento) -> Path:
    sufijo = Path(upload.filename or "").suffix.lower()
    if sufijo not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(
            status_code=415,
            detail=f"{tipo.value}: formato '{sufijo or '?'}' no soportado. Usa {sorted(EXTENSIONES_PERMITIDAS)}.",
        )
    destino = destino_dir / f"{tipo.value}{sufijo}"
    with destino.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return destino


@app.post("/api/v1/process-order", response_model=OrderAnalysisResponse, status_code=201)
def process_order(
    factura: Optional[UploadFile] = File(None),
    albaran: Optional[UploadFile] = File(None),
    packing_list: Optional[UploadFile] = File(None),
    sample: str = Form("4521", description="Pedido de sample_docs/ a usar si no se suben ficheros."),
):
    """
    Ejecuta extractor -> comparator -> summarizer y persiste el resultado.
    Sin ficheros, usa los documentos de ejemplo (útil para la demo).
    """
    subidas = {
        TipoDocumento.FACTURA: factura,
        TipoDocumento.ALBARAN: albaran,
        TipoDocumento.PACKING_LIST: packing_list,
    }
    presentes = {t: f for t, f in subidas.items() if f is not None and f.filename}

    if presentes and len(presentes) != len(subidas):
        faltan = [t.value for t in subidas if t not in presentes]
        raise HTTPException(status_code=422, detail=f"Hay que subir los 3 documentos. Faltan: {faltan}")

    with tempfile.TemporaryDirectory() as tmp:
        if presentes:
            rutas = {t: _guardar_subida(f, Path(tmp), t) for t, f in presentes.items()}
        else:
            rutas = documentos_de_ejemplo(sample)
            if not all(r.exists() for r in rutas.values()):
                raise HTTPException(status_code=404, detail=f"No hay documentos de ejemplo para el pedido '{sample}'.")
        try:
            resultado = analizar(rutas)
        except Exception as e:  # red, API key, JSON mal formado del LLM...
            raise HTTPException(status_code=502, detail=f"Fallo en la extracción: {e}") from e

    return store.guardar_analisis(resultado)


@app.get("/api/v1/feedbacks", response_model=List[OrderAnalysisResponse])
def list_feedbacks(
    estado: Optional[EstadoRevision] = Query(None),
    severidad: Optional[Severidad] = Query(None, description="Pedidos con al menos una discrepancia de esta severidad."),
    proveedor: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Búsqueda parcial por número de pedido."),
):
    return store.listar(estado=estado, severidad=severidad, proveedor=proveedor, q=q)


@app.get("/api/v1/metrics", response_model=MetricsResponse)
def get_metrics():
    return store.metricas()


@app.get("/api/v1/feedbacks/{order_id}", response_model=OrderAnalysisDetail)
def get_feedback(order_id: str):
    detalle = store.obtener(order_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail=f"Pedido '{order_id}' no encontrado.")
    return detalle


@app.put("/api/v1/feedbacks/{order_id}/review", response_model=OrderAnalysisDetail)
def review_order(order_id: str, body: UserFeedbackUpdate):
    if body.order_id is not None and body.order_id != order_id:
        raise HTTPException(status_code=422, detail="order_id del body no coincide con el de la URL.")
    detalle = store.registrar_revision(order_id, body.action_taken, body.user_notes, body.operator_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail=f"Pedido '{order_id}' no encontrado.")
    return detalle

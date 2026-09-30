"""
Pipeline end-to-end reutilizable: extractor -> comparator -> summarizer.

Vive fuera de main.py para que el script de consola y la API REST
ejecuten exactamente el mismo código. Si la API tuviera su propia
copia del flujo, tarde o temprano ambos darían resultados distintos
para el mismo pedido, y eso rompe la auditabilidad.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from comparator import comparar_pedido
from extractor import extract_mock, extract_with_claude
from models import Discrepancia, DocumentoExtraido, Semaforo, TipoDocumento
from summarizer import generar_resumen, semaforo

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DOCS_DIR = BASE_DIR / "sample_docs"


@dataclass
class ResultadoAnalisis:
    numero_pedido: str
    documentos: Dict[TipoDocumento, DocumentoExtraido]
    discrepancias: List[Discrepancia]
    semaforo: Semaforo
    resumen: str


def extraer(path: Path, tipo: TipoDocumento) -> DocumentoExtraido:
    """Texto plano -> extractor regex (sin red). PDF/imagen -> Claude."""
    if path.suffix.lower() == ".txt":
        return extract_mock(path.read_text(encoding="utf-8"), tipo)
    return extract_with_claude(str(path), tipo)


def documentos_de_ejemplo(numero: str = "4521") -> Dict[TipoDocumento, Path]:
    return {
        TipoDocumento.FACTURA: SAMPLE_DOCS_DIR / f"factura_{numero}.txt",
        TipoDocumento.ALBARAN: SAMPLE_DOCS_DIR / f"albaran_{numero}.txt",
        TipoDocumento.PACKING_LIST: SAMPLE_DOCS_DIR / f"packing_list_{numero}.txt",
    }


def analizar(rutas: Dict[TipoDocumento, Path]) -> ResultadoAnalisis:
    docs = {tipo: extraer(ruta, tipo) for tipo, ruta in rutas.items()}
    factura = docs[TipoDocumento.FACTURA]
    discrepancias = comparar_pedido(factura, docs[TipoDocumento.ALBARAN], docs[TipoDocumento.PACKING_LIST])
    numero = factura.numero_pedido or "DESCONOCIDO"
    return ResultadoAnalisis(
        numero_pedido=numero,
        documentos=docs,
        discrepancias=discrepancias,
        semaforo=semaforo(discrepancias),
        resumen=generar_resumen(numero, discrepancias),
    )

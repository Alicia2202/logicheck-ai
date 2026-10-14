"""
Persistencia ligera sin ORM: Postgres si hay DATABASE_URL (Supabase en
Vercel), SQLite en local. Las consultas son SQL estándar común a ambos;
solo cambian el DDL y el estilo de parámetros (? frente a %s).

Dos tablas con responsabilidades distintas:
  - analyses: cada ejecución del pipeline. Reprocesar un pedido crea una
    fila nueva, no pisa la anterior: queremos poder reconstruir qué vio
    el sistema en cada momento.
  - reviews: log append-only de decisiones humanas. Nunca se actualiza
    ni se borra una fila; es el rastro de auditoría.

Las vistas del dashboard trabajan sobre el análisis más reciente de
cada pedido.
"""

import json
import os
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from api.schemas import (
    AccionOperador,
    DiscrepancyModel,
    DocumentoResumen,
    EstadoRevision,
    MetricsResponse,
    OrderAnalysisDetail,
    OrderAnalysisResponse,
    ProveedorIncidencias,
    ReviewRecord,
)
from comparator import similitud_minima
from models import Semaforo, Severidad
from pipeline import ResultadoAnalisis



def _url_postgres() -> Optional[str]:
    # DATABASE_URL: la cadena del pooler de Supabase (Connect -> Transaction
    # pooler). POSTGRES_URL: la que crea la integración Supabase de Vercel,
    # que añade un parámetro "supa" que libpq rechaza.
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        return None
    partes = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(partes.query) if k != "supa"]
    return urlunsplit(partes._replace(query=urlencode(query)))


POSTGRES_URL = _url_postgres()
# Sin Postgres, SQLite en un fichero local. No sirve en Vercel: cada
# instancia tendría su propia copia de /tmp y verían datos distintos.
DB_PATH = Path(os.environ.get("LOGICHECK_DB", Path(__file__).resolve().parent.parent / "logicheck.db"))

# Campos que cuentan como "fricción" de un proveedor en las métricas:
# lo que no se pudo leer y lo que no cuadró en cantidad.
CAMPOS_FRICCION = {"cantidad", "calidad_extraccion"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id                  {id_autoincremental},
    order_id            TEXT NOT NULL,
    proveedor           TEXT,
    similitud_proveedor REAL,
    semaforo            TEXT NOT NULL,
    estado              TEXT NOT NULL,
    decision            TEXT,
    severidades         TEXT NOT NULL,   -- ",critica,info," para filtrar con LIKE
    documentos_json     TEXT NOT NULL,
    discrepancias_json  TEXT NOT NULL,
    resumen             TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_order ON analyses(order_id);

CREATE TABLE IF NOT EXISTS reviews (
    id          {id_autoincremental},
    analysis_id BIGINT NOT NULL REFERENCES analyses(id),
    order_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    notes       TEXT,
    operator_id TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_order ON reviews(order_id);
"""

# Supabase expone las tablas de "public" por su API REST con la clave anónima.
# Con RLS activado y sin políticas, esa vía no ve nada; la API de este repo
# conecta como propietario de las tablas y no se ve afectada.
_SCHEMA_POSTGRES_EXTRA = """
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
"""

_ULTIMO_POR_PEDIDO = "a.id IN (SELECT MAX(id) FROM analyses GROUP BY order_id)"


def _ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class _ConexionPostgres:
    """Adapta psycopg a la interfaz de sqlite3 que usa este módulo."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        # Sin parámetros se pasa None: así psycopg admite varias sentencias
        # en una sola llamada (el esquema) y no interpreta los "%" literales.
        return self._conn.execute(sql.replace("?", "%s"), params or None)


@contextmanager
def _conexion() -> Iterator[sqlite3.Connection]:
    if POSTGRES_URL:
        import psycopg
        from psycopg.rows import dict_row

        # prepare_threshold=None: el pooler de Supabase (modo transacción)
        # no admite sentencias preparadas.
        with psycopg.connect(POSTGRES_URL, row_factory=dict_row, prepare_threshold=None) as conn:
            yield _ConexionPostgres(conn)
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    if POSTGRES_URL:
        with _conexion() as conn:
            conn.execute(_SCHEMA.format(id_autoincremental="BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY")
                         + _SCHEMA_POSTGRES_EXTRA)
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conexion() as conn:
        conn.executescript(_SCHEMA.format(id_autoincremental="INTEGER PRIMARY KEY AUTOINCREMENT"))


def vacia() -> bool:
    with _conexion() as conn:
        return conn.execute("SELECT 1 FROM analyses LIMIT 1").fetchone() is None


def _estado_inicial(semaforo: Semaforo) -> EstadoRevision:
    return EstadoRevision.AUTO_APROBADO if semaforo == Semaforo.VERDE else EstadoRevision.PENDIENTE_REVISION


def guardar_analisis(resultado: ResultadoAnalisis) -> OrderAnalysisResponse:
    docs = resultado.documentos.values()
    documentos = [
        DocumentoResumen(
            tipo=d.tipo.value,
            proveedor=d.proveedor,
            producto=d.producto.nombre,
            cantidad=d.producto.cantidad,
            fecha=d.fecha,
            confianza=d.confianza,
        )
        for d in docs
    ]
    discrepancias = [DiscrepancyModel.from_discrepancia(d) for d in resultado.discrepancias]
    proveedor = next((d.proveedor for d in docs if d.proveedor), None)
    severidades = "," + ",".join(sorted({d.severidad.value for d in discrepancias})) + ","

    with _conexion() as conn:
        nuevo_id = conn.execute(
            """INSERT INTO analyses (order_id, proveedor, similitud_proveedor, semaforo, estado,
                                     severidades, documentos_json, discrepancias_json, resumen, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                resultado.numero_pedido,
                proveedor,
                similitud_minima([d.proveedor for d in docs]),
                resultado.semaforo.value,
                _estado_inicial(resultado.semaforo).value,
                severidades,
                json.dumps([d.model_dump(mode="json") for d in documentos], ensure_ascii=False),
                json.dumps([d.model_dump(mode="json") for d in discrepancias], ensure_ascii=False),
                resultado.resumen,
                _ahora(),
            ),
        ).fetchone()["id"]
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (nuevo_id,)).fetchone()
    return _a_respuesta(row)


def _a_respuesta(row: sqlite3.Row) -> OrderAnalysisResponse:
    discrepancias = [DiscrepancyModel(**d) for d in json.loads(row["discrepancias_json"])]
    return OrderAnalysisResponse(
        analysis_id=row["id"],
        order_id=row["order_id"],
        status_semaforo=Semaforo(row["semaforo"]),
        estado_revision=EstadoRevision(row["estado"]),
        decision_final=AccionOperador(row["decision"]) if row["decision"] else None,
        proveedor=row["proveedor"],
        similitud_proveedor=row["similitud_proveedor"],
        documentos=[DocumentoResumen(**d) for d in json.loads(row["documentos_json"])],
        total_discrepancies=len(discrepancias),
        items_discrepancias=discrepancias,
        resumen_texto=row["resumen"],
        timestamp=datetime.fromisoformat(row["created_at"]),
    )


def listar(
    estado: Optional[EstadoRevision] = None,
    severidad: Optional[Severidad] = None,
    proveedor: Optional[str] = None,
    q: Optional[str] = None,
) -> List[OrderAnalysisResponse]:
    where, params = [_ULTIMO_POR_PEDIDO], []
    if estado:
        where.append("a.estado = ?")
        params.append(estado.value)
    if severidad:
        where.append("a.severidades LIKE ?")
        params.append(f"%,{severidad.value},%")
    if proveedor:
        where.append("a.proveedor = ?")
        params.append(proveedor)
    if q:
        where.append("a.order_id LIKE ?")
        params.append(f"%{q}%")
    sql = f"SELECT a.* FROM analyses a WHERE {' AND '.join(where)} ORDER BY a.created_at DESC, a.id DESC"
    with _conexion() as conn:
        return [_a_respuesta(r) for r in conn.execute(sql, params).fetchall()]


def obtener(order_id: str) -> Optional[OrderAnalysisDetail]:
    with _conexion() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,)
        ).fetchone()
        if row is None:
            return None
        reviews = conn.execute(
            "SELECT * FROM reviews WHERE order_id = ? ORDER BY id DESC", (order_id,)
        ).fetchall()
    return OrderAnalysisDetail(
        **_a_respuesta(row).model_dump(),
        historial_revisiones=[
            ReviewRecord(
                action_taken=AccionOperador(r["action"]),
                user_notes=r["notes"],
                operator_id=r["operator_id"],
                timestamp=datetime.fromisoformat(r["created_at"]),
            )
            for r in reviews
        ],
    )


def registrar_revision(
    order_id: str, accion: AccionOperador, notas: Optional[str], operador: str
) -> Optional[OrderAnalysisDetail]:
    with _conexion() as conn:
        row = conn.execute(
            "SELECT id FROM analyses WHERE order_id = ? ORDER BY id DESC LIMIT 1", (order_id,)
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """INSERT INTO reviews (analysis_id, order_id, action, notes, operator_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row["id"], order_id, accion.value, notas, operador, _ahora()),
        )
        conn.execute(
            "UPDATE analyses SET estado = ?, decision = ? WHERE id = ?",
            (EstadoRevision.RESUELTO.value, accion.value, row["id"]),
        )
    return obtener(order_id)


def metricas() -> MetricsResponse:
    pedidos = listar()
    total = len(pedidos)
    auto = sum(p.status_semaforo == Semaforo.VERDE for p in pedidos)
    en_cola = sum(p.estado_revision == EstadoRevision.PENDIENTE_REVISION for p in pedidos)

    friccion: Counter = Counter()
    for p in pedidos:
        n = sum(d.campo in CAMPOS_FRICCION for d in p.items_discrepancias)
        if n:
            friccion[p.proveedor or "Desconocido"] += n

    with _conexion() as conn:
        resueltos_hoy = conn.execute(
            "SELECT COUNT(DISTINCT order_id) AS n FROM reviews WHERE substr(created_at, 1, 10) = ?",
            (date.today().isoformat(),),
        ).fetchone()["n"]

    return MetricsResponse(
        total_pedidos=total,
        pct_auto_aprobacion=round(100 * auto / total, 1) if total else 0.0,
        en_cola=en_cola,
        resueltos_hoy=resueltos_hoy,
        top_proveedores=[ProveedorIncidencias(proveedor=k, incidencias=v) for k, v in friccion.most_common(5)],
    )

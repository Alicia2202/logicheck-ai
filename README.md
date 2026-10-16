# LogiCheck AI — Cuadre automático de documentos de pedido

Compara la factura, el albarán y el packing list de un pedido, detecta
discrepancias (cantidades, importes, proveedor, producto, fechas) y
manda a revisión humana solo los pedidos que lo necesitan.

## Cómo ejecutarlo

```bash
cd logicheck-ai
python3 main.py
```

No necesita API key ni red: usa `extract_mock`, un extractor por regex
sobre los documentos de ejemplo en `sample_docs/`, y ejecuta el
pipeline completo end-to-end.

## API REST y dashboard

El script de consola y la API ejecutan **el mismo código**:
`pipeline.analizar()` encadena extractor → comparator → summarizer.
`main.py` lo imprime por consola; `api/main.py` lo guarda en base de
datos y lo expone al dashboard.

```bash
# Backend (desde la raíz del repo)
pip install -r requirements.txt
cp .env.example .env                   # y rellena las claves
uvicorn api.main:app --reload          # http://localhost:8000/docs

# Frontend (otra terminal)
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

En el dashboard, "Procesar nuevo pedido → Usar pedido de ejemplo" lanza
el mismo análisis que `python3 main.py`. También se pueden subir los 3
documentos: `.txt` va al extractor regex; `.pdf`/`.jpg` va a
`extract_with_llm`, que usa Gemini por defecto (`GEMINI_API_KEY`, tiene
plan gratuito) o Claude con `LOGICHECK_LLM=claude` (`ANTHROPIC_API_KEY`).
Las tres extracciones de un pedido se lanzan en paralelo.

### Variables de entorno

En local se leen de `.env` (ver `.env.example`; `.env` no se sube a git).

| Variable | Para qué |
|---|---|
| `GEMINI_API_KEY` | Extracción de PDFs/imágenes con Gemini |
| `LOGICHECK_LLM` | `gemini` (por defecto) o `claude` |
| `ANTHROPIC_API_KEY` | Solo si `LOGICHECK_LLM=claude` |
| `DATABASE_URL` | Postgres (Supabase). Vacía: SQLite en `logicheck.db` |
| `LOGICHECK_DB` | Ruta del fichero SQLite (si no hay `DATABASE_URL`) |
| `LOGICHECK_CORS_ORIGINS` | Orígenes permitidos si el frontend va en otro dominio |

### Endpoints

| Endpoint | Qué hace |
|---|---|
| `POST /api/v1/process-order` | Ejecuta el pipeline. Multipart con `factura`, `albaran`, `packing_list`; sin ficheros usa `sample_docs/` |
| `GET /api/v1/feedbacks` | Último análisis de cada pedido. Filtros: `estado`, `severidad`, `proveedor`, `q` (nº de pedido) |
| `GET /api/v1/feedbacks/{order_id}` | Detalle con discrepancias e historial de revisiones |
| `PUT /api/v1/feedbacks/{order_id}/review` | Decisión del operador: `APPROVE`, `REJECT` o `FALSE_POSITIVE` |
| `GET /api/v1/metrics` | % auto-aprobación, cola, resueltos hoy, top proveedores con incidencias |

**Semáforo y cola de revisión** (`summarizer.semaforo`): 🔴 si hay alguna
discrepancia crítica (bloqueante), 🟠 si hay alguna alta (revisión
recomendada), 🟢 en otro caso. Solo 🔴/🟠 entran en la cola humana; las
discrepancias medias están dentro de tolerancia por definición, así que
se auto-aprueban pero siguen visibles en el detalle.

**Trazabilidad**: reprocesar un pedido crea un análisis nuevo (no pisa
el anterior) y cada decisión humana se añade a un log de revisiones que
nunca se modifica. Si la base de datos está vacía al arrancar, se carga
el pedido de ejemplo para que el dashboard no salga vacío.

## Despliegue en Vercel

Un único proyecto de Vercel sirve API y dashboard en el mismo dominio:
`pyproject.toml` apunta Vercel a `api.main:app` y compila el frontend en
`frontend/dist`, que FastAPI sirve en `/`.

1. Importa el repo en Vercel con la raíz del repo como *Root Directory*
   y elige "Import single project" en la app FastAPI (no *Services*).
2. En *Settings → Environment Variables* añade `GEMINI_API_KEY` y
   `DATABASE_URL`.
3. Despliega.

**Persistencia:** en Vercel la base de datos es Postgres en Supabase
(`DATABASE_URL`, cadena del *Transaction pooler*, puerto 6543). Un
SQLite local no sirve ahí: Vercel reparte las peticiones entre varias
instancias y cada una tendría su propia copia. Las tablas se crean solas
al arrancar, con RLS activado para que la API REST pública de Supabase
no las exponga. Conviene crear el proyecto de Supabase en la misma
región que las funciones de Vercel (por defecto, Washington / us-east).

**Privacidad:** en el plan gratuito de Gemini, Google puede usar los
documentos enviados para mejorar sus productos. No subas documentos
reales de clientes sin pasar al plan de pago.

## Arquitectura (y por qué)

```
Documento (PDF/imagen/texto)
        │
        ▼
  extractor.py   ──► LLM con salida JSON forzada (o regex en el mock)
        │              Responsabilidad única: leer texto no estructurado
        ▼              y devolver una estructura de datos limpia.
DocumentoExtraido (por cada uno de los 3 documentos)
        │
        ▼
  comparator.py  ──► Reglas deterministas en Python, SIN LLM
        │              Responsabilidad única: aplicar lógica de negocio
        │              (tolerancias, qué es crítico, qué es solo formato).
        ▼
  List[Discrepancia]
        │
        ▼
  summarizer.py  ──► Formatea para un humano de operaciones
                       Responsabilidad única: priorizar y comunicar.
```

**Por qué esta separación y no "todo con un prompt al LLM":**

- **Extracción → LLM.** Es la parte con más variabilidad de formato
  (cada proveedor factura distinto, el albarán puede venir escaneado).
  Un LLM con visión absorbe esa variabilidad sin escribir un parser por
  proveedor, y con salida JSON forzada por esquema es fiable.
- **Comparación → reglas de Python, no LLM.** Queremos que sea
  determinista (mismo input → mismo output siempre), auditable
  (alguien puede leer el código y saber exactamente por qué saltó
  una alerta) y barato. Preguntarle a un LLM "¿cuadran estos
  números?" es más lento, más caro, y menos explicable que un `if`.
  El LLM es bueno leyendo; las reglas de negocio las debe definir
  y poder auditar operaciones, no un modelo probabilístico.
- **Resumen → determinista también**, pensado para lectura en
  el móvil en 10 segundos: semáforo único, lo más grave primero,
  y "qué hacer" en cada línea, no solo "qué está mal".

## Discrepancias que detecta

| Campo | Severidad | Lógica |
|---|---|---|
| Número de pedido | 🔴 Crítica | Debe ser idéntico en los 3 (si no, podrían ser pedidos distintos) |
| Cantidad | 🔴 Crítica / 🟡 Media | Tolerancia configurable (2% por defecto); mermas de transporte vs pérdida real |
| Aritmética de factura | 🔴 Crítica | cantidad×precio = base imponible; base+IVA = total |
| Proveedor / Producto | 🟠 Alta si no coinciden ni por similitud de texto | Fuzzy matching (difflib) para absorber variaciones de nombre |
| Fechas | 🟡 Media | Avisa si la factura es posterior a la entrega (facturación diferida o error de fecha) |
| Campos no legibles | ⚪ Info | Transparencia: qué no se pudo extraer con confianza |

## Casos cubiertos por los documentos de ejemplo

1. **"Frutas Hnos. García, S.L."** vs **"Fruta Hermanos Garcia"** vs
   **"Frutas Garcia"** — mismo proveedor, tres formatos de nombre.
   Un `==` los marcaría como error; el fuzzy matching no.
2. **"Tomate Rama Extra"** vs **"Tomate en Rama"** vs **"Tomates Rama"**
   — mismo producto. Mismo razonamiento.
3. **Importe total con IVA (624 €)** vs cantidad×precio (600 €) —
   esto NO se compara entre documentos como si fuera un error;
   se valida la aritmética interna de la factura (base + IVA = total)
   por separado. Comparar "a ciegas" total facturado contra
   cantidad×precio sin contar el IVA sería un falso positivo.
4. **Cantidad 500 kg (factura/albarán) vs 480 kg (packing list)**
   — esta sí es una discrepancia real y queda marcada como crítica.

## Próximos pasos

- Umbrales de tolerancia configurables por categoría de producto
  (no es lo mismo una merma en fruta fresca que en un producto envasado).
- Que el extractor solo marque como "no legibles" los campos que ese
  tipo de documento debería llevar (hoy el albarán y el packing list
  avisan de que no tienen precio ni IVA, que nunca incluyen).
- Autenticación de operadores: hoy el ID de operador es texto libre.
- Tests con documentos reales variados (distintos idiomas, escaneados
  de mala calidad, PDFs generados vs fotografiados).

# Cuadre automático de documentos de pedido — ejercicio Wikifarmer

## Cómo ejecutarlo

```bash
cd logiccheck-ai
python3 main.py
```

No necesita API key ni red: usa `extract_mock`, un extractor por regex
sobre los documentos de ejemplo en `sample_docs/`, para poder practicar
el pipeline completo end-to-end.

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
  Un LLM con visión es lo único razonable de construir en el tiempo
  disponible, y con salida JSON forzada es fiable.
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
| Fechas | 🟡 Media | Validación de orden lógico (factura no debería preceder a la entrega) |
| Campos no legibles | ⚪ Info | Transparencia: qué no se pudo extraer con confianza |

## Trampas incluidas a propósito en los documentos de ejemplo

1. **"Frutas Hnos. García, S.L."** vs **"Fruta Hermanos Garcia"** vs
   **"Frutas Garcia"** — mismo proveedor, tres formatos de nombre.
   Un `==` los marcaría como error; el fuzzy matching no.
2. **"Tomate Rama"** vs **"Tomates rama"** vs **"Tomate Rama Extra"**
   — mismo producto. Mismo razonamiento.
3. **Importe total con IVA (624 €)** vs cantidad×precio (600 €) —
   esto NO se compara entre documentos como si fuera un error;
   se valida la aritmética interna de la factura (base + IVA = total)
   por separado. Comparar "a ciegas" total facturado contra
   cantidad×precio sin contar el IVA sería un falso positivo.
4. **Cantidad 500 kg (factura/albarán) vs 480 kg (packing list)**
   — esta sí es una discrepancia real y queda marcada como crítica.

## Qué le falta para producción (para si te preguntan "¿y cómo lo escalarías?")

- Cola de revisión humana **solo** para los casos 🔴/🟠, no para todos
  (los 🟢 se auto-aprueban).
- Persistir cada extracción y decisión para trazabilidad/auditoría.
- Métricas de calidad del extractor (campos no legibles por proveedor)
  para detectar qué proveedores generan más fricción.
- Umbrales de tolerancia configurables por categoría de producto
  (no es lo mismo una merma en fruta fresca que en un producto envasado).
- Tests con documentos reales variados (distintos idiomas, escaneados
  de mala calidad, PDFs generados vs fotografiados).

## Cómo presentarlo en la entrevista

1. Empieza por el diagrama de arquitectura y el "por qué" de cada capa
   (arriba) — antes de enseñar código. Es lo que más peso tiene.
2. Ejecuta `main.py` en vivo y enseña el caso con discrepancia real.
3. Enseña brevemente `comparator.py` y explica 2-3 reglas con su
   razonamiento (especialmente la del IVA — es la que demuestra que
   entiendes el dominio, no solo que sabes comparar números).
4. Cierra con la sección "qué le falta para producción" — muestra que
   sabes que esto es un prototipo razonado, no una solución completa,
   y que piensas en escala y operación real.

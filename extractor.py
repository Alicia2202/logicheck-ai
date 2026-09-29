"""
Extracción de campos clave de cada documento.

Este módulo tiene DOS implementaciones a propósito:

1. extract_mock(): parsea texto plano con regex. Sirve para practicar
   el pipeline completo sin depender de red ni de una API key, y deja
   claro qué campos se están buscando.

2. extract_with_claude(): la versión real que usarías el día de la
   entrevista, con PDFs/imágenes de verdad y salida JSON forzada.
   Requiere ANTHROPIC_API_KEY y el SDK `anthropic` instalado.

En ambos casos la salida es un DocumentoExtraido, así el resto del
pipeline (comparator.py) no sabe ni le importa cómo se extrajo.
"""

import re
from typing import Optional

from models import DocumentoExtraido, ProductoExtraido, TipoDocumento


def _parse_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    raw = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    try:
        return float(raw)
    except ValueError:
        return None


def _find(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def extract_mock(text: str, tipo: TipoDocumento) -> DocumentoExtraido:
    """
    Extractor basado en reglas para los documentos de ejemplo de este
    ejercicio. En un caso real esto NO escala (cada proveedor tiene su
    propio formato) — por eso en producción usaríamos extract_with_claude.
    Aquí sirve para poder ejecutar y entender el pipeline sin red.
    """
    campos_no_legibles = []

    numero_pedido = _find(r"(?:Número de pedido|Pedido asociado)[:\s]+([A-Z0-9\-]+)", text)
    proveedor = _find(r"Proveedor[:\s]+(.+)", text)
    fecha_raw = _find(r"(?:Fecha factura|Fecha de entrega|Fecha de recepción)[:\s]+(\d{4}-\d{2}-\d{2})", text)

    nombre_prod = _find(r"(?:Producto|Mercancía)[:\s]+(.+)", text)
    cantidad_raw = _find(r"Cantidad(?:\s+entregada|\s+recibida)?[:\s]+([\d\.,]+)\s*kg", text)
    precio_raw = _find(r"Precio unitario[:\s]+([\d\.,]+)", text)
    base_raw = _find(r"Base imponible[:\s]+([\d\.,]+)", text)
    iva_raw = _find(r"IVA\s*\(([\d\.,]+)%\)", text)
    total_raw = _find(r"Importe total[:\s]+([\d\.,]+)", text)

    if not numero_pedido:
        campos_no_legibles.append("numero_pedido")
    if not nombre_prod:
        campos_no_legibles.append("producto")
    if not cantidad_raw:
        campos_no_legibles.append("cantidad")

    producto = ProductoExtraido(
        nombre=nombre_prod,
        cantidad=_parse_float(cantidad_raw),
        unidad="kg" if cantidad_raw else None,
        precio_unitario=_parse_float(precio_raw),
        base_imponible=_parse_float(base_raw),
        iva_pct=_parse_float(iva_raw),
        importe_total=_parse_float(total_raw),
    )

    return DocumentoExtraido(
        tipo=tipo,
        numero_pedido=numero_pedido,
        proveedor=proveedor,
        fecha=fecha_raw,
        producto=producto,
        campos_no_legibles=campos_no_legibles,
        confianza="alta" if not campos_no_legibles else "media",
    )


# ---------------------------------------------------------------------------
# Versión real con Claude, para usar el día de la entrevista con PDFs/fotos
# de verdad. No se ejecuta en este entorno de práctica (sin red / sin key),
# pero así es como la conectarías.
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """Eres un motor de extracción de datos de documentos logísticos.
Vas a recibir un documento (factura, albarán o packing list) de un pedido.
Devuelve ÚNICAMENTE un JSON con este esquema exacto, sin texto adicional:

{
  "numero_pedido": string|null,
  "proveedor": string|null,
  "fecha": string|null,        // YYYY-MM-DD
  "producto": {
    "nombre": string|null,
    "cantidad": number|null,
    "unidad": string|null,
    "precio_unitario": number|null,
    "base_imponible": number|null,
    "iva_pct": number|null,
    "importe_total": number|null
  },
  "campos_no_legibles": string[],   // campos que NO pudiste leer con confianza
  "confianza": "alta"|"media"|"baja"
}

Reglas importantes:
- Si un campo no aparece en el documento o no estás seguro, ponlo en null
  y añádelo a "campos_no_legibles". NUNCA inventes un valor.
- Normaliza fechas a YYYY-MM-DD y números a formato decimal con punto.
- No añadas explicaciones fuera del JSON.
"""


def extract_with_claude(file_path: str, tipo: TipoDocumento) -> DocumentoExtraido:
    """
    Extracción real usando la API de Claude con un PDF o imagen.
    Requiere: pip install anthropic ; export ANTHROPIC_API_KEY=...
    """
    import base64
    import json
    import anthropic

    client = anthropic.Anthropic()

    with open(file_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    media_type = "application/pdf" if file_path.lower().endswith(".pdf") else "image/jpeg"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document" if media_type == "application/pdf" else "image",
                 "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": f"Tipo de documento: {tipo.value}. Extrae los campos."}
            ],
        }],
    )

    raw_text = "".join(b.text for b in response.content if b.type == "text")
    raw_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
    parsed = json.loads(raw_text)

    producto = ProductoExtraido(**parsed["producto"])
    return DocumentoExtraido(
        tipo=tipo,
        numero_pedido=parsed.get("numero_pedido"),
        proveedor=parsed.get("proveedor"),
        fecha=parsed.get("fecha"),
        producto=producto,
        campos_no_legibles=parsed.get("campos_no_legibles", []),
        confianza=parsed.get("confianza", "media"),
    )

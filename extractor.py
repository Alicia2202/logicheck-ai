"""
Extracción de campos clave de cada documento.

Este módulo tiene DOS implementaciones a propósito:

1. extract_mock(): parsea texto plano con regex. Sirve para practicar
   el pipeline completo sin depender de red ni de una API key, y deja
   claro qué campos se están buscando.

2. extract_with_llm(): la versión real, con PDFs/imágenes de verdad y
   salida JSON forzada. El proveedor se elige con LOGICHECK_LLM:
   "gemini" (por defecto, tiene plan gratuito; requiere GEMINI_API_KEY)
   o "claude" (requiere ANTHROPIC_API_KEY).

En ambos casos la salida es un DocumentoExtraido, así el resto del
pipeline (comparator.py) no sabe ni le importa cómo se extrajo.
"""

import base64
import json
import os
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
    propio formato) — por eso en producción usaríamos extract_with_llm.
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
# Versión real con un LLM con visión (Gemini o Claude). Ambos proveedores
# comparten prompt y parseo; solo cambia la llamada a la API.
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


def _nullable(tipo: str) -> dict:
    return {"type": [tipo, "null"]}


# El mismo esquema que describe EXTRACTION_SYSTEM_PROMPT. Gemini lo exige
# para devolver JSON y además garantiza que la respuesta lo cumple.
EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "numero_pedido": _nullable("string"),
        "proveedor": _nullable("string"),
        "fecha": _nullable("string"),
        "producto": {
            "type": "object",
            "properties": {
                "nombre": _nullable("string"),
                "cantidad": _nullable("number"),
                "unidad": _nullable("string"),
                "precio_unitario": _nullable("number"),
                "base_imponible": _nullable("number"),
                "iva_pct": _nullable("number"),
                "importe_total": _nullable("number"),
            },
            "required": ["nombre", "cantidad", "unidad", "precio_unitario",
                         "base_imponible", "iva_pct", "importe_total"],
        },
        "campos_no_legibles": {"type": "array", "items": {"type": "string"}},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
    },
    "required": ["numero_pedido", "proveedor", "fecha", "producto", "campos_no_legibles", "confianza"],
}

GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_TIMEOUT_S = 100
CLAUDE_MODEL = "claude-sonnet-4-6"


def _media_type(file_path: str) -> str:
    return "application/pdf" if file_path.lower().endswith(".pdf") else "image/jpeg"


def _leer_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _instruccion(tipo: TipoDocumento) -> str:
    return f"Tipo de documento: {tipo.value}. Extrae los campos."


def _documento_desde_json(raw_text: str, tipo: TipoDocumento) -> DocumentoExtraido:
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


def extract_with_gemini(file_path: str, tipo: TipoDocumento) -> DocumentoExtraido:
    """
    Extracción real usando la API de Gemini con un PDF o imagen.
    Requiere: pip install google-genai ; GEMINI_API_KEY=...
    """
    from google import genai

    client = genai.Client()
    media_type = _media_type(file_path)

    interaction = client.interactions.create(
        model=os.environ.get("GEMINI_MODEL", GEMINI_MODEL),
        system_instruction=EXTRACTION_SYSTEM_PROMPT,
        input=[
            {"type": "document" if media_type == "application/pdf" else "image",
             "data": _leer_base64(file_path), "mime_type": media_type},
            {"type": "text", "text": _instruccion(tipo)},
        ],
        response_format={"type": "text", "mime_type": "application/json", "schema": EXTRACTION_JSON_SCHEMA},
        # Copiar campos de un documento no requiere razonar; con más
        # "thinking" solo se gana latencia.
        generation_config={"thinking_level": "low"},
        # Por defecto Gemini guarda la interacción en sus servidores; aquí
        # no hay conversación que continuar, así que no tiene sentido.
        store=False,
        # Por debajo del maxDuration de vercel.json: mejor un error con
        # mensaje que un 504 genérico de Vercel.
        timeout=GEMINI_TIMEOUT_S,
    )
    return _documento_desde_json(interaction.output_text or "", tipo)


def extract_with_claude(file_path: str, tipo: TipoDocumento) -> DocumentoExtraido:
    """
    Extracción real usando la API de Claude con un PDF o imagen.
    Requiere: pip install anthropic ; ANTHROPIC_API_KEY=...
    """
    import anthropic

    client = anthropic.Anthropic()
    media_type = _media_type(file_path)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document" if media_type == "application/pdf" else "image",
                 "source": {"type": "base64", "media_type": media_type, "data": _leer_base64(file_path)}},
                {"type": "text", "text": _instruccion(tipo)}
            ],
        }],
    )
    return _documento_desde_json("".join(b.text for b in response.content if b.type == "text"), tipo)


EXTRACTORES_LLM = {"gemini": extract_with_gemini, "claude": extract_with_claude}


def extract_with_llm(file_path: str, tipo: TipoDocumento) -> DocumentoExtraido:
    proveedor = os.environ.get("LOGICHECK_LLM", "gemini").lower()
    if proveedor not in EXTRACTORES_LLM:
        raise ValueError(f"LOGICHECK_LLM='{proveedor}' no válido. Usa uno de {sorted(EXTRACTORES_LLM)}.")
    return EXTRACTORES_LLM[proveedor](file_path, tipo)

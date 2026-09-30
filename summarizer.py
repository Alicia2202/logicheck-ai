"""
Convierte la lista de discrepancias en algo que una persona de
operaciones pueda leer en 10 segundos desde el móvil.

Principio de diseño: severidad más grave primero, un semáforo
único al principio, y "qué hacer" en cada línea — no solo "qué falla".
"""

from typing import List

from models import Discrepancia, Semaforo, Severidad

ORDEN_SEVERIDAD = {
    Severidad.CRITICA: 0,
    Severidad.ALTA: 1,
    Severidad.MEDIA: 2,
    Severidad.INFO: 3,
}

EMOJI_SEVERIDAD = {
    Severidad.CRITICA: "🔴",
    Severidad.ALTA: "🟠",
    Severidad.MEDIA: "🟡",
    Severidad.INFO: "⚪️",
}


def _estado_global(discrepancias: List[Discrepancia]) -> str:
    severidades = {d.severidad for d in discrepancias}
    if Severidad.CRITICA in severidades:
        return "🔴 REQUIERE ACCIÓN — no cerrar el pedido sin revisar"
    if Severidad.ALTA in severidades:
        return "🟠 REVISAR — probable error, verificar antes de cerrar"
    if Severidad.MEDIA in severidades:
        return "🟡 VIGILAR — dentro de tolerancia, sin acción urgente"
    return "🟢 OK — los 3 documentos cuadran"


def semaforo(discrepancias: List[Discrepancia]) -> Semaforo:
    """
    Solo CRITICA y ALTA mandan el pedido a la cola de revisión humana.
    MEDIA está dentro de tolerancia por definición: se auto-aprueba y
    queda visible en el detalle, pero no le quita tiempo a nadie.
    """
    severidades = {d.severidad for d in discrepancias}
    if Severidad.CRITICA in severidades:
        return Semaforo.ROJO
    if Severidad.ALTA in severidades:
        return Semaforo.AMARILLO
    return Semaforo.VERDE


def generar_resumen(numero_pedido: str, discrepancias: List[Discrepancia]) -> str:
    lineas = [f"PEDIDO {numero_pedido}", _estado_global(discrepancias), ""]

    relevantes = [d for d in discrepancias if d.severidad != Severidad.INFO]
    informativas = [d for d in discrepancias if d.severidad == Severidad.INFO]

    if not relevantes and not informativas:
        lineas.append("Sin discrepancias. Número de pedido, proveedor, producto,")
        lineas.append("cantidad e importes coinciden en factura, albarán y packing list.")
        return "\n".join(lineas)

    relevantes.sort(key=lambda d: ORDEN_SEVERIDAD[d.severidad])

    for d in relevantes:
        emoji = EMOJI_SEVERIDAD[d.severidad]
        lineas.append(f"{emoji} [{d.campo.upper()}] {d.mensaje}")
        for doc, val in d.valores.items():
            lineas.append(f"     · {doc}: {val}")
        lineas.append(f"     → Acción: {d.accion_sugerida}")
        lineas.append("")

    if informativas:
        lineas.append("Notas (no bloquean el pedido):")
        for d in informativas:
            lineas.append(f"  {EMOJI_SEVERIDAD[d.severidad]} {d.mensaje}")

    return "\n".join(lineas)

"""
Orquestador del pipeline: extrae los 3 documentos, los compara
y genera el resumen para operaciones.

Uso:
    python3 main.py
"""

import sys
from pathlib import Path

from extractor import extract_mock
from comparator import comparar_pedido
from summarizer import generar_resumen
from models import TipoDocumento

# El resumen usa emojis (🔴🟠🟡🟢) y la consola de Windows suele venir en
# cp1252, que no puede codificarlos: print() lanzaría UnicodeEncodeError
# antes de que el usuario vea una sola línea. Forzamos utf-8 en stdout.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Rutas ancladas a la ubicación de este script, no al directorio desde el
# que se ejecute python. Así "python3 main.py" funciona siempre, vengas
# de donde vengas (esta es una causa muy común de FileNotFoundError).
BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DOCS_DIR = BASE_DIR / "sample_docs"


def cargar_texto(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    factura_txt = cargar_texto(SAMPLE_DOCS_DIR / "factura_4521.txt")
    albaran_txt = cargar_texto(SAMPLE_DOCS_DIR / "albaran_4521.txt")
    packing_txt = cargar_texto(SAMPLE_DOCS_DIR / "packing_list_4521.txt")

    factura = extract_mock(factura_txt, TipoDocumento.FACTURA)
    albaran = extract_mock(albaran_txt, TipoDocumento.ALBARAN)
    packing = extract_mock(packing_txt, TipoDocumento.PACKING_LIST)

    print("=== Extracción ===")
    for d in (factura, albaran, packing):
        print(f"{d.tipo.value}: pedido={d.numero_pedido} proveedor={d.proveedor!r} "
              f"producto={d.producto.nombre!r} cantidad={d.producto.cantidad} "
              f"confianza={d.confianza}")
    print()

    discrepancias = comparar_pedido(factura, albaran, packing)

    print("=== Resumen para operaciones ===\n")
    print(generar_resumen(factura.numero_pedido or "DESCONOCIDO", discrepancias))


if __name__ == "__main__":
    main()

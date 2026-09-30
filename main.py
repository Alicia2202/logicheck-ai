"""
Orquestador del pipeline: extrae los 3 documentos, los compara
y genera el resumen para operaciones.

Uso:
    python3 main.py

La misma lógica está expuesta como API REST en api/main.py
(ver README, sección "API REST y dashboard").
"""

import sys

from pipeline import analizar, documentos_de_ejemplo

# El resumen usa emojis (🔴🟠🟡🟢) y la consola de Windows suele venir en
# cp1252, que no puede codificarlos: print() lanzaría UnicodeEncodeError
# antes de que el usuario vea una sola línea. Forzamos utf-8 en stdout.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Las rutas a sample_docs/ se anclan a la ubicación del código (ver
# pipeline.py), no al directorio desde el que se ejecute python.


def main():
    resultado = analizar(documentos_de_ejemplo("4521"))

    print("=== Extracción ===")
    for d in resultado.documentos.values():
        print(f"{d.tipo.value}: pedido={d.numero_pedido} proveedor={d.proveedor!r} "
              f"producto={d.producto.nombre!r} cantidad={d.producto.cantidad} "
              f"confianza={d.confianza}")
    print()

    print("=== Resumen para operaciones ===\n")
    print(resultado.resumen)


if __name__ == "__main__":
    main()

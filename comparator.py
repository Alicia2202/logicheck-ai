"""
Comparación de los tres documentos ya extraídos.

Decisión de diseño (importante para defender en la entrevista):
esta capa es 100% determinista, NO vuelve a llamar a un LLM.
¿Por qué? Porque:
  - Queremos que el resultado sea reproducible y auditable
    (si dos veces comparas lo mismo, el resultado no puede cambiar).
  - Las reglas de negocio (tolerancias, qué es crítico) las define
    operaciones, no un modelo probabilístico.
  - Es mucho más barato y rápido que otra llamada a un LLM.
El LLM se usa solo donde de verdad hace falta: leer texto no estructurado
(extractor.py) y, opcionalmente, para el matching difuso de nombres de
producto si difflib se queda corto (aquí no ha hecho falta).
"""

import difflib
import unicodedata
from typing import List, Optional

from models import Discrepancia, DocumentoExtraido, Severidad

TOLERANCIA_CANTIDAD_PCT = 2.0     # % de diferencia de cantidad aceptable
TOLERANCIA_IMPORTE_EUR = 0.05     # error de redondeo aceptable en euros
UMBRAL_SIMILITUD_TEXTO = 0.55     # por debajo de esto, dos nombres se consideran distintos


def _normalizar(texto: Optional[str]) -> str:
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    for palabra in ["s.l.", "sl", "s.a.", "sa", "extra", "primera", "categoria i"]:
        texto = texto.replace(palabra, "")
    return " ".join(texto.split())


def _similitud(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalizar(a), _normalizar(b)).ratio()


def similitud_minima(nombres: List[Optional[str]]) -> Optional[float]:
    """Peor similitud del primer nombre contra el resto (None si hay menos de 2)."""
    valores = [v for v in nombres if v]
    if len(valores) < 2:
        return None
    return min(_similitud(valores[0], v) for v in valores[1:])


def comparar_pedido(
    factura: DocumentoExtraido,
    albaran: DocumentoExtraido,
    packing_list: DocumentoExtraido,
) -> List[Discrepancia]:
    discrepancias: List[Discrepancia] = []
    docs = {"factura": factura, "albaran": albaran, "packing_list": packing_list}

    # 1. Número de pedido: debe ser idéntico en los tres. Si no, nada más
    #    tiene sentido compararse: podríamos estar mezclando pedidos distintos.
    numeros = {k: d.numero_pedido for k, d in docs.items()}
    if len(set(v for v in numeros.values() if v)) > 1:
        discrepancias.append(Discrepancia(
            campo="numero_pedido",
            severidad=Severidad.CRITICA,
            mensaje="Los documentos referencian números de pedido distintos.",
            valores=numeros,
            accion_sugerida="Verificar que los 3 documentos pertenecen al mismo pedido antes de continuar.",
        ))

    # 2. Proveedor: nombres casi nunca coinciden literalmente
    #    (razón social vs nombre comercial), así que usamos similitud de texto.
    proveedores = {k: d.proveedor for k, d in docs.items()}
    sim_min = similitud_minima(list(proveedores.values()))
    if sim_min is not None:
        if sim_min < UMBRAL_SIMILITUD_TEXTO:
            discrepancias.append(Discrepancia(
                campo="proveedor",
                severidad=Severidad.ALTA,
                mensaje="Los nombres de proveedor son demasiado distintos entre documentos.",
                valores=proveedores,
                accion_sugerida="Confirmar con el proveedor que es el mismo remitente en los 3 documentos.",
            ))

    # 3. Producto: igual que proveedor, esperamos variación de nombre
    #    ("Tomate Rama" vs "Tomate Rama Extra" vs "Tomates rama").
    productos = {k: d.producto.nombre for k, d in docs.items()}
    sim_min = similitud_minima(list(productos.values()))
    if sim_min is not None:
        if sim_min < UMBRAL_SIMILITUD_TEXTO:
            discrepancias.append(Discrepancia(
                campo="producto",
                severidad=Severidad.ALTA,
                mensaje="Los nombres de producto no parecen referirse al mismo artículo.",
                valores=productos,
                accion_sugerida="Revisar visualmente si se trata del mismo producto o hay un envío cruzado.",
            ))
        elif sim_min < 0.95:
            discrepancias.append(Discrepancia(
                campo="producto",
                severidad=Severidad.INFO,
                mensaje="Nombres de producto con variación de formato, pero parecen el mismo artículo.",
                valores=productos,
                accion_sugerida="Ninguna. Diferencia de nomenclatura entre proveedor y almacén.",
            ))

    # 4. Cantidad: aquí sí toleramos un margen pequeño (mermas de transporte),
    #    pero por encima del umbral es dinero perdido real.
    cantidades = {k: d.producto.cantidad for k, d in docs.items() if d.producto.cantidad is not None}
    if len(cantidades) >= 2:
        valores_cant = list(cantidades.values())
        max_v, min_v = max(valores_cant), min(valores_cant)
        diff_pct = ((max_v - min_v) / max_v) * 100 if max_v else 0
        if diff_pct > TOLERANCIA_CANTIDAD_PCT:
            discrepancias.append(Discrepancia(
                campo="cantidad",
                severidad=Severidad.CRITICA,
                mensaje=f"Diferencia de cantidad del {diff_pct:.1f}%, por encima del {TOLERANCIA_CANTIDAD_PCT}% tolerado.",
                valores=cantidades,
                accion_sugerida="Contactar con almacén para confirmar la cantidad realmente recibida y abrir incidencia con el transportista si procede.",
            ))
        elif diff_pct > 0:
            discrepancias.append(Discrepancia(
                campo="cantidad",
                severidad=Severidad.MEDIA,
                mensaje=f"Diferencia de cantidad del {diff_pct:.1f}%, dentro de tolerancia pero a vigilar.",
                valores=cantidades,
                accion_sugerida="Sin acción inmediata. Vigilar si se repite con este proveedor/transportista.",
            ))

    # 5. Aritmética interna de la factura: cantidad x precio debe cuadrar
    #    con la base imponible, y base + IVA con el importe total.
    #    Esto NO se compara entre documentos, es una validación interna.
    p = factura.producto
    if p.cantidad is not None and p.precio_unitario is not None and p.base_imponible is not None:
        calculado = round(p.cantidad * p.precio_unitario, 2)
        if abs(calculado - p.base_imponible) > TOLERANCIA_IMPORTE_EUR:
            discrepancias.append(Discrepancia(
                campo="importe_factura",
                severidad=Severidad.CRITICA,
                mensaje=f"Cantidad × precio unitario ({calculado} €) no coincide con la base imponible facturada ({p.base_imponible} €).",
                valores={"calculado": calculado, "base_imponible_factura": p.base_imponible},
                accion_sugerida="Revisar la factura con el proveedor, puede haber un error de facturación.",
            ))

    if p.base_imponible is not None and p.iva_pct is not None and p.importe_total is not None:
        calculado_total = round(p.base_imponible * (1 + p.iva_pct / 100), 2)
        if abs(calculado_total - p.importe_total) > TOLERANCIA_IMPORTE_EUR:
            discrepancias.append(Discrepancia(
                campo="importe_total_factura",
                severidad=Severidad.CRITICA,
                mensaje=f"Base imponible + IVA ({calculado_total} €) no coincide con el importe total facturado ({p.importe_total} €).",
                valores={"calculado": calculado_total, "importe_total_factura": p.importe_total},
                accion_sugerida="Revisar el cálculo de IVA en la factura antes de aprobar el pago.",
            ))

    # 6. Fechas: solo una validación de orden lógico, informativa.
    if factura.fecha and albaran.fecha and factura.fecha > albaran.fecha:
        discrepancias.append(Discrepancia(
            campo="fechas",
            severidad=Severidad.MEDIA,
            mensaje="La fecha de la factura es posterior a la fecha de entrega.",
            valores={"fecha_factura": factura.fecha, "fecha_entrega": albaran.fecha},
            accion_sugerida="Revisar si es facturación diferida habitual con este proveedor o un error de fecha.",
        ))

    # 7. Campos que ningún documento pudo extraer con confianza:
    #    esto no es una discrepancia entre documentos, pero operaciones
    #    debe saber que hay puntos ciegos en los datos.
    for k, d in docs.items():
        if d.campos_no_legibles:
            discrepancias.append(Discrepancia(
                campo="calidad_extraccion",
                severidad=Severidad.INFO,
                mensaje=f"En el documento '{k}' no se pudieron leer con confianza: {', '.join(d.campos_no_legibles)}.",
                valores={k: d.campos_no_legibles},
                accion_sugerida="Revisar manualmente esos campos si son relevantes para el cuadre.",
            ))

    return discrepancias

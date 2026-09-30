// Vocabulario compartido entre la card y el dashboard. Espeja los enums
// de models.py / api/schemas.py: si cambian allí, cambian aquí.

export const SEVERIDADES = {
  critica: { emoji: "🔴", label: "Crítica", orden: 0, card: "border-red-200 bg-red-50", chip: "bg-red-100 text-red-800" },
  alta: { emoji: "🟠", label: "Alta", orden: 1, card: "border-orange-200 bg-orange-50", chip: "bg-orange-100 text-orange-800" },
  media: { emoji: "🟡", label: "Media", orden: 2, card: "border-amber-200 bg-amber-50", chip: "bg-amber-100 text-amber-800" },
  info: { emoji: "⚪", label: "Info", orden: 3, card: "border-slate-200 bg-white", chip: "bg-slate-100 text-slate-700" },
};

export const SEMAFORO = {
  verde: { label: "Auto-aprobado", detalle: "Los 3 documentos cuadran", lamp: "bg-emerald-500", text: "text-emerald-700" },
  amarillo: { label: "Revisión recomendada", detalle: "Probable error, verificar antes de cerrar", lamp: "bg-amber-400", text: "text-amber-700" },
  rojo: { label: "Bloqueante", detalle: "No cerrar el pedido sin revisar", lamp: "bg-red-500", text: "text-red-700" },
};

export const ESTADOS = {
  AUTO_APROBADO: { label: "Auto-aprobado", emoji: "🟢", chip: "bg-emerald-100 text-emerald-800" },
  PENDIENTE_REVISION: { label: "En cola", emoji: "⏳", chip: "bg-amber-100 text-amber-800" },
  RESUELTO: { label: "Resuelto", emoji: "✔", chip: "bg-slate-200 text-slate-800" },
};

export const ACCIONES = {
  APPROVE: "Aprobado",
  REJECT: "Rechazado / escalado",
  FALSE_POSITIVE: "Falso positivo",
};

export const DOCUMENTOS = {
  factura: "Factura",
  albaran: "Albarán",
  packing_list: "Packing List",
};

const ETIQUETAS_VALOR = {
  ...DOCUMENTOS,
  calculado: "Calculado",
  base_imponible_factura: "Base facturada",
  importe_total_factura: "Total facturado",
  fecha_factura: "Fecha factura",
  fecha_entrega: "Fecha entrega",
};

export const etiquetaValor = (clave) => ETIQUETAS_VALOR[clave] ?? clave;

export function formatValor(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (Array.isArray(valor)) return valor.join(", ");
  if (typeof valor === "number") return valor.toLocaleString("es-ES", { maximumFractionDigits: 2 });
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}

export const formatFecha = (iso) =>
  new Date(iso).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" });

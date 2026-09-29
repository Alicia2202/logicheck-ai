// Cliente mínimo de la API REST (ver api/main.py).
const BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `Error ${res.status}`;
    throw new Error(detail);
  }
  return body;
}

export function listOrders({ estado, severidad, proveedor, q } = {}) {
  const params = new URLSearchParams();
  if (estado) params.set("estado", estado);
  if (severidad) params.set("severidad", severidad);
  if (proveedor) params.set("proveedor", proveedor);
  if (q) params.set("q", q);
  const qs = params.toString();
  return request(`/feedbacks${qs ? `?${qs}` : ""}`);
}

export const getOrder = (orderId) => request(`/feedbacks/${encodeURIComponent(orderId)}`);

export const getMetrics = () => request("/metrics");

// files: { factura, albaran, packing_list } (File) o null para usar los documentos de ejemplo.
export function processOrder(files = null) {
  const form = new FormData();
  if (files) Object.entries(files).forEach(([tipo, file]) => form.append(tipo, file));
  return request("/process-order", { method: "POST", body: form });
}

export function reviewOrder(orderId, { action, notes, operatorId }) {
  return request(`/feedbacks/${encodeURIComponent(orderId)}/review`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_taken: action, user_notes: notes || null, operator_id: operatorId }),
  });
}

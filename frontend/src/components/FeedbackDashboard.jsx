import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "../api.js";
import { ESTADOS, SEMAFORO, SEVERIDADES, formatFecha } from "../constants.js";
import DiscrepancyCard from "./DiscrepancyCard.jsx";

const PESTANAS = [
  { id: "", label: "Todos" },
  { id: "PENDIENTE_REVISION", label: "En cola de revisión", hint: "🔴/🟠" },
  { id: "AUTO_APROBADO", label: "Auto-aprobados", hint: "🟢" },
  { id: "RESUELTO", label: "Resueltos" },
];

/**
 * Historial de pedidos procesados + cola de revisión humana.
 * Solo los 🔴/🟠 llegan a la cola; los 🟢 se auto-aprueban.
 */
export default function FeedbackDashboard() {
  const [pedidos, setPedidos] = useState([]);
  const [todos, setTodos] = useState([]); // sin filtrar: opciones de proveedor y contadores
  const [metricas, setMetricas] = useState(null);
  const [filtros, setFiltros] = useState({ estado: "PENDIENTE_REVISION", proveedor: "", q: "" });
  const [busqueda, setBusqueda] = useState("");
  const [seleccionado, setSeleccionado] = useState(null);
  const [operador, setOperador] = useState(() => localStorage.getItem("logicheck.operador") ?? "");
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(null);

  // Debounce de la búsqueda por número de pedido.
  useEffect(() => {
    const t = setTimeout(() => setFiltros((f) => ({ ...f, q: busqueda.trim() })), 250);
    return () => clearTimeout(t);
  }, [busqueda]);

  useEffect(() => {
    localStorage.setItem("logicheck.operador", operador);
  }, [operador]);

  const recargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [filtrados, sinFiltro, m] = await Promise.all([
        api.listOrders(filtros),
        api.listOrders(),
        api.getMetrics(),
      ]);
      setPedidos(filtrados);
      setTodos(sinFiltro);
      setMetricas(m);
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, [filtros]);

  useEffect(() => {
    recargar();
  }, [recargar]);

  // Enlace directo a un pedido (?pedido=4521), p. ej. desde una alerta.
  useEffect(() => {
    const pedido = new URLSearchParams(window.location.search).get("pedido");
    if (pedido) abrir(pedido);
  }, []);

  const proveedores = useMemo(
    () => [...new Set(todos.map((p) => p.proveedor).filter(Boolean))].sort(),
    [todos],
  );
  const contadores = useMemo(() => {
    const c = { "": todos.length };
    todos.forEach((p) => (c[p.estado_revision] = (c[p.estado_revision] ?? 0) + 1));
    return c;
  }, [todos]);

  async function abrir(orderId) {
    setError(null);
    try {
      setSeleccionado(await api.getOrder(orderId));
    } catch (e) {
      setError(e.message);
    }
  }

  async function procesar(files) {
    setError(null);
    try {
      const nuevo = await api.processOrder(files);
      await recargar();
      await abrir(nuevo.order_id);
    } catch (e) {
      setError(e.message);
    }
  }

  async function revisar(action, notes) {
    if (!operador.trim()) {
      setError("Indica tu ID de operador antes de registrar una decisión.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      setSeleccionado(await api.reviewOrder(seleccionado.order_id, { action, notes, operatorId: operador.trim() }));
      await recargar();
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cuadre de pedidos</h1>
          <p className="text-sm text-slate-600">Factura · Albarán · Packing List</p>
        </div>
        <label className="text-sm">
          <span className="block text-xs text-slate-500">ID de operador</span>
          <input
            value={operador}
            onChange={(e) => setOperador(e.target.value)}
            placeholder="p. ej. ana.lopez"
            className="w-48 rounded-lg border border-slate-300 bg-white px-3 py-1.5"
          />
        </label>
      </header>

      {error && (
        <div role="alert" className="flex items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="font-semibold" aria-label="Cerrar aviso">✕</button>
        </div>
      )}

      <PanelMetricas metricas={metricas} />

      <ProcesarPedido onProcesar={procesar} />

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-4 lg:flex-row lg:items-center lg:justify-between">
          <nav className="flex flex-wrap gap-1" aria-label="Filtrar por estado">
            {PESTANAS.map((p) => (
              <button
                key={p.id}
                onClick={() => setFiltros((f) => ({ ...f, estado: p.id }))}
                aria-pressed={filtros.estado === p.id}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${filtros.estado === p.id ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}
              >
                {p.hint && <span className="mr-1">{p.hint}</span>}
                {p.label}
                <span className="ml-1.5 opacity-70">{contadores[p.id] ?? 0}</span>
              </button>
            ))}
          </nav>
          <div className="flex flex-col gap-2 sm:flex-row">
            <select
              value={filtros.proveedor}
              onChange={(e) => setFiltros((f) => ({ ...f, proveedor: e.target.value }))}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm"
              aria-label="Filtrar por proveedor"
            >
              <option value="">Todos los proveedores</option>
              {proveedores.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <input
              type="search"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar nº de pedido…"
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
              aria-label="Buscar por número de pedido"
            />
          </div>
        </div>

        <TablaPedidos pedidos={pedidos} cargando={cargando} onSelect={abrir} seleccionadoId={seleccionado?.order_id} />
      </section>

      {seleccionado && (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/40" onClick={() => setSeleccionado(null)}>
          <aside
            className="h-full w-full max-w-2xl overflow-y-auto bg-slate-50 p-4 shadow-2xl sm:p-6"
            onClick={(e) => e.stopPropagation()}
            aria-label={`Detalle del pedido ${seleccionado.order_id}`}
          >
            <button onClick={() => setSeleccionado(null)} className="mb-3 text-sm font-medium text-slate-600 hover:text-slate-900">
              ← Volver al listado
            </button>
            <DiscrepancyCard analysis={seleccionado} onReview={revisar} busy={guardando} />
          </aside>
        </div>
      )}
    </div>
  );
}

function PanelMetricas({ metricas }) {
  if (!metricas) return <div className="h-28 animate-pulse rounded-2xl bg-slate-200" />;
  const maxIncidencias = Math.max(1, ...metricas.top_proveedores.map((p) => p.incidencias));
  return (
    <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Métricas">
      <Kpi titulo="Auto-aprobación" valor={`${metricas.pct_auto_aprobacion.toLocaleString("es-ES")}%`} detalle={`de ${metricas.total_pedidos} pedidos procesados`} />
      <Kpi titulo="En cola de revisión" valor={metricas.en_cola} detalle="pedidos 🔴/🟠 pendientes" />
      <Kpi titulo="Resueltos hoy" valor={metricas.resueltos_hoy} detalle="decisiones de operadores" />
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-xs uppercase tracking-wide text-slate-500">Top proveedores con incidencias</h2>
        <p className="text-xs text-slate-400">lectura + cantidad</p>
        {metricas.top_proveedores.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">Sin incidencias registradas.</p>
        ) : (
          <ol className="mt-2 space-y-1.5">
            {metricas.top_proveedores.map((p) => (
              <li key={p.proveedor} className="text-xs" title={`${p.proveedor}: ${p.incidencias} incidencias`}>
                <div className="flex justify-between gap-2">
                  <span className="truncate text-slate-700">{p.proveedor}</span>
                  <span className="font-semibold text-slate-900">{p.incidencias}</span>
                </div>
                <div className="mt-0.5 h-1.5 rounded-full bg-slate-100">
                  <div className="h-1.5 rounded-full bg-slate-500" style={{ width: `${(p.incidencias / maxIncidencias) * 100}%` }} />
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function Kpi({ titulo, valor, detalle }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xs uppercase tracking-wide text-slate-500">{titulo}</h2>
      <p className="mt-1 text-3xl font-bold tabular-nums text-slate-900">{valor}</p>
      <p className="text-xs text-slate-500">{detalle}</p>
    </div>
  );
}

function ProcesarPedido({ onProcesar }) {
  const [files, setFiles] = useState({ factura: null, albaran: null, packing_list: null });
  const [enviando, setEnviando] = useState(false);
  const completos = Object.values(files).every(Boolean);

  async function enviar(conFicheros) {
    setEnviando(true);
    try {
      await onProcesar(conFicheros ? files : null);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <details className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <summary className="cursor-pointer text-sm font-semibold text-slate-700">＋ Procesar nuevo pedido</summary>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {[["factura", "Factura"], ["albaran", "Albarán"], ["packing_list", "Packing List"]].map(([tipo, label]) => (
          <label key={tipo} className="text-sm">
            <span className="block text-xs text-slate-500">{label} (.txt, .pdf, .jpg)</span>
            <input
              type="file"
              accept=".txt,.pdf,.jpg,.jpeg"
              onChange={(e) => setFiles((f) => ({ ...f, [tipo]: e.target.files?.[0] ?? null }))}
              className="mt-1 block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2 file:py-1"
            />
          </label>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          disabled={!completos || enviando}
          onClick={() => enviar(true)}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          Analizar documentos
        </button>
        <button
          disabled={enviando}
          onClick={() => enviar(false)}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        >
          Usar pedido de ejemplo (#4521)
        </button>
        {enviando && <span className="self-center text-sm text-slate-500">Analizando…</span>}
      </div>
    </details>
  );
}

function ResumenSeveridades({ items }) {
  const conteo = {};
  items.forEach((d) => (conteo[d.severidad] = (conteo[d.severidad] ?? 0) + 1));
  const orden = Object.keys(SEVERIDADES).filter((s) => conteo[s]);
  if (orden.length === 0) return <span className="text-slate-400">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {orden.map((s) => (
        <span key={s} className={`rounded-full px-1.5 py-0.5 text-xs ${SEVERIDADES[s].chip}`} title={SEVERIDADES[s].label}>
          {SEVERIDADES[s].emoji} {conteo[s]}
        </span>
      ))}
    </span>
  );
}

function TablaPedidos({ pedidos, cargando, onSelect, seleccionadoId }) {
  if (!cargando && pedidos.length === 0) {
    return <p className="p-8 text-center text-sm text-slate-500">No hay pedidos con estos filtros.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2 font-medium">Semáforo</th>
            <th className="px-4 py-2 font-medium">Pedido</th>
            <th className="hidden px-4 py-2 font-medium md:table-cell">Proveedor</th>
            <th className="px-4 py-2 font-medium">Discrepancias</th>
            <th className="px-4 py-2 font-medium">Estado</th>
            <th className="hidden px-4 py-2 font-medium sm:table-cell">Procesado</th>
          </tr>
        </thead>
        <tbody className={`divide-y divide-slate-100 ${cargando ? "opacity-60" : ""}`}>
          {pedidos.map((p) => {
            const s = SEMAFORO[p.status_semaforo];
            const e = ESTADOS[p.estado_revision];
            return (
              <tr
                key={p.analysis_id}
                onClick={() => onSelect(p.order_id)}
                onKeyDown={(ev) => ev.key === "Enter" && onSelect(p.order_id)}
                tabIndex={0}
                className={`cursor-pointer hover:bg-slate-50 focus:bg-slate-100 focus:outline-none ${seleccionadoId === p.order_id ? "bg-slate-100" : ""}`}
              >
                <td className="px-4 py-3">
                  <span className="flex items-center gap-2">
                    <span className={`h-3 w-3 shrink-0 rounded-full ${s.lamp}`} aria-hidden />
                    <span className={`hidden text-xs font-medium lg:inline ${s.text}`}>{s.label}</span>
                  </span>
                </td>
                <td className="px-4 py-3 font-semibold">#{p.order_id}</td>
                <td className="hidden max-w-xs truncate px-4 py-3 text-slate-700 md:table-cell">{p.proveedor ?? "—"}</td>
                <td className="px-4 py-3"><ResumenSeveridades items={p.items_discrepancias} /></td>
                <td className="px-4 py-3">
                  <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${e.chip}`}>{e.emoji} {e.label}</span>
                </td>
                <td className="hidden whitespace-nowrap px-4 py-3 text-slate-500 sm:table-cell">{formatFecha(p.timestamp)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

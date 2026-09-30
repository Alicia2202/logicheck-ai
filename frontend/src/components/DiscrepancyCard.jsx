import { useState } from "react";
import {
  ACCIONES,
  DOCUMENTOS,
  ESTADOS,
  SEMAFORO,
  SEVERIDADES,
  etiquetaValor,
  formatFecha,
  formatValor,
} from "../constants.js";

// Mismo umbral que comparator.UMBRAL_SIMILITUD_TEXTO.
const UMBRAL_SIMILITUD = 0.55;

/**
 * Detalle de un pedido analizado, pensado para decidir en 10 segundos:
 * semáforo arriba, lo más grave primero y "qué hacer" en cada discrepancia.
 *
 * Props:
 *  - analysis: OrderAnalysisDetail (GET /api/v1/feedbacks/{order_id})
 *  - onReview(action, notes): Promise — registra la decisión del operador
 *  - busy: deshabilita las acciones mientras se guarda
 */
export default function DiscrepancyCard({ analysis, onReview, busy = false }) {
  const [modalAbierto, setModalAbierto] = useState(false);

  const discrepancias = [...analysis.items_discrepancias].sort(
    (a, b) => SEVERIDADES[a.severidad].orden - SEVERIDADES[b.severidad].orden,
  );
  const bloqueantes = discrepancias.filter((d) => d.severidad !== "info");
  const notas = discrepancias.filter((d) => d.severidad === "info");

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <Cabecera analysis={analysis} />

      <div className="space-y-6 p-5">
        <Metadatos analysis={analysis} />

        <section aria-labelledby="discrepancias-titulo" className="space-y-3">
          <h3 id="discrepancias-titulo" className="text-sm font-semibold text-slate-700">
            Discrepancias ({analysis.total_discrepancies})
          </h3>
          {discrepancias.length === 0 && (
            <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
              Sin discrepancias: pedido, proveedor, producto, cantidad e importes coinciden.
            </p>
          )}
          {bloqueantes.map((d, i) => (
            <DiscrepanciaItem key={`${d.campo}-${i}`} d={d} />
          ))}
          {notas.length > 0 && (
            <details className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm" open={bloqueantes.length === 0}>
              <summary className="cursor-pointer font-medium text-slate-700">
                ⚪ {notas.length} nota{notas.length > 1 ? "s" : ""} informativa{notas.length > 1 ? "s" : ""} (no bloquean)
              </summary>
              <div className="mt-3 space-y-3">
                {notas.map((d, i) => (
                  <DiscrepanciaItem key={`${d.campo}-${i}`} d={d} />
                ))}
              </div>
            </details>
          )}
        </section>

        <Acciones
          analysis={analysis}
          busy={busy}
          onApprove={() => onReview("APPROVE", null)}
          onFalsePositive={() => onReview("FALSE_POSITIVE", null)}
          onReject={() => setModalAbierto(true)}
        />

        <Historial revisiones={analysis.historial_revisiones ?? []} />
      </div>

      {modalAbierto && (
        <ModalRechazo
          orderId={analysis.order_id}
          busy={busy}
          onCancel={() => setModalAbierto(false)}
          onConfirm={async (notes) => {
            await onReview("REJECT", notes);
            setModalAbierto(false);
          }}
        />
      )}
    </article>
  );
}

function Semaforo({ estado }) {
  const luces = ["rojo", "amarillo", "verde"];
  return (
    <div className="flex flex-col gap-1.5 rounded-xl bg-slate-800 p-2" role="img" aria-label={`Semáforo: ${SEMAFORO[estado].label}`}>
      {luces.map((luz) => (
        <span
          key={luz}
          className={`h-5 w-5 rounded-full ${luz === estado ? `${SEMAFORO[luz].lamp} shadow-[0_0_10px] shadow-current` : "bg-slate-600"}`}
        />
      ))}
    </div>
  );
}

function Cabecera({ analysis }) {
  const s = SEMAFORO[analysis.status_semaforo];
  const estado = ESTADOS[analysis.estado_revision];
  return (
    <header className="flex items-center gap-4 border-b border-slate-200 bg-slate-50 p-5">
      <Semaforo estado={analysis.status_semaforo} />
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-wide text-slate-500">Pedido</p>
        <h2 className="truncate text-2xl font-bold text-slate-900">#{analysis.order_id}</h2>
        <p className={`text-sm font-semibold ${s.text}`}>
          {s.label} <span className="font-normal text-slate-600">— {s.detalle}</span>
        </p>
      </div>
      <div className="flex flex-col items-end gap-1 text-right">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${estado.chip}`}>
          {estado.emoji} {estado.label}
        </span>
        {analysis.decision_final && (
          <span className="text-xs text-slate-600">{ACCIONES[analysis.decision_final]}</span>
        )}
      </div>
    </header>
  );
}

function Metadatos({ analysis }) {
  const sim = analysis.similitud_proveedor;
  const mismoProveedor = sim === null || sim >= UMBRAL_SIMILITUD;
  return (
    <section className="grid gap-4 sm:grid-cols-2">
      <div>
        <h3 className="text-xs uppercase tracking-wide text-slate-500">Proveedor</h3>
        <p className="font-semibold text-slate-900">{analysis.proveedor ?? "—"}</p>
        {sim !== null && (
          <p className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${mismoProveedor ? "bg-emerald-100 text-emerald-800" : "bg-orange-100 text-orange-800"}`}>
            {mismoProveedor ? "≈" : "≠"} Fuzzy match {Math.round(sim * 100)}%
            {mismoProveedor ? " · mismo proveedor" : " · nombres distintos"}
          </p>
        )}
        <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
          {analysis.documentos.map((doc) => (
            <li key={doc.tipo}>
              <span className="text-slate-500">{DOCUMENTOS[doc.tipo]}:</span> {doc.proveedor ?? "no legible"}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="text-xs uppercase tracking-wide text-slate-500">Documentos</h3>
        <ul className="mt-1 space-y-1.5">
          {analysis.documentos.map((doc) => (
            <li key={doc.tipo} className="flex flex-wrap items-center justify-between gap-x-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm">
              <span className="font-medium">📄 {DOCUMENTOS[doc.tipo]}</span>
              <span className="text-xs text-slate-500">
                {doc.fecha ?? "sin fecha"} · confianza {doc.confianza}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-500">Analizado {formatFecha(analysis.timestamp)}</p>
      </div>
    </section>
  );
}

function DiscrepanciaItem({ d }) {
  const sev = SEVERIDADES[d.severidad];
  const entradas = Object.entries(d.valores);
  // Misma regla que DiscrepancyModel.from_discrepancia: la referencia es la
  // factura o el valor recalculado. Resaltamos lo que no coincide con ella.
  const claveRef = ["factura", "calculado"].find((k) => k in d.valores) ?? entradas[0]?.[0];
  const resaltar = d.severidad !== "info";
  return (
    <div className={`rounded-xl border p-4 ${sev.card}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${sev.chip}`}>
          {sev.emoji} {sev.label}
        </span>
        <span className="font-mono text-xs uppercase text-slate-600">{d.campo.replaceAll("_", " ")}</span>
      </div>
      <p className="mt-2 text-sm text-slate-800">{d.mensaje}</p>

      {entradas.length > 0 && (
        <dl className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(min(7rem,100%),1fr))] gap-2">
          {entradas.map(([clave, valor]) => {
            const esReferencia = clave === claveRef;
            const difiere = resaltar && !esReferencia && JSON.stringify(valor) !== JSON.stringify(d.valores[claveRef]);
            return (
              <div
                key={clave}
                className={`rounded-lg border bg-white px-3 py-2 ${difiere ? "border-red-300 ring-1 ring-red-200" : "border-slate-200"}`}
              >
                <dt className="text-xs text-slate-500">
                  {etiquetaValor(clave)}
                  {esReferencia && entradas.length > 1 && <span className="ml-1 text-slate-400">(ref.)</span>}
                </dt>
                <dd className={`text-sm font-semibold ${difiere ? "text-red-700" : "text-slate-900"}`}>
                  {formatValor(valor)}
                </dd>
              </div>
            );
          })}
        </dl>
      )}

      <p className="mt-3 flex gap-2 rounded-lg bg-white/70 p-2 text-sm text-slate-800">
        <span aria-hidden>→</span>
        <span>
          <strong className="font-semibold">Qué hacer:</strong> {d.accion_sugerida}
        </span>
      </p>
    </div>
  );
}

function Acciones({ analysis, busy, onApprove, onReject, onFalsePositive }) {
  const hayDiscrepancias = analysis.items_discrepancias.some((d) => d.severidad !== "info");
  return (
    <section className="flex flex-col gap-2 border-t border-slate-200 pt-5 sm:flex-row">
      <button
        type="button"
        disabled={busy}
        onClick={onApprove}
        className="flex-1 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        ✔ Aprobar pedido
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onReject}
        className="flex-1 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
      >
        ✖ Rechazar / Escalar
      </button>
      <button
        type="button"
        disabled={busy || !hayDiscrepancias}
        onClick={onFalsePositive}
        title={hayDiscrepancias ? "La alerta no era un problema real" : "No hay discrepancias que marcar"}
        className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        ⚑ Marcar falso positivo
      </button>
    </section>
  );
}

function Historial({ revisiones }) {
  if (revisiones.length === 0) return null;
  return (
    <section>
      <h3 className="text-xs uppercase tracking-wide text-slate-500">Historial de revisiones</h3>
      <ol className="mt-2 space-y-2">
        {revisiones.map((r, i) => (
          <li key={i} className="border-l-2 border-slate-300 pl-3 text-sm">
            <p>
              <strong>{ACCIONES[r.action_taken]}</strong> por {r.operator_id}
              <span className="text-slate-500"> · {formatFecha(r.timestamp)}</span>
            </p>
            {r.user_notes && <p className="text-slate-600">“{r.user_notes}”</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

function ModalRechazo({ orderId, busy, onCancel, onConfirm }) {
  const [notas, setNotas] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center" role="dialog" aria-modal="true" aria-labelledby="modal-rechazo-titulo">
      <form
        className="w-full max-w-md space-y-4 rounded-2xl bg-white p-5 shadow-xl"
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(notas.trim());
        }}
      >
        <h2 id="modal-rechazo-titulo" className="text-lg font-semibold">
          Rechazar / escalar pedido #{orderId}
        </h2>
        <label className="block text-sm">
          <span className="text-slate-700">Comentario para el proveedor</span>
          <textarea
            autoFocus
            required
            rows={4}
            maxLength={2000}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            placeholder="Ej.: El packing list recoge 480 kg frente a los 500 kg facturados. Solicitamos abono de 20 kg."
            className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-slate-500 focus:outline-none"
          />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
            Cancelar
          </button>
          <button
            type="submit"
            disabled={busy || !notas.trim()}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          >
            Rechazar y escalar
          </button>
        </div>
      </form>
    </div>
  );
}

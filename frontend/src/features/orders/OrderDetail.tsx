import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { orders } from "../../api/orders";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice } from "../../components/Feedback";
import { panelUrl } from "../../panel";
import { actionLabel, itemDetails, localDate, money } from "./orderHelpers";

export function OrderDetail() {
  const { id = "" } = useParams();
  const q = useQuery(() => orders.detail(id), [id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [minutes, setMinutes] = useState(30);

  async function transition(status: string) {
    if (status === "cancelled" && !window.confirm(`Cancelar o pedido #${id}?`)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await orders.transition(id, status, {
        ...(status === "confirmed" ? { prep_minutes: minutes } : {}),
      });
      setMessages([{ level: "success", text: result.detail }]);
      q.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  async function estimate() {
    setBusy(true);
    setError(null);
    try {
      const result = await orders.estimate(id, minutes);
      setMessages([{ level: "success", text: result.detail }]);
      q.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  const d = q.data;
  return (
    <>
      <Link className="back no-print" to={panelUrl("orders")}>← Voltar aos pedidos</Link>
      <div className="page-heading order-detail-heading">
        <div>
          <p className="eyebrow">Pedido</p>
          <h1>#{id} {d && <span className={`status-pill status-${d.status}`}>{d.status_label}</span>}</h1>
        </div>
        <div className="heading-actions no-print">
          <button className="secondary" onClick={() => window.print()}>🖨 Imprimir comanda</button>
        </div>
      </div>
      <Notice messages={messages} />
      <Feedback error={error}><></></Feedback>
      <Feedback loading={q.loading} error={q.error}>
        {d && (
          <div className="order-detail-grid">
            <div>
              <section className="card print-ticket">
                <div className="ticket-title">
                  <div><strong>Pedido #{d.id}</strong><small>{localDate(d.created_at)}</small></div>
                  <strong>{money(d.total)}</strong>
                </div>
                <div className="ticket-meta">
                  <span><strong>{d.customer_name}</strong>{d.customer_phone ? ` · ${d.customer_phone}` : ""}</span>
                  <span>{d.delivery_label}{d.delivery_type === "delivery" && d.delivery_address ? ` · ${d.delivery_address}` : ""}</span>
                  {d.delivery_reference && <span>Referência: {d.delivery_reference}</span>}
                  <span>{d.payment_label}</span>
                </div>
                <h2>Itens</h2>
                {d.items.map((item: any) => (
                  <div className="ticket-item" key={item.id}>
                    <div><strong>{item.quantity}× {item.name}</strong><b>{money(item.line_total)}</b></div>
                    {itemDetails(item.combination_details).map((line, i) => <small key={i}>{line}</small>)}
                    {item.notes && <em>Obs.: {item.notes}</em>}
                  </div>
                ))}
                <div className="ticket-totals">
                  <span>Subtotal <strong>{money(d.subtotal)}</strong></span>
                  <span>Entrega <strong>{money(d.delivery_fee)}</strong></span>
                  {Number(d.discount_amount) > 0 && <span>Desconto <strong>-{money(d.discount_amount)}</strong></span>}
                  <span className="ticket-grand-total">Total <strong>{money(d.total)}</strong></span>
                </div>
              </section>
              <section className="card">
                <h2>Cliente e entrega</h2>
                <div className="detail-list">
                  <span><small>Cliente</small><strong>{d.customer_name}</strong></span>
                  <span><small>WhatsApp</small><strong>{d.customer_phone || "Não informado"}</strong></span>
                  <span><small>Recebimento</small><strong>{d.delivery_label}</strong></span>
                  <span><small>Endereço</small><strong>{d.delivery_address}</strong></span>
                  {d.delivery_reference && <span><small>Referência</small><strong>{d.delivery_reference}</strong></span>}
                  <span><small>Pagamento</small><strong>{d.payment_label} · {d.payment.label}</strong></span>
                  <span><small>Origem</small><strong>{d.source_label}</strong></span>
                </div>
              </section>
            </div>
            <aside>
              <section className="card no-print">
                <h2>Operação</h2>
                <label className="field">
                  Previsão de preparo
                  <div className="inline-control">
                    <input type="number" min={5} max={240} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
                    <button className="secondary" disabled={busy} onClick={estimate}>Atualizar</button>
                  </div>
                </label>
                {d.estimated_ready_at && <p className={d.late ? "late-text" : "muted"}>Previsão atual: {localDate(d.estimated_ready_at)}</p>}
                <div className="detail-actions">
                  {d.allowed_transitions.filter((a: any) => a.value !== "cancelled").map((a: any) => (
                    <button key={a.value} disabled={busy} onClick={() => transition(a.value)}>
                      {actionLabel[a.value] || a.label}
                    </button>
                  ))}
                  {d.allowed_transitions.some((a: any) => a.value === "cancelled") && (
                    <button className="secondary danger-text" disabled={busy} onClick={() => transition("cancelled")}>Cancelar pedido</button>
                  )}
                </div>
              </section>
              <section className="card no-print">
                <h2>Histórico operacional</h2>
                {d.events.length ? d.events.map((event: any) => (
                  <div className="order-event" key={event.id}>
                    <small>{localDate(event.created_at)} · {event.actor}</small>
                    <strong>{event.from_label ? `${event.from_label} → ` : ""}{event.to_label}</strong>
                    {event.note && <p>{event.note}</p>}
                    {event.notification && (
                      <span className={`notice-state ${event.notification.status}`}>
                        WhatsApp: {event.notification.status === "sent" ? "enviado" : event.notification.status === "skipped" ? "ignorado" : "pendente"}
                        {event.notification.last_error ? ` · ${event.notification.last_error}` : ""}
                      </span>
                    )}
                  </div>
                )) : <p className="muted">Ainda não há mudanças de status registradas.</p>}
              </section>
            </aside>
          </div>
        )}
      </Feedback>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { orders } from "../../api/orders";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice, Empty } from "../../components/Feedback";
import { panelUrl } from "../../panel";
import { actionLabel, localTime, money, statusIcon } from "./orderHelpers";

function useOrderRealtime(reload: () => void) {
  const [state, setState] = useState<"connecting" | "online" | "fallback">(
    "connecting",
  );
  const reloadRef = useRef(reload);
  useEffect(() => {
    reloadRef.current = reload;
  }, [reload]);
  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let retry: number | undefined;
    const connect = () => {
      if (closed) return;
      setState("connecting");
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/merchant/orders/`);
      socket.onopen = () => setState("online");
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (String(payload.event || "").startsWith("order.")) reloadRef.current();
        } catch {
          // Ignore malformed realtime hints; HTTP remains authoritative.
        }
      };
      socket.onerror = () => setState("fallback");
      socket.onclose = () => {
        if (closed) return;
        setState("fallback");
        retry = window.setTimeout(connect, 5000);
      };
    };
    connect();
    const poll = window.setInterval(() => reloadRef.current(), 30000);
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      window.clearInterval(poll);
      socket?.close();
    };
  }, []);
  return state;
}

function playAlert() {
  try {
    const Context = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new Context();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();
    oscillator.frequency.value = 740;
    gain.gain.value = 0.08;
    oscillator.connect(gain);
    gain.connect(ctx.destination);
    oscillator.start();
    oscillator.stop(ctx.currentTime + 0.16);
    oscillator.onended = () => ctx.close();
  } catch {
    // Audio is an enhancement only.
  }
}

function OrderCard({
  order,
  onTransition,
  busy,
}: {
  order: any;
  onTransition: (order: any, status: string) => void;
  busy: boolean;
}) {
  return (
    <article className={`order-card ${order.late ? "late" : ""}`}>
      <div className="order-card-head">
        <div>
          <strong>#{order.id}</strong>
          <small>{localTime(order.created_at)}</small>
        </div>
        <span className={`order-source source-${order.source}`}>
          {order.source_label}
        </span>
      </div>
      <Link className="order-customer" to={panelUrl(`orders/${order.id}`)}>
        {order.customer_name}
      </Link>
      <small>{order.delivery_label} · {order.payment.label}</small>
      <div className="order-items-mini">
        {order.items.slice(0, 3).map((item: any) => (
          <span key={item.id}>
            {item.quantity}× {item.name}
          </span>
        ))}
        {order.items.length > 3 && <span>+ mais itens</span>}
      </div>
      <div className="order-card-meta">
        <strong>{money(order.total)}</strong>
        {order.estimated_ready_at && (
          <span className={order.late ? "late-text" : ""}>
            {order.late ? "Atrasado · " : "Prev. "}
            {localTime(order.estimated_ready_at)}
          </span>
        )}
      </div>
      <div className="order-actions">
        {order.allowed_transitions
          .filter((a: any) => a.value !== "cancelled")
          .map((a: any) => (
            <button
              key={a.value}
              disabled={busy}
              onClick={() => onTransition(order, a.value)}
            >
              {actionLabel[a.value] || a.label}
            </button>
          ))}
        {order.allowed_transitions.some((a: any) => a.value === "cancelled") && (
          <button
            className="text-button danger-text"
            disabled={busy}
            onClick={() => onTransition(order, "cancelled")}
          >
            Cancelar
          </button>
        )}
      </div>
    </article>
  );
}

function NotificationSettings({ data, onSaved }: { data: any; onSaved: () => void }) {
  const [form, setForm] = useState(data);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => setForm(data), [data]);
  const toggles = [
    ["notify_confirmed", "Pedido confirmado"],
    ["notify_preparing", "Pedido em preparo"],
    ["notify_ready", "Pedido pronto"],
    ["notify_out_for_delivery", "Saiu para entrega"],
    ["notify_delivered", "Pedido entregue"],
    ["notify_cancelled", "Pedido cancelado"],
  ];
  async function save() {
    setBusy(true);
    setMessage("");
    try {
      await orders.saveSettings(form);
      setMessage("Preferências salvas.");
      onSaved();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card order-settings">
      <summary>Notificações automáticas no WhatsApp</summary>
      <p className="muted">
        O backend envia estes avisos pelo WhatsApp conectado da loja sempre que o
        status é alterado no painel.
      </p>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={Boolean(form.enabled)}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
        />
        Ativar avisos automáticos de status
      </label>
      <div className="settings-grid">
        {toggles.map(([key, label]) => (
          <label className="toggle-row" key={key}>
            <input
              type="checkbox"
              checked={Boolean(form[key])}
              disabled={!form.enabled}
              onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
            />
            {label}
          </label>
        ))}
        <label className="field">
          Tempo padrão de preparo
          <input
            type="number"
            min={5}
            max={240}
            value={form.default_prep_minutes}
            onChange={(e) =>
              setForm({ ...form, default_prep_minutes: Number(e.target.value) })
            }
          />
          <small>Em minutos. É usado ao confirmar um novo pedido.</small>
        </label>
      </div>
      {message && <p className="muted">{message}</p>}
      <button disabled={busy} onClick={save}>
        {busy ? "Salvando…" : "Salvar preferências"}
      </button>
    </details>
  );
}

export function OrdersBoard() {
  const q = useQuery(() => orders.board(), []);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [alerts, setAlerts] = useState(
    () => localStorage.getItem("vdd_order_alerts") === "on",
  );
  const seen = useRef<Set<number> | null>(null);
  const realtime = useOrderRealtime(q.reload);

  useEffect(() => {
    if (!q.data) return;
    const current = new Set<number>(
      q.data.columns
        .flatMap((column: any) => column.orders)
        .filter((row: any) => row.status === "pending")
        .map((row: any) => row.id),
    );
    if (seen.current && alerts) {
      const fresh = [...current].filter((id) => !seen.current!.has(id));
      if (fresh.length) {
        playAlert();
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("Novo pedido no VemDeDelivery", {
            body: `${fresh.length} novo(s) pedido(s) aguardando confirmação.`,
          });
        }
      }
    }
    seen.current = current;
  }, [q.data, alerts]);

  async function enableAlerts() {
    if ("Notification" in window && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    playAlert();
    localStorage.setItem("vdd_order_alerts", "on");
    setAlerts(true);
  }

  async function transition(order: any, status: string) {
    if (status === "cancelled" && !window.confirm(`Cancelar o pedido #${order.id}?`)) return;
    setBusyId(order.id);
    setError(null);
    try {
      const options =
        status === "confirmed"
          ? { prep_minutes: q.data?.notification_settings?.default_prep_minutes || 30 }
          : {};
      const result = await orders.transition(order.id, status, options);
      setMessages([{ level: "success", text: result.detail }]);
      q.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusyId(null);
    }
  }

  const d = q.data;
  return (
    <>
      <div className="page-heading orders-heading">
        <div>
          <p className="eyebrow">Operação em tempo real</p>
          <h1>Pedidos</h1>
          <div className="realtime-status">
            <span className={`live-dot ${realtime}`} />
            {realtime === "online"
              ? "Atualização em tempo real"
              : realtime === "fallback"
                ? "Reconectando · atualização automática ativa"
                : "Conectando…"}
          </div>
        </div>
        <div className="heading-actions">
          {!alerts && (
            <button className="secondary" onClick={enableAlerts}>
              🔔 Ativar alertas
            </button>
          )}
          <Link className="button" to={panelUrl("orders/novo")}>
            + Pedido manual
          </Link>
        </div>
      </div>
      <Notice messages={messages} />
      <Feedback error={error}><></></Feedback>
      <Feedback loading={q.loading} error={q.error}>
        {d && (
          <>
            <div className="order-summary-strip">
              {d.columns.map((column: any) => (
                <span key={column.status}>
                  <strong>{column.orders.length}</strong> {column.label}
                </span>
              ))}
            </div>
            <div className="order-board">
              {d.columns.map((column: any) => (
                <section className={`order-column status-${column.status}`} key={column.status}>
                  <header className="order-column-head">
                    <span>{statusIcon[column.status]}</span>
                    <strong>{column.label}</strong>
                    <b>{column.orders.length}</b>
                  </header>
                  <div className="order-column-body">
                    {column.orders.length ? (
                      column.orders.map((order: any) => (
                        <OrderCard
                          key={order.id}
                          order={order}
                          busy={busyId === order.id}
                          onTransition={transition}
                        />
                      ))
                    ) : (
                      <Empty />
                    )}
                  </div>
                </section>
              ))}
            </div>
            <NotificationSettings data={d.notification_settings} onSaved={q.reload} />
            <details className="card finished-orders">
              <summary>Pedidos finalizados recentemente ({d.finished.length})</summary>
              {d.finished.length ? (
                <div className="finished-grid">
                  {d.finished.map((order: any) => (
                    <Link key={order.id} to={panelUrl(`orders/${order.id}`)}>
                      <strong>#{order.id}</strong> · {order.customer_name} · {order.status_label} · {money(order.total)}
                    </Link>
                  ))}
                </div>
              ) : (
                <Empty />
              )}
            </details>
          </>
        )}
      </Feedback>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import { Pagination } from "../../components/Pagination";
import { Monitor } from "../../components/Monitor";
import { Link } from "react-router-dom";
import { orders } from "../../api/orders";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice, Empty } from "../../components/Feedback";
import { panelUrl } from "../../panel";
import { claimOrderAlerts } from "./orderAlerts";
import { TransitionDialog } from "./TransitionDialog";
import { actionLabel, itemDetails, localTime, money, statusIcon } from "./orderHelpers";

export function useOrderRealtime(reload: () => void) {
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
      socket.onopen = () => { setState("online"); reloadRef.current(); };
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
  expanded = false,
  fresh = false,
}: {
  order: any;
  onTransition: (order: any, status: string) => void;
  busy: boolean;
  expanded?: boolean;
  fresh?: boolean;
}) {
  return (
    <article className={`order-card ${order.late ? "late" : ""} ${fresh ? "order-fresh" : ""}`}>
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
      {order.scheduled_for&&<p>Agendado: {new Date(order.scheduled_for).toLocaleString("pt-BR")}</p>}
      <small>{order.delivery_label} · {order.payment.label}</small>
      {expanded && <>
        <small>{order.payment_label}</small>
        <small>Há {Math.max(0, Math.floor((Date.now() - new Date(order.created_at).getTime()) / 60000))} min · {order.status_label}</small>
        {order.delivery_type === "delivery" && <p>{order.delivery_address}</p>}
        {order.delivery_reference && <p className="operation-note">Referência: {order.delivery_reference}</p>}
        {order.estimated_fulfillment_at && <small>Previsão de {order.delivery_type === "pickup" ? "retirada" : "entrega"}: {localTime(order.estimated_fulfillment_at)}</small>}
      </>}
      <div className="order-items-mini">
        {(expanded ? order.items : order.items.slice(0, 3)).map((item: any) => (
          <span key={item.id}>
            {item.quantity}× {item.name}
            {expanded && itemDetails(item.combination_details).map((line, index) => <small key={index}>{line}</small>)}
            {expanded && item.notes && <em className="operation-note">Obs.: {item.notes}</em>}
          </span>
        ))}
        {!expanded && order.items.length > 3 && <span>+ mais itens</span>}
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
        <label className="toggle-row"><input type="checkbox" checked={Boolean(form.allow_skip_notification)} onChange={(e) => setForm({ ...form, allow_skip_notification: e.target.checked })} />Permitir omitir aviso por pedido</label>
        {[["default_delivery_minutes", "Entrega"], ["default_pickup_minutes", "Retirada"]].map(([key, label]) => <label className="field" key={key}>Prazo padrão de {label.toLowerCase()}<input type="number" min={5} max={240} value={form[key]} onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} /><small>Em minutos.</small></label>)}
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

export function OrdersBoard({ activeOnly = false }: { activeOnly?: boolean }) {
  const [page,setPage]=useState(1),[size,setSize]=useState(10);
  const q = useQuery(() => orders.board(activeOnly,page,size), [activeOnly,page,size]);
  const [selected, setSelected] = useState<{ order: any; status: string } | null>(null);
  const [freshIds, setFreshIds] = useState<number[]>([]);
  const [, tick] = useState(0);
  useEffect(() => { const timer = window.setInterval(() => tick((n) => n + 1), 30000); return () => window.clearInterval(timer); }, []);
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
    if (seen.current) {
      const fresh = [...current].filter((id) => !seen.current!.has(id));
      if (fresh.length) setFreshIds(fresh);
      if (fresh.length && alerts) {
        void claimOrderAlerts(fresh).then((claimed) => {
        if (!claimed.length) return;
        playAlert();
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("Novo pedido no VemDeDelivery", {
            body: `${claimed.length} novo(s) pedido(s) aguardando confirmação.`,
            tag: `vdd-orders-${claimed.join("-")}`,
          });
        }
        });
      }
    }
    seen.current = new Set([...(seen.current || []), ...current]);
  }, [q.data, alerts]);

  useEffect(() => {
    if (!freshIds.length) return;
    const timer = window.setTimeout(() => setFreshIds([]), 20000);
    return () => window.clearTimeout(timer);
  }, [freshIds]);

  async function enableAlerts() {
    if ("Notification" in window && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    playAlert();
    localStorage.setItem("vdd_order_alerts", "on");
    setAlerts(true);
  }

  async function transition(options: Parameters<typeof orders.transition>[2]) {
    if (!selected) return;
    const { order, status } = selected;
    setBusyId(order.id);
    setError(null);
    try {
      const result = await orders.transition(order.id, status, options);
      setMessages([{ level: "success", text: result.detail }]);
      setSelected(null);
      q.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusyId(null);
    }
  }

  const d = q.data;
  return (
    <Monitor>
      <div className="page-heading orders-heading">
        <div>
          <p className="eyebrow">Operação em tempo real</p>
          <h1>{activeOnly ? "Pedidos ativos" : "Pedidos e histórico"}</h1>
          <p className="muted">{activeOnly ? "Todos os pedidos em andamento, com detalhes para a equipe." : "Acompanhe a operação e consulte os pedidos finalizados abaixo."}</p><div className="realtime-status">
            <span className={`live-dot ${realtime}`} />
            {realtime === "online"
              ? "Atualização em tempo real"
              : realtime === "fallback"
                ? "Reconectando · atualização automática ativa"
                : "Conectando…"}
          </div>
        </div>
        <div className="heading-actions">
          <Link className="button secondary" to={panelUrl(activeOnly ? "orders" : "operacao")}>{activeOnly ? "Todos os pedidos" : "Operação rápida"}</Link>
          {alerts && <button className="secondary" onClick={() => { localStorage.setItem("vdd_order_alerts", "off"); setAlerts(false); }}>Silenciar alertas</button>}
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
                          expanded={activeOnly}
                          fresh={freshIds.includes(order.id)}
                          onTransition={(order, status) => { setError(null); setSelected({ order, status }); }}
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
            {!activeOnly && <details className="card finished-orders">
              <summary>Pedidos finalizados recentemente ({d.finished_pagination?.count ?? d.finished.length})</summary><Pagination page={d.finished_pagination?.page} pages={d.finished_pagination?.pages} size={size} onPage={setPage} onSize={n=>{setSize(n);setPage(1);}}/>
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
            </details>}
          </>
        )}
      </Feedback>
      {selected && <TransitionDialog order={selected.order} status={selected.status} settings={d.notification_settings} busy={busyId !== null} error={error} onConfirm={transition} onClose={() => setSelected(null)} />}
    </Monitor>
  );
}

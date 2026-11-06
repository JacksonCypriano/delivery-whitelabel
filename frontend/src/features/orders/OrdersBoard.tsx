import { useEffect, useRef, useState } from "react";
import { Pagination } from "../../components/Pagination";
import { Monitor } from "../../components/Monitor";
import { Link } from "react-router-dom";
import { orders } from "../../api/orders";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice, Empty } from "../../components/Feedback";
import { panelUrl } from "../../panel";
import { claimOrderAlerts } from "./orderAlerts";
import { ChannelBand } from "./ChannelBand";
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

export function playAlert() {
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

function dropTarget(order:any,status:string){
  return status==='ready' && order.allowed_transitions.some((a:any)=>a.value==='ready_for_pickup') ? 'ready_for_pickup' : status;
}

function OrderCard({
  order,
  onTransition,
  busy,
  expanded = false,
  fresh = false,
  onDrag,
}: {
  order: any;
  onTransition: (order: any, status: string) => void;
  busy: boolean;
  expanded?: boolean;
  fresh?: boolean;
  onDrag?: (order: any | null) => void;
}) {
  return (
    <article draggable={Boolean(onDrag && !busy && order.allowed_transitions.length)} onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(order.id)); onDrag?.(order); }} onDragEnd={() => onDrag?.(null)} className={`order-card status-${order.status} ${order.late ? "late" : ""} ${fresh ? "order-fresh" : ""}`}>
      <ChannelBand order={order} />
      {onDrag && order.allowed_transitions.length > 0 && <button className="drag-handle secondary" aria-label={`Arrastar pedido ${order.id}`} disabled={busy}
        onPointerDown={e => { if(e.pointerType !== 'mouse'){e.currentTarget.setPointerCapture(e.pointerId);onDrag(order);} }}
        onPointerUp={e => { if(e.pointerType !== 'mouse'){ const lane = document.elementFromPoint(e.clientX,e.clientY)?.closest<HTMLElement>('[data-drop-status]');const laneStatus=lane?.dataset.dropStatus;const target=laneStatus ? dropTarget(order,laneStatus) : '';if(target && order.allowed_transitions.some((a:any)=>a.value===target))onTransition(order,target);onDrag(null);} }}
        onPointerCancel={()=>onDrag(null)}>⠿ Mover</button>}
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
      <div className="order-badges"><span>{order.delivery_label}</span><span className={order.payment.paid ? "paid" : "unpaid"}>{order.payment.label}</span></div>
      <small>{order.item_count ?? order.items.reduce((n: number,i: any)=>n+i.quantity,0)} itens · há {Math.max(0,Math.floor((Date.now()-new Date(order.created_at).getTime())/60000))} min</small>
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
        {onDrag && order.allowed_transitions.length > 0 && <label className="move-select">Mover para
          <select aria-label={`Mover pedido ${order.id} para`} value="" disabled={busy} onChange={e=>{if(e.target.value)onTransition(order,e.target.value);}}>
            <option value="">Escolher etapa…</option>{order.allowed_transitions.map((a:any)=><option value={a.value} key={a.value}>{a.label}</option>)}
          </select>
        </label>}
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
  const [filters,setFilters] = useState<Record<string,string>>({period:"today"});
  const [dragged,setDragged] = useState<any>(null);
  const [detailed,setDetailed] = useState(activeOnly);
  const [historyMode,setHistoryMode] = useState<"board"|"all">("board");
  const q = useQuery(() => orders.board(activeOnly,page,size,filters), [activeOnly,page,size,JSON.stringify(filters)]);
  function filter(key:string,value:string){setFilters(f=>({...f,[key]:value,delivered_page:"1",all_page:"1"}));setPage(1);}
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
      const result = await orders.transition(order.id, status, {...options, expected_status_updated_at: order.status_updated_at});
      setMessages([{ level: "success", text: result.detail }]);
      setSelected(null);
      q.reload();
    } catch (e) {
      setError(e as Error);
      q.reload();
    } finally {
      setBusyId(null);
    }
  }

  const d = q.data;
  function choose(order:any,status:string){setError(null);setSelected({order,status});}
  const operationalColumns = d ? d.columns.filter((c:any)=>c.status!=='ready_for_pickup').map((c:any)=>c.status==='ready'?{...c,label:'Prontos',orders:[...c.orders,...(d.columns.find((r:any)=>r.status==='ready_for_pickup')?.orders||[])]}:c) : [];
  if(d && !d.columns.some((c:any)=>c.status==='ready') && d.columns.some((c:any)=>c.status==='ready_for_pickup')) operationalColumns.push({...d.columns.find((c:any)=>c.status==='ready_for_pickup'),status:'ready',label:'Prontos'});
  const columns = d ? [...operationalColumns, ...(!activeOnly && d.delivered ? [{status:"delivered",label:"Entregues",orders:d.delivered,pagination:d.delivered_pagination}] : [])] : [];
  const visibleColumns = historyMode === "all" && !activeOnly ? [{status:"all",label:"Todos",orders:d?.all_orders || [],pagination:d?.all_pagination}] : columns;
  function drop(status:string){
    if(!dragged)return;
    status=dropTarget(dragged,status);
    if(dragged.allowed_transitions.some((a:any)=>a.value===status))choose(dragged,status);
    else setError(new Error("Esta movimentação não é permitida para o pedido. Confira as ações disponíveis."));
    setDragged(null);
  }
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
      <div className="board-toolbar card">
        {!activeOnly && <div className="board-tabs" role="group" aria-label="Visão de pedidos"><button className={historyMode==='board'?'':'secondary'} onClick={()=>setHistoryMode('board')}>Kanban</button><button className={historyMode==='all'?'':'secondary'} onClick={()=>setHistoryMode('all')}>Todos</button></div>}
        <label>Buscar<input type="search" placeholder="Pedido ou cliente" value={filters.q||''} onChange={e=>filter('q',e.target.value)}/></label>
        <label>Origem<select value={filters.source||''} onChange={e=>filter('source',e.target.value)}><option value="">Todas</option><option value="direct">VemDeDelivery</option><option value="ifood">Pedidos iFood</option><option value="99food">Pedidos 99Food</option></select></label>
        <label>Modalidade<select value={filters.modality||''} onChange={e=>filter('modality',e.target.value)}><option value="">Todas</option><option value="delivery">Entrega</option><option value="pickup">Retirada</option></select></label>
        {!activeOnly && <><label>Período do histórico<select value={filters.period} onChange={e=>filter('period',e.target.value)}><option value="today">Hoje</option><option value="yesterday">Ontem</option><option value="week">Últimos 7 dias</option><option value="custom">Personalizado</option></select></label>
        {filters.period==='custom' && <><label>De<input type="date" value={filters.start||''} onChange={e=>filter('start',e.target.value)}/></label><label>Até<input type="date" value={filters.end||''} onChange={e=>filter('end',e.target.value)}/></label></>}
        {historyMode==='all' && <label>Status<select value={filters.history_status||''} onChange={e=>filter('history_status',e.target.value)}><option value="">Todos</option>{[...d?.columns||[],{status:'delivered',label:'Entregues'},{status:'cancelled',label:'Cancelados'}].filter((c:any)=>c.status!=='awaiting_cancellation').map((c:any)=><option value={c.status} key={c.status}>{c.label}</option>)}</select></label>}</>}
        <label className="toggle-row"><input type="checkbox" checked={detailed} onChange={e=>setDetailed(e.target.checked)}/>Detalhes nos cards</label>
      </div>
      {!activeOnly && <p className="muted">Pedidos em andamento permanecem visíveis. O período filtra Entregues pela conclusão e Todos pela criação. {d?.timezone && `Fuso: ${d.timezone}.`}</p>}
      {dragged && <p role="status">Movendo #{dragged.id}. Solte em uma etapa permitida; a confirmação será solicitada.</p>}
      <Notice messages={messages} />
      <Feedback error={error}><></></Feedback>
      <Feedback loading={q.loading && !q.data} error={q.error}>
        {d && (
          <>
            <div className="order-summary-strip">
              {d.columns.map((column: any) => (
                <span key={column.status}>
                  <strong>{column.orders.length}</strong> {column.label}
                </span>
              ))}
            </div>
            <div className={`order-board ${historyMode==='all'?'history-board':''}`}>
              {visibleColumns.map((column: any) => (
                <section data-drop-status={column.status} onDragOver={e=>{if(dragged){e.preventDefault();e.dataTransfer.dropEffect=dragged.allowed_transitions.some((a:any)=>a.value===dropTarget(dragged,column.status))?'move':'none';}}} onDrop={e=>{e.preventDefault();drop(column.status);}} className={`order-column status-${column.status} ${dragged?.allowed_transitions.some((a:any)=>a.value===dropTarget(dragged,column.status))?'drop-allowed':''}`} key={column.status}>
                  <header className="order-column-head">
                    <span>{statusIcon[column.status]}</span>
                    <strong>{column.label}</strong>
                    <b>{column.pagination?.count ?? column.orders.length}</b>
                  </header>
                  {column.pagination && <Pagination page={column.pagination.page} pages={column.pagination.pages} size={size} onPage={n=>setFilters(f=>({...f,[column.status==='all'?'all_page':'delivered_page']:String(n)}))} onSize={n=>{setSize(n);setFilters(f=>({...f,all_page:'1',delivered_page:'1'}));}}/>}
                  <div className="order-column-body">
                    {column.orders.length ? (
                      column.orders.map((order: any) => (
                        <OrderCard
                          key={order.id}
                          order={order}
                          busy={busyId !== null}
                          expanded={detailed}
                          onDrag={setDragged}
                          fresh={freshIds.includes(order.id)}
                          onTransition={choose}
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

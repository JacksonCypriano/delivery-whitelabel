import { useEffect, useRef, useState } from "react";
import { actionLabel } from "./orderHelpers";

type Options = { prep_minutes?: number; fulfillment_minutes?: number; message?: string; complement?: string; send_notification?: boolean };

export function TransitionDialog({ order, status, settings, busy, error, onConfirm, onClose }: {
  order: any; status: string; settings: any; busy: boolean; error?: Error | null;
  onConfirm: (options: Options) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const action = order.allowed_transitions.find((item: any) => item.value === status);
  const [message, setMessage] = useState(action?.message || "");
  const [complement, setComplement] = useState("");
  const [send, setSend] = useState(true);
  const [manual, setManual] = useState(false);
  const prep = status === "confirmed" || status === "preparing";
  const fulfillment = status === "out_for_delivery" || (prep && order.delivery_type === "pickup");
  const defaultMinutes = status === "out_for_delivery" ? settings.default_delivery_minutes : order.delivery_type === "pickup" ? settings.default_pickup_minutes : settings.default_prep_minutes;
  const [minutes, setMinutes] = useState(defaultMinutes);
  const enabled = Boolean(action?.notification_enabled && order.customer_phone);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="order-transition-dialog" aria-labelledby="transition-title" onCancel={(e) => { if (busy) e.preventDefault(); else onClose(); }}>
    <form onSubmit={(e) => {
      e.preventDefault();
      const options: Options = {};
      if (manual) {
        if (fulfillment) options.fulfillment_minutes = minutes;
        else if (prep) options.prep_minutes = minutes;
      }
      if (enabled) { options.message = message === action?.message ? undefined : message; options.complement = complement; options.send_notification = send; }
      onConfirm(options);
    }}>
      <h2 id="transition-title">{actionLabel[status] || action?.label} · #{order.id}</h2>
      <p>{order.customer_name} · {order.delivery_label}</p>
      {(prep || fulfillment) && <>
        <label className="toggle-row"><input type="checkbox" checked={manual} onChange={(e) => setManual(e.target.checked)} disabled={busy} />Informar prazo manual</label>
        {manual ? <label className="field">Prazo de {fulfillment ? order.delivery_type === "pickup" ? "retirada" : "entrega" : "preparo"} (minutos)
          <input type="number" min={5} max={240} step={1} required value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} disabled={busy} />
        </label> : <p className="muted">Usar prazo padrão: {defaultMinutes} minutos. O prazo de preparo já registrado é preservado.</p>}
      </>}
      {enabled ? <>
        {settings.allow_skip_notification && <label className="toggle-row"><input type="checkbox" checked={send} onChange={(e) => setSend(e.target.checked)} disabled={busy} />Avisar cliente pelo WhatsApp</label>}
        {send && <>
          <label className="field">Mensagem<textarea maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)} disabled={busy} /></label>
          <button type="button" className="text-button" onClick={() => setMessage(action?.message || "")} disabled={busy}>Usar mensagem padrão</button>
          <label className="field">Complemento opcional<textarea maxLength={500} value={complement} onChange={(e) => setComplement(e.target.value)} disabled={busy} /></label>
          <p className="muted">A previsão calculada será acrescentada ao aviso quando aplicável.</p>
        </>}
      </> : <p className="muted">Sem aviso por WhatsApp para esta alteração: confira as preferências e o telefone do cliente.</p>}
      {error && <p role="alert" className="danger-text">{error.message}</p>}
      <div className="actions"><button type="button" className="secondary" onClick={onClose} disabled={busy}>Voltar</button><button disabled={busy}>{busy ? "Salvando…" : "Confirmar alteração"}</button></div>
    </form>
  </dialog>;
}

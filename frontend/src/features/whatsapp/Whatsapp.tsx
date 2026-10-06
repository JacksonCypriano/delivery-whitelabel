import { useState, useEffect } from "react";
import { whatsapp } from "../../api/whatsapp";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice, Empty } from "../../components/Feedback";
export function Whatsapp() {
  const q = useQuery(whatsapp.get),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [messages, setMessages] = useState<any[]>([]),
    [qr, setQr] = useState<string | null>(null);
  useEffect(() => {
    const timer = window.setInterval(() => {
      whatsapp
        .status()
        .then((s) =>
          q.setData((current: any) =>
            current
              ? {
                  ...current,
                  agent: {
                    ...current.agent,
                    ...s,
                    status_label: s.status_display,
                  },
                }
              : current,
          ),
        )
        .catch(() => {});
    }, 10000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!qr) return;
    const timer = window.setTimeout(() => setQr(null), 60000);
    return () => window.clearTimeout(timer);
  }, [qr]);
  async function action(a: string) {
    if (
      a === "disconnect" &&
      !window.confirm("Desconectar o WhatsApp da loja?")
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const r = await whatsapp.action(a);
      setMessages(r.messages || []);
      setQr(r.qr || null);
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
      <p className="eyebrow">Atendimento</p>
      <h1>WhatsApp e agente</h1>
      <p className="muted">
        Conecte o número da loja e gerencie o atendimento atual.
      </p>
      <Notice messages={messages} />
      <Feedback error={error}>
        <></>
      </Feedback>
      <Feedback loading={q.loading} error={q.error}>
        {d && (
          <>
            <section className="card">
              <span className="badge">{d.agent.status_label}</span>
              <h2>
                {d.agent.ai_enabled ? "Agente ativado" : "Agente desativado"}
              </h2>
              {!d.feature_enabled && (
                <div className="alert">
                  O atendimento inteligente ainda não está habilitado neste
                  ambiente.
                </div>
              )}
              {d.stale && (
                <div className="alert">
                  A situação pode estar desatualizada. Consulte novamente.
                </div>
              )}
              <p>Instância: {d.agent.instance_name}</p>
              <p>
                Último webhook:{" "}
                {d.agent.webhook_at
                  ? new Date(d.agent.webhook_at).toLocaleString("pt-BR")
                  : "Ainda não recebido"}
              </p>
              <p>
                Reconexões tentadas: {d.agent.reconnect_attempts} · Próxima
                tentativa:{" "}
                {d.agent.next_reconnect_at
                  ? new Date(d.agent.next_reconnect_at).toLocaleString("pt-BR")
                  : "—"}
              </p>
              <p>
                Última verificação:{" "}
                {d.agent.checked_at
                  ? new Date(d.agent.checked_at).toLocaleString("pt-BR")
                  : "Ainda não verificado"}
              </p>
              {d.agent.last_error && (
                <p className="field-error">{d.agent.last_error}</p>
              )}
              <div className="actions">
                {[
                  ["connect", "Conectar / gerar QR Code"],
                  ["check", "Consultar conexão"],
                  [
                    "toggle",
                    d.agent.ai_enabled ? "Desativar agente" : "Ativar agente",
                  ],
                  ["disconnect", "Desconectar"],
                ].map(([a, label]) => (
                  <button
                    key={a}
                    className={
                      a === "disconnect" ? "secondary danger-text" : "secondary"
                    }
                    disabled={
                      busy ||
                      !d.feature_enabled ||
                      (a === "toggle" &&
                        !d.agent.ai_enabled &&
                        d.agent.status !== "open")
                    }
                    onClick={() => action(a)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {qr && (
                <div className="qr">
                  <img
                    src={
                      qr.startsWith("data:")
                        ? qr
                        : "data:image/png;base64," + qr
                    }
                    alt="QR Code para conectar o WhatsApp"
                  />
                  <p>
                    No WhatsApp, acesse Dispositivos conectados e escaneie o
                    código.
                  </p>
                </div>
              )}
            </section>
            <section className="card">
              <h2>Como o atendimento funciona</h2>
              <p>
                O agente usa o catálogo, horários, disponibilidade, entrega e
                formas de pagamento já configurados na loja. O contexto da
                conversa expira após {d.context_timeout_minutes} minutos.
              </p>
              <p>
                Quando a equipe responde manualmente, o agente pausa a conversa
                temporariamente. Mensagens geradas pelo fechamento do pedido não
                recebem resposta automática. Nos grupos, a primeira mensagem
                recebe orientação para continuar no privado; depois o grupo
                permanece silencioso.
              </p>
            </section>
            <section className="card">
              <h2>Histórico da conexão</h2>
              {d.events.length ? (
                d.events.map((e: any, i: number) => (
                  <div className="event" key={i}>
                    <small>
                      {new Date(e.created_at).toLocaleString("pt-BR")}
                    </small>
                    <p>{e.description}</p>
                  </div>
                ))
              ) : (
                <Empty />
              )}
            </section>
          </>
        )}
      </Feedback>
    </>
  );
}

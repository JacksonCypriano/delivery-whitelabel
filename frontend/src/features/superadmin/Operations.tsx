import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request, post, formData } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice } from "../../components/Feedback";
import { FieldInput } from "../../components/Fields";
import { Confirm } from "../../components/Confirm";
import { panelUrl } from "../../panel";

export function Credit() {
  const { id } = useParams();
  const endpoint = `subscriptions/${id}/credit/`;
  const q = useQuery(() => request(endpoint), [id]);
  const [preview, setPreview] = useState<any>(null);
  const [pending, setPending] = useState<FormData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [done, setDone] = useState("");
  async function submit(data: FormData) {
    setBusy(true);
    setError(null);
    try {
      const result = await post(endpoint, data);
      if (result.preview) {
        setPending(data);
        setPreview(result);
      } else {
        setDone(`${result.detail} Vencimento: ${result.valid_until}`);
        setPreview(null);
      }
    } catch (e) {
      setError(e as Error);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link to={panelUrl(`billing-subscription/${id}`)}>← Assinatura</Link>
      <h1>Acrescentar meses</h1>
      <Feedback loading={q.loading} error={q.error || error}>
        <>
          {done ? (
            <div role="status" className="alert">
              {done}
            </div>
          ) : (
            q.data && (
              <section className="card">
                <h2>{q.data.tenant}</h2>
                <p>Último plano pago: {q.data.plan}</p>
                <p>
                  {q.data.status} · Vencimento:{" "}
                  {q.data.valid_until || "Sem vencimento"}
                </p>
                {(q.data.manually_blocked || q.data.payment_review) && (
                  <p className="alert">
                    Há bloqueio manual ou revisão de pagamento. Acrescentar
                    meses preserva essas restrições.
                  </p>
                )}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void submit(new FormData(e.currentTarget));
                  }}
                >
                  {q.data.fields.map((f: any) => (
                    <FieldInput key={f.name} field={f} />
                  ))}
                  <button disabled={busy}>
                    {busy ? "Processando…" : "Conferir resultado"}
                  </button>
                </form>
              </section>
            )
          )}
        </>
      </Feedback>
      {preview && (
        <Confirm
          title="Confirmar concessão"
          details={[
            `${preview.months} mês(es). Vencimento: ${preview.previous || "Sem vencimento"} → ${preview.until}`,
            preview.reason,
            "Esta operação registra crédito manual e não cria cobrança no Asaas.",
          ]}
          onClose={() => setPreview(null)}
          onConfirm={() => {
            if (pending) {
              pending.set("preview", preview.preview);
              setPreview(null);
              void submit(pending);
            }
          }}
        />
      )}
    </>
  );
}

export function Prospecting() {
  const q = useQuery(() => request("prospecting/"), []);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const [messages, setMessages] = useState<any[]>([]),
    [confirm, setConfirm] = useState<any>(null);
  useEffect(() => {
    const timer = window.setInterval(q.reload, 15000);
    return () => window.clearInterval(timer);
  }, []);
  async function run(data: FormData) {
    setBusy(true);
    setError(null);
    try {
      const r = await post("prospecting/", data);
      if (r.confirmation_required) setConfirm({ data, details: r.objects });
      else {
        setMessages(r.messages || []);
        q.reload();
      }
    } catch (e: any) {
      setError(e);
      setMessages(e.data?.messages || []);
    } finally {
      setBusy(false);
    }
  }
  const d = q.data;
  return (
    <>
      <h1>Prospecção WhatsApp</h1>
      <Notice messages={messages} />
      <Feedback loading={q.loading} error={q.error || error}>
        <>
          {d && (
            <>
              <section className="card">
                <h2>{d.enabled ? "Campanha ativa" : "Campanha pausada"}</h2>
                <p>
                  {d.pending_count} pendentes · {d.sent_count} telefones
                  abordados · Fila: {d.queue_name}
                </p>
                <p>
                  {d.window_open
                    ? "Janela de envio aberta"
                    : "Fora da janela de envio"}{" "}
                  · {d.timezone}
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    run(
                      formData({
                        prospecting_action: d.enabled ? "pause" : "start",
                      }),
                    )
                  }
                >
                  {d.enabled ? "Pausar campanha" : "Iniciar campanha"}
                </button>
              </section>
              <section className="card">
                <h2>Importar contatos</h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const data = new FormData(e.currentTarget);
                    data.set("prospecting_action", "import");
                    void run(data);
                  }}
                >
                  <label>
                    Planilha XLSX
                    <input
                      name="prospecting_file"
                      type="file"
                      accept=".xlsx"
                      required
                    />
                  </label>
                  <button disabled={busy}>Importar XLSX</button>
                </form>
              </section>
              <section className="card">
                <h2>Janela e velocidade</h2>
                <form
                  key={`${d.start_time}-${d.end_time}-${d.messages_per_minute}-${d.weekdays}`}
                  onSubmit={(e) => {
                    e.preventDefault();
                    const data = new FormData(e.currentTarget);
                    data.set("prospecting_action", "save_settings");
                    void run(data);
                  }}
                >
                  <div className="form-grid">
                    <label>
                      Início
                      <input
                        type="time"
                        name="start_time"
                        defaultValue={d.start_time}
                        required
                      />
                    </label>
                    <label>
                      Fim
                      <input
                        type="time"
                        name="end_time"
                        defaultValue={d.end_time}
                        required
                      />
                    </label>
                    <label>
                      Contatos por minuto
                      <input
                        type="number"
                        min="1"
                        max="10"
                        name="messages_per_minute"
                        defaultValue={d.messages_per_minute}
                        required
                      />
                    </label>
                  </div>
                  <fieldset>
                    <legend>Dias permitidos</legend>
                    {[
                      "Segunda",
                      "Terça",
                      "Quarta",
                      "Quinta",
                      "Sexta",
                      "Sábado",
                      "Domingo",
                    ].map((day, i) => (
                      <label key={day}>
                        <input
                          type="checkbox"
                          name="weekdays"
                          value={i}
                          defaultChecked={d.weekdays.includes(i)}
                        />
                        {day}{" "}
                      </label>
                    ))}
                  </fieldset>
                  <button disabled={busy}>Salvar configuração</button>
                </form>
              </section>
              <section className="card">
                <h2>Lotes e resultados</h2>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Arquivo</th>
                        <th>Situação</th>
                        <th>Total</th>
                        <th>Contatados</th>
                        <th>Pendentes</th>
                        <th>Falhas/incertos</th>
                        <th>Ignorados</th>
                        <th>Ação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.batches.map((b: any) => (
                        <tr key={b.id}>
                          <td>{b.filename}</td>
                          <td>{b.status}</td>
                          <td>{b.total}</td>
                          <td>{b.contacted}</td>
                          <td>{b.pending}</td>
                          <td>{b.issues}</td>
                          <td>{b.ignored}</td>
                          <td>
                            <button
                              className="secondary"
                              disabled={busy}
                              onClick={() =>
                                run(
                                  formData({
                                    prospecting_action: "delete_batch",
                                    batch_id: String(b.id),
                                  }),
                                )
                              }
                            >
                              Remover lote
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Link to={panelUrl("prospecting-prospectingbatch")}>
                  Pesquisar todos os lotes →
                </Link>
              </section>
            </>
          )}
        </>
      </Feedback>
      {confirm && (
        <Confirm
          title="Confirmar operação"
          details={confirm.details}
          onClose={() => setConfirm(null)}
          onConfirm={() => {
            const data = confirm.data;
            data.set("confirmed", "yes");
            setConfirm(null);
            void run(data);
          }}
        />
      )}
    </>
  );
}

export function Evolution() {
  const q = useQuery(() => request("evolution/"), []);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const [messages, setMessages] = useState<any[]>([]),
    [qr, setQr] = useState<string | null>(null);
  useEffect(() => {
    const timer = window.setInterval(q.reload, 15000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!qr) return;
    const timer = window.setTimeout(() => setQr(null), 60000);
    return () => window.clearTimeout(timer);
  }, [qr]);
  async function run(action: string) {
    setBusy(true);
    setError(null);
    setQr(null);
    try {
      const r = await post("evolution/", formData({ action }));
      setMessages(r.messages || []);
      setQr(r.qr || null);
      q.reload();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  const d = q.data,
    c = d?.connection;
  return (
    <>
      <h1>WhatsApp / Evolution API</h1>
      <Notice messages={messages} />
      <Feedback loading={q.loading} error={q.error || error}>
        <>
          {d && (
            <section className="card">
              {c ? (
                <>
                  <h2>
                    {c.environment} · {c.instance}
                  </h2>
                  <p>
                    Situação: {c.status} · Última verificação:{" "}
                    {c.checked_at || "Pendente"}
                  </p>
                  <p>
                    Tentativas: {c.attempts} · {c.reason}
                  </p>
                  {d.stale && (
                    <p className="alert">
                      Estado desatualizado. Solicite uma verificação.
                    </p>
                  )}
                  <div className="actions">
                    <button disabled={busy} onClick={() => run("check")}>
                      Consultar conexão
                    </button>
                    <button
                      disabled={busy || c.manual_required || c.attempts >= 3}
                      onClick={() => run("restart")}
                    >
                      Reconectar
                    </button>
                    <button
                      disabled={busy || !d.pair_allowed}
                      onClick={() => run("pair")}
                    >
                      Exibir QR Code
                    </button>
                  </div>
                </>
              ) : (
                <p>Monitoramento WhatsApp desabilitado neste ambiente.</p>
              )}
            </section>
          )}
          {qr && (
            <section className="card">
              <p>
                Escaneie com o número da plataforma. O QR Code será ocultado em
                60 segundos.
              </p>
              <img
                src={qr}
                alt="QR Code de pareamento da plataforma"
                width="280"
              />
            </section>
          )}
          {d && (
            <section className="card">
              <h2>Eventos recentes</h2>
              {d.events.map((e: any, i: number) => (
                <p key={i}>
                  {e.date} · {e.description}
                </p>
              ))}
              <h2>Alertas</h2>
              {d.alerts.map((a: any, i: number) => (
                <p key={i}>
                  {a.date} · {a.status}
                </p>
              ))}
            </section>
          )}
        </>
      </Feedback>
    </>
  );
}

export function UserPassword() {
  const { id } = useParams();
  const q = useQuery(() => request(`users/${id}/password/`), [id]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [done, setDone] = useState("");
  return (
    <>
      <Link to={panelUrl(`accounts-user/${id}`)}>← Usuário</Link>
      <h1>Alterar senha · {q.data?.username}</h1>
      <Feedback loading={q.loading} error={q.error || error}>
        <>
          {done ? (
            <p role="status">{done}</p>
          ) : (
            q.data && (
              <form
                className="card"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  setBusy(true);
                  setError(null);
                  try {
                    const r = await post(`users/${id}/password/`, data);
                    setDone(r.detail);
                  } catch (e: any) {
                    setError(e);
                    if (e.data?.fields)
                      q.setData({ ...q.data, fields: e.data.fields });
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {q.data.fields.map((f: any) => (
                  <FieldInput key={f.name} field={f} />
                ))}
                <button disabled={busy}>Salvar senha</button>
              </form>
            )
          )}
        </>
      </Feedback>
    </>
  );
}

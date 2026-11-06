import { Pagination } from "../../components/Pagination";
import { panel, panelUrl } from "../../panel";
import { useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
  useOutletContext,
} from "react-router-dom";
import { ApiError } from "../../api/client";
import { finance } from "../../api/finance";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice, Empty } from "../../components/Feedback";
const money = (v: any) =>
  v === null || v === undefined
    ? "Consulte o Asaas"
    : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const date = (v: any) =>
  v
    ? new Date(v.length === 10 ? v + "T12:00:00" : v).toLocaleDateString(
        "pt-BR",
      )
    : "—";
function Note({ note: n }: { note: any }) {
  return (
    <div>
      <p>
        {n.status_label}
        {n.number ? " · Nº " + n.number : ""}
      </p>
      <div className="actions">
        {["pdf", "xml"].map((k) =>
          n[k] ? (
            <a
              className="button secondary"
              key={k}
              href={`${panel.apiBase}finance/invoices/${n.invoice_id}/notes/${k}/`}
            >
              Baixar {k.toUpperCase()}
            </a>
          ) : null,
        )}
      </div>
      <small>
        Os documentos arquivados continuam disponíveis. Observe a situação atual
        da nota, inclusive em caso de cancelamento.
      </small>
    </div>
  );
}
export function Finance({
  mode,
}: {
  mode: "assinatura" | "notas" | "taxas" | "cobrancas";
}) {
  const { id } = useParams(),
    [params, setParams] = useSearchParams(),
    navigate = useNavigate(),
    context = useOutletContext<any>();
  const path =
    mode === "assinatura"
      ? ""
      : mode === "notas"
        ? "notes/"
        : mode === "taxas"
          ? "fees/"
          : `invoices/${id}/`;
  const q = useQuery(
      () => finance.get(path + "?" + params.toString()),
      [path, params.toString()],
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [messages, setMessages] = useState<any[]>([]),
    [purchaseErrors, setPurchaseErrors] = useState<any>({});
  async function submit(path: string, data?: FormData) {
    setBusy(true);
    setError(null);
    setPurchaseErrors({});
    try {
      const r = await finance.post(path, data);
      setMessages(r.messages || []);
      if (r.redirect) navigate(r.redirect);
      q.reload();
    } catch (e) {
      if (e instanceof ApiError)
        setPurchaseErrors({
          quote: data?.get("quote"),
          fields: e.data.errors || {},
        });
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  const d = q.data;
  return (
    <>
      <p className="eyebrow">Financeiro da loja</p>
      <h1>
        {
          {
            assinatura: "Minha assinatura",
            notas: "Notas fiscais",
            taxas: "Tarifas Asaas · somente consulta",
            cobrancas: "Detalhes da cobrança",
          }[mode]
        }
      </h1>
      <nav className="tabs">
        <Link to={panelUrl("assinatura")}>Assinatura e histórico</Link>
        <Link to={panelUrl("notas")}>Notas fiscais</Link>
        {context?.online_payments_allowed && (
          <Link to={panelUrl("taxas")}>Tarifas Asaas</Link>
        )}
      </nav>
      <Notice messages={messages} />
      <Feedback error={error}>
        <></>
      </Feedback>
      <Feedback loading={q.loading} error={q.error}>
        {d && (
          <>
            {d.missing ? (
              <section className="card">
                <h2>Complete o cadastro da loja</h2>
                <p>
                  {Array.isArray(d.missing)
                    ? d.missing.join(", ")
                    : String(d.missing)}
                </p>
                <Link
                  className="button"
                  to={panelUrl("store/" + context.store_id)}
                >
                  Completar minha loja
                </Link>
              </section>
            ) : mode === "assinatura" ? (
              <>
                {d.sandbox && (
                  <div className="alert">
                    Ambiente de testes: cobranças simuladas, sem pagamento real.
                  </div>
                )}
                {!d.ready && (
                  <div className="alert">
                    Novas cobranças estão temporariamente indisponíveis.
                  </div>
                )}
                {(d.subscription.manually_blocked ||
                  d.subscription.payment_review) && (
                  <div className="alert">
                    Existe uma pendência administrativa. Um novo pagamento não
                    remove esse bloqueio. Entre em contato com o suporte.
                  </div>
                )}
                <div className="stats">
                  <section className="card">
                    <span>Situação</span>
                    <strong>{d.subscription.situation}</strong>
                  </section>
                  <section className="card">
                    <span>Vencimento</span>
                    <strong>{date(d.subscription.valid_until)}</strong>
                    <small>
                      {d.subscription.days_remaining} dias restantes
                    </small>
                  </section>
                  <section className="card">
                    <span>Última cobrança</span>
                    <strong>
                      {d.latest_invoice?.status_label || "Nenhuma"}
                    </strong>
                  </section>
                </div>
                {[
                  ["plans", "Planos disponíveis"],
                  ["services", "Serviços adicionais"],
                ].map(([key, title]) => (
                  <section key={key}>
                    <h2>{title}</h2>
                    <p className="muted">
                      {key === "plans"
                        ? "O período vigente é preservado. Os novos meses são somados ao final."
                        : "Contratações avulsas, sem alterar o vencimento da assinatura."}
                    </p>
                    <div className="cards">
                      {d[key].length ? (
                        d[key].map((row: any) => (
                          <article className="card" key={row.item.pk}>
                            <h3>{row.item.name}</h3>
                            <p>
                              {row.item.description}
                              {row.item.months
                                ? `${row.item.months} mês(es)`
                                : ""}
                            </p>
                            {row.options.length ? (
                              row.options.map((o: any) => (
                                <div key={o.quote}>
                                  <h3>{money(o.amount)}</h3>
                                  <p>{o.label}</p>
                                  {d.ready && (
                                    <details>
                                      <summary>Contratar</summary>
                                      <form
                                        onSubmit={(e) => {
                                          e.preventDefault();
                                          submit(
                                            "purchase/",
                                            new FormData(e.currentTarget),
                                          );
                                        }}
                                      >
                                        <input
                                          type="hidden"
                                          name="quote"
                                          value={o.quote}
                                        />
                                        {[
                                          ["name", "Nome / razão social"],
                                          ["document", "CPF / CNPJ"],
                                          ["email", "E-mail financeiro"],
                                        ].map(([n, l]) => (
                                          <label className="field" key={n}>
                                            {l}
                                            <input
                                              required
                                              type={
                                                n === "email" ? "email" : "text"
                                              }
                                              name={n}
                                              defaultValue={
                                                d.customer?.[n] || ""
                                              }
                                            />
                                            {purchaseErrors.quote === o.quote &&
                                              purchaseErrors.fields?.[n]?.map(
                                                (error: string, i: number) => (
                                                  <small
                                                    className="field-error"
                                                    role="alert"
                                                    key={i}
                                                  >
                                                    {error}
                                                  </small>
                                                ),
                                              )}
                                          </label>
                                        ))}
                                        <p>
                                          Compra única, sem renovação
                                          automática. Os dados do pagador serão
                                          usados na cobrança e na nota fiscal.
                                        </p>
                                        <button disabled={busy}>
                                          Gerar cobrança de {money(o.amount)}
                                        </button>
                                      </form>
                                    </details>
                                  )}
                                </div>
                              ))
                            ) : (
                              <p>Nenhuma forma de pagamento habilitada.</p>
                            )}
                          </article>
                        ))
                      ) : (
                        <Empty />
                      )}
                    </div>
                  </section>
                ))}
                <section className="card">
                  <h2>Histórico de cobranças</h2>
                  {d.invoices.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Data</th>
                            <th>Referência</th>
                            <th>Valor</th>
                            <th>Forma</th>
                            <th>Situação</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.invoices.map((b: any) => (
                            <tr key={b.pk}>
                              <td>{date(b.created_at)}</td>
                              <td>{b.plan_name}</td>
                              <td>{money(b.amount)}</td>
                              <td>{b.method_label}</td>
                              <td>{b.status_label}</td>
                              <td>
                                <Link to={panelUrl("cobrancas/" + b.pk)}>
                                  Detalhes →
                                </Link>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty />
                  )}
                </section>
              </>
            ) : mode === "cobrancas" ? (
              <section className="card">
                <h2>{d.invoice.plan_name}</h2>
                <h2>{money(d.invoice.amount)}</h2>
                <p>
                  {d.invoice.method_label} · {d.invoice.status_label}
                </p>
                <p>Vencimento: {date(d.invoice.due_date)}</p>
                {d.invoice.environment === "sandbox" && (
                  <div className="alert">
                    Cobrança de teste: sem pagamento real.
                  </div>
                )}
                {d.invoice.status === "PAID" ? (
                  <div className="alert success">Pagamento confirmado.</div>
                ) : d.invoice.status === "REVIEW" ? (
                  <div className="alert">
                    Esta cobrança exige revisão administrativa. Entre em contato
                    com o suporte.
                  </div>
                ) : d.invoice.checkout_url ? (
                  <a
                    className="button"
                    href={d.invoice.checkout_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Pagar com segurança no Asaas ↗
                  </a>
                ) : (
                  <p>
                    A emissão está sendo verificada. Não é necessário gerar
                    outra cobrança.
                  </p>
                )}
                <p>
                  Para Pix, o QR Code e o código copia e cola aparecem na página
                  de pagamento.
                </p>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => submit(`invoices/${id}/refresh/`)}
                >
                  Já paguei / consultar pagamento
                </button>
                <p>
                  A confirmação é automática e depende da confirmação do
                  provedor.
                </p>
                {d.invoice.note && <Note note={d.invoice.note} />}
              </section>
            ) : mode === "notas" ? (
              <>
                <div className="stats">
                  <section className="card">{d.total ?? 0} notas</section>
                  <section className="card">{d.authorized ?? 0} autorizadas</section>
                  <section className="card">
                    {d.processing ?? 0} em processamento
                  </section>
                </div>
                {(d.notes || []).length ? (
                  d.notes.map((n: any) => (
                    <section className="card" key={n.pk}>
                      <Link to={panelUrl("cobrancas/" + n.invoice_id)}>
                        Ver cobrança →
                      </Link>
                      <Note note={n} />
                    </section>
                  ))
                ) : (
                  <section className="card"><h2>Documentos fiscais</h2><p>Nenhuma nota fiscal emitida para esta loja.</p></section>
                )}
              </>
            ) : (
              <section className="card">
                <p>
                  Esta tela é somente para consulta; o lojista não cadastra taxas aqui. A configuração administrativa permanece no painel do administrador. As vendas online são recebidas na subconta Asaas da loja, sem
                  comissão do VemDeDelivery. As tarifas são definidas e
                  debitadas pelo Asaas.
                </p>
                {d.fee_error ? (
                  <div className="alert error">
                    Não foi possível consultar as tarifas: {d.fee_error}
                  </div>
                ) : d.fee_summary ? (
                  <>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Operação</th>
                            <th>Tarifa</th>
                            <th>Recebimento</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>Pix</td>
                            <td>{money(d.fee_summary.pix.effective)}</td>
                            <td>Em poucos segundos</td>
                          </tr>
                          {d.card_fee_rows.map(([label, percent]: any) => (
                            <tr key={label}>
                              <td>{label}</td>
                              <td>
                                {percent === null
                                  ? "Consulte o Asaas"
                                  : `${percent}%${d.fee_summary.card.fixed !== null ? " + " + money(d.fee_summary.card.fixed) : ""}`}
                              </td>
                              <td>
                                {d.fee_summary.card.days_to_receive
                                  ? `${d.fee_summary.card.days_to_receive} dias`
                                  : "Conforme o Asaas"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {d.fee_summary.next_discount_expiration && (
                      <p>
                        Condição promocional com expiração em{" "}
                        {date(d.fee_summary.next_discount_expiration)}.
                      </p>
                    )}
                  </>
                ) : (
                  <p>
                    As tarifas aparecerão após a criação da subconta. Solicite o
                    recebimento online em Minha loja.
                  </p>
                )}
                <p>
                  As tarifas podem mudar conforme as condições comerciais da sua
                  conta. Os preços dos produtos não são alterados
                  automaticamente.
                </p>
              </section>
            )}
            {(mode === "notas" || mode === "assinatura") && <Pagination page={d.page} pages={d.pages} size={Number(params.get("page_size")||10)} onPage={n=>{const next=new URLSearchParams(params);next.set("pagina",String(n));setParams(next);}} onSize={n=>{const next=new URLSearchParams(params);next.set("page_size",String(n));next.delete("pagina");setParams(next);}}/>}
          </>
        )}
      </Feedback>
    </>
  );
}

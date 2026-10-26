import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request, post } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { FieldInput } from "../../components/Fields";
import { Feedback } from "../../components/Feedback";
import { Confirm } from "../../components/Confirm";
import { panelUrl } from "../../panel";
import { formatDateBR, formatDateTimeBR } from "../../utils/dates";
export function FreeDays() {
  const { id } = useParams();
  const [page, setPage] = useState(1);
  const endpoint = `tenants/${id}/free-days/`;
  const q = useQuery(() => request(`${endpoint}?page=${page}`), [id, page]);
  const [preview, setPreview] = useState<any>(null),
    [pending, setPending] = useState<FormData | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [message, setMessage] = useState("");
  const inFlight = useRef(false);
  async function send(data: FormData) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const r = await post(endpoint, data);
      if (r.preview) {
        setPending(data);
        setPreview(r);
      } else {
        setPreview(null);
        setMessage(
          `${r.detail} Período: ${formatDateBR(r.grant.start)} até ${formatDateBR(r.grant.end)} (término exclusivo). ${r.grant.access_after.active ? "Loja ativa." : "A loja permanece bloqueada por outro motivo."}`,
        );
        q.reload();
      }
    } catch (e: any) {
      setError(e);
      setPreview(null);
      if (e.data?.fields) q.setData({ ...q.data, fields: e.data.fields });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  const d = q.data;
  return (
    <>
      <Link to={panelUrl(`tenants-tenant/${id}`)}>← Loja</Link>
      <h1>Conceder dias gratuitos</h1>
      {message && (
        <p role="status" className="alert">
          {message}
        </p>
      )}
      <Feedback loading={q.loading} error={q.error || error}>
        <>
          {d && (
            <>
              <section className="card">
                <h2>{d.tenant}</h2>
                <p>
                  Último plano pago: {d.plan} · Situação: {d.status}
                </p>
                <p>
                  Validade do acesso: {d.valid_until ? formatDateBR(d.valid_until) : "Sem prazo definido"} ·
                  Loja {d.active ? "ativa" : "inativa"}
                </p>
                <p>
                  Total concedido em dias: {d.total_days} · Fim do período
                  gratuito atual:{" "}
                  {d.free_until ? formatDateBR(d.free_until) : "Nenhum período gratuito em andamento"}
                </p>
                <p>
                  O início está incluído; a data final não está incluída. Datas
                  seguem o fuso do negócio. Eventual tolerância de pagamento é
                  calculada separadamente.
                </p>
                <p className="alert">{d.impact.billing}</p>
                <p>{d.impact.access}</p>
                <form
                  key={`${id}-${d.fields.find((f: any) => f.name === "token")?.value}`}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void send(new FormData(e.currentTarget));
                  }}
                >
                  {d.fields.map((f: any) => (
                    <FieldInput key={f.name} field={f} />
                  ))}
                  <button disabled={busy}>
                    {busy ? "Processando…" : "Conferir período"}
                  </button>
                </form>
              </section>
              <section className="card">
                <h2>Histórico de gratuidades em dias</h2>
                <p>
                  Os créditos anteriores de meses de calendário continuam
                  disponíveis em Créditos e na auditoria de cobrança.
                </p>
                {!d.history.length && (
                  <p>Nenhuma concessão em dias registrada.</p>
                )}
                {d.history.map((g: any) => (
                  <article key={g.operation_id}>
                    <strong>
                      {g.days} dias · {formatDateBR(g.start)} → {formatDateBR(g.end)}
                    </strong>
                    <p>{g.reason}</p>
                    <p>
                      {g.actor} · {formatDateTimeBR(g.date)} ·
                      Validade anterior: {g.previous ? formatDateBR(g.previous) : "Não definida"}
                    </p>
                    <p>
                      Acesso: {g.access_before.active ? "ativo" : "inativo"} →{" "}
                      {g.access_after.active ? "ativo" : "inativo"}
                    </p>
                    <small>Operação: {g.operation_id}</small>
                  </article>
                ))}
                <div className="pagination">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                  >
                    Anterior
                  </button>
                  <span>
                    {d.page}/{d.pages}
                  </span>
                  <button
                    disabled={page >= d.pages}
                    onClick={() => setPage(page + 1)}
                  >
                    Próxima
                  </button>
                </div>
              </section>
            </>
          )}
        </>
      </Feedback>
      {preview && (
        <Confirm
          title="Confirmar gratuidade"
          details={[
            `${preview.days} dias: ${formatDateBR(preview.start)} até ${formatDateBR(preview.end)} (fim exclusivo).`,
            preview.reason,
            preview.impact.access,
            preview.impact.billing,
          ]}
          onClose={() => setPreview(null)}
          onConfirm={() => {
            if (pending) {
              pending.set("preview", preview.preview);
              setPreview(null);
              void send(pending);
            }
          }}
        />
      )}
    </>
  );
}

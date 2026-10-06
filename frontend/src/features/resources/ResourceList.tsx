import { panelUrl } from "../../panel";
import { ListEditor } from "./ListEditor";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { resources } from "../../api/resources";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice, Empty } from "../../components/Feedback";
import { Display } from "../../components/Fields";
import { Confirm } from "../../components/Confirm";
export function ResourceList() {
  const { resource = "" } = useParams(),
    [params, setParams] = useSearchParams(),
    query = useQuery(
      () => resources.list(resource, "?" + params.toString()),
      [resource, params.toString()],
    );
  const [selected, setSelected] = useState<string[]>([]),
    [action, setAction] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [messages, setMessages] = useState<any[]>([]),
    [confirm, setConfirm] = useState<any>(null);
  async function run(confirmed = false) {
    setBusy(true);
    setError(null);
    setConfirm(null);
    try {
      const r = await resources.action(resource, action, selected, confirmed);
      if (r.confirmation_required) setConfirm(r.objects);
      else {
        setSelected([]);
        setMessages(r.messages || [{ level: "success", text: r.detail }]);
        query.reload();
      }
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  const [editing, setEditing] = useState(false);
  const d = query.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Sua operação</p>
          <h1>{d?.title || "Carregando"}</h1>
        </div>
        {d?.can_add && (
          <Link className="button" to="novo">
            Adicionar
          </Link>
        )}
      </div>
      {d?.can_list_edit && !editing && (
        <button className="secondary" onClick={() => setEditing(true)}>
          Editar campos desta página
        </button>
      )}
      {editing && (
        <ListEditor
          resource={resource}
          query={params.toString()}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            setMessages([
              { level: "success", text: "Alterações da página salvas." },
            ]);
            query.reload();
          }}
        />
      )}
      <Notice messages={messages} />
      <Feedback error={error}>
        <></>
      </Feedback>
      <Feedback loading={query.loading} error={query.error}>
        {d && (
          <>
            {d.metrics?.generated !== undefined && (
              <>
                <h2>Pedidos · últimos 30 dias</h2>
                <div className="cards">
                  {[
                    ["generated", "Pedidos gerados"],
                    ["whatsapp_opened", "WhatsApp aberto"],
                    ["conversion", "Conversão até WhatsApp (%)"],
                    ["revenue", "Faturamento potencial (R$)"],
                    ["avg_ticket", "Ticket médio (R$)"],
                  ].map(([k, l]) => (
                    <section className="card" key={k}>
                      <small>{l}</small>
                      <h2>{d.metrics[k]}</h2>
                    </section>
                  ))}
                </div>
                {d.metrics.top_products.length > 0 && (
                  <section className="card">
                    <h2>Produtos mais pedidos · 30 dias</h2>
                    {d.metrics.top_products.map((p: any) => (
                      <p key={p.name}>
                        {p.name} · {p.quantity} un.
                      </p>
                    ))}
                  </section>
                )}
              </>
            )}
            <section className="card">
              <form
                className="toolbar"
                onSubmit={(e) => {
                  e.preventDefault();
                  const q = String(
                    new FormData(e.currentTarget).get("q") || "",
                  );
                  const next = new URLSearchParams(params);
                  next.set("q", q);
                  next.delete("p");
                  setParams(next);
                }}
              >
                <input
                  aria-label="Buscar"
                  name="q"
                  placeholder="Buscar registros…"
                  defaultValue={params.get("q") || ""}
                />
                <button type="submit" className="secondary">
                  Buscar
                </button>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setParams({})}
                >
                  Limpar filtros
                </button>
              </form>
              {d.date_hierarchy?.show && (
                <nav className="actions" aria-label="Filtrar por data">
                  {d.date_hierarchy.back && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        setParams(d.date_hierarchy.back.link.replace(/^\?/, ""))
                      }
                    >
                      ← {d.date_hierarchy.back.title}
                    </button>
                  )}
                  {d.date_hierarchy.choices?.map((c: any, i: number) =>
                    c.link ? (
                      <button
                        type="button"
                        className="secondary"
                        key={i}
                        onClick={() => setParams(c.link.replace(/^\?/, ""))}
                      >
                        {c.title}
                      </button>
                    ) : (
                      <span key={i}>{c.title}</span>
                    ),
                  )}
                </nav>
              )}
              <div className="filters">
                {d.filters.map((f: any, i: number) => (
                  <label key={i}>
                    {f.title}
                    <select
                      value={
                        f.options.find((o: any) => o.selected)?.query || ""
                      }
                      onChange={(e) => {
                        setSelected([]);
                        setParams(e.target.value.replace(/^\?/, ""));
                      }}
                    >
                      {f.options.map((o: any, j: number) => (
                        <option key={j} value={o.query}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              {d.actions.length > 0 && (
                <div className="toolbar">
                  <select
                    aria-label="Ação em selecionados"
                    value={action}
                    onChange={(e) => setAction(e.target.value)}
                  >
                    <option value="">Ações em selecionados</option>
                    {d.actions.map((a: any) => (
                      <option key={a.name} value={a.name}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={busy || !selected.length || !action}
                    onClick={() => run()}
                  >
                    {busy ? "Processando…" : `Aplicar (${selected.length})`}
                  </button>
                </div>
              )}
              {d.rows.length === 0 ? (
                <Empty />
              ) : (
                <div className="table-scroll">
                  <table className="resource-table">
                    <thead>
                      <tr>
                        <th>
                          <input
                            type="checkbox"
                            aria-label="Selecionar página"
                            checked={
                              selected.length === d.rows.length &&
                              d.rows.length > 0
                            }
                            onChange={(e) =>
                              setSelected(
                                e.target.checked
                                  ? d.rows.map((r: any) => String(r.id))
                                  : [],
                              )
                            }
                          />
                        </th>
                        {d.columns.map((c: any) => (
                          <th key={c.name}>
                            {c.sort ? (
                              <button
                                type="button"
                                className="sort-button"
                                onClick={() =>
                                  setParams(c.sort.replace(/^\?/, ""))
                                }
                              >
                                {c.label} ↕
                              </button>
                            ) : (
                              c.label
                            )}
                          </th>
                        ))}
                        <th>Detalhes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.rows.map((row: any) => (
                        <tr key={row.id}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={"Selecionar " + row.id}
                              checked={selected.includes(String(row.id))}
                              onChange={(e) =>
                                setSelected(
                                  e.target.checked
                                    ? [...selected, String(row.id)]
                                    : selected.filter(
                                        (id) => id !== String(row.id),
                                      ),
                                )
                              }
                            />
                          </td>
                          {row.values.map((v: any, i: number) => (
                            <td key={i} data-label={d.columns[i].label}>
                              <Display value={v} />
                            </td>
                          ))}
                          <td data-label="Detalhes">
                            <Link to={String(row.id)}>Abrir →</Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <nav className="pagination" aria-label="Paginação">
                <span>{d.count} registros</span>
                <button
                  className="secondary"
                  disabled={d.page <= 1}
                  onClick={() => {
                    const next = new URLSearchParams(params);
                    next.set("p", String(d.page - 1));
                    setParams(next);
                    setSelected([]);
                  }}
                >
                  Anterior
                </button>
                <span>
                  {d.page} / {d.pages}
                </span>
                <button
                  className="secondary"
                  disabled={d.page >= d.pages}
                  onClick={() => {
                    const next = new URLSearchParams(params);
                    next.set("p", String(d.page + 1));
                    setParams(next);
                    setSelected([]);
                  }}
                >
                  Próxima
                </button>
              </nav>
            </section>
          </>
        )}
      </Feedback>
      {confirm && (
        <Confirm
          title="Confirmar ação"
          details={confirm}
          onClose={() => setConfirm(null)}
          onConfirm={() => run(true)}
        />
      )}
    </>
  );
}

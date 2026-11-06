import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { Feedback } from "../../components/Feedback";
export function Activity() {
  const [page, setPage] = useState(1);
  const q = useQuery(() => request(`activity/?page=${page}`), [page]);
  return (
    <section className="card">
      <h2>Atividades administrativas recentes</h2>
      <Feedback loading={q.loading} error={q.error}>
        <>
          {q.data && (
            <>
              {!q.data.rows.length && <p>Nenhuma atividade acessível.</p>}
              {q.data.rows.map((r: any) => (
                <article key={r.id}>
                  <p>
                    <strong>{r.type}</strong> ·{" "}
                    {r.url ? <Link to={r.url}>{r.object}</Link> : r.object}
                  </p>
                  <p>
                    {r.resource} · {r.user} ·{" "}
                    {new Date(r.date).toLocaleString("pt-BR")}
                  </p>
                  <p>{r.action}</p>
                </article>
              ))}
              <div className="pagination">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Anterior
                </button>
                <span>
                  {q.data.page} / {q.data.pages}
                </span>
                <button
                  disabled={page >= q.data.pages}
                  onClick={() => setPage(page + 1)}
                >
                  Próxima
                </button>
              </div>
            </>
          )}
        </>
      </Feedback>
    </section>
  );
}

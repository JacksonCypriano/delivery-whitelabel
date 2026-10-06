import { request } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Empty } from "../../components/Feedback";
import { useState } from "react";
export function History({ resource, id }: { resource: string; id: string }) {
  const [page, setPage] = useState(1),
    q = useQuery(
      () => request(`resources/${resource}/${id}/history/?page=${page}`),
      [resource, id, page],
    );
  return (
    <section className="card">
      <h2>Histórico de alterações</h2>
      <Feedback loading={q.loading} error={q.error}>
        {q.data && (
          <>
            {q.data.rows.length ? (
              q.data.rows.map((row: any, i: number) => (
                <div className="event" key={i}>
                  <small>
                    {new Date(row.date).toLocaleString("pt-BR")} · {row.user}
                  </small>
                  <p>{row.action}</p>
                </div>
              ))
            ) : (
              <Empty />
            )}
            <div className="pagination">
              <button
                className="secondary"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Anterior
              </button>
              <span>
                {page} / {q.data.pages}
              </span>
              <button
                className="secondary"
                disabled={page >= q.data.pages}
                onClick={() => setPage(page + 1)}
              >
                Próxima
              </button>
            </div>
          </>
        )}
      </Feedback>
    </section>
  );
}

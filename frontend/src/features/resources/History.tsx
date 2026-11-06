import { Pagination } from "../../components/Pagination";
import { request } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Empty } from "../../components/Feedback";
import { useState } from "react";
export function History({ resource, id }: { resource: string; id: string }) {
  const [size,setSize] = useState(10), [page, setPage] = useState(1),
    q = useQuery(
      () => request(`resources/${resource}/${id}/history/?page=${page}&page_size=${size}`),
      [resource, id, page, size],
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
            <Pagination page={q.data.page} pages={q.data.pages} size={size} onPage={setPage} onSize={n=>{setSize(n);setPage(1);}}/>
          </>
        )}
      </Feedback>
    </section>
  );
}

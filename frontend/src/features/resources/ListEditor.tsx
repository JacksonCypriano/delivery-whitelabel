import { useState } from "react";
import { request, post, ApiError } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { FormFields } from "../../components/Fields";
import { Feedback } from "../../components/Feedback";
export function ListEditor({
  resource,
  query,
  onClose,
  onSaved,
}: {
  resource: string;
  query: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const path = `resources/${resource}/list-edit/?${query}`,
    q = useQuery(() => request(path), [path]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [version, setVersion] = useState(0);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(path, new FormData(e.currentTarget));
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.data.rows) {
        q.setData(e.data);
        setVersion((n) => n + 1);
      }
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>Edição rápida desta página</h2>
      <p>Os campos são os mesmos da edição em lista do painel anterior.</p>
      <Feedback loading={q.loading} error={q.error}>
        <Feedback error={error}>
          <></>
        </Feedback>
        {q.data && (
          <form onSubmit={save} key={version}>
            {q.data.management.map((f: any) => (
              <input
                key={f.html_name}
                type="hidden"
                name={f.html_name}
                value={f.value}
              />
            ))}
            {q.data.errors.map((e: string, i: number) => (
              <p className="field-error" key={i}>
                {e}
              </p>
            ))}
            {q.data.rows.map((row: any, i: number) => (
              <div className="inline-row" key={i}>
                <h3>{row.title}</h3>
                <FormFields row={row} />
              </div>
            ))}
            <div className="actions">
              <button disabled={busy}>
                {busy ? "Salvando…" : "Salvar página"}
              </button>
              <button
                type="button"
                disabled={busy}
                className="secondary"
                onClick={onClose}
              >
                Cancelar edição
              </button>
            </div>
          </form>
        )}
      </Feedback>
    </section>
  );
}

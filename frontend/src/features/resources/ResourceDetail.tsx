import { panelUrl } from "../../panel";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { resources } from "../../api/resources";
import { ApiError } from "../../api/client";
import { useQuery } from "../../hooks/useQuery";
import { Feedback, Notice } from "../../components/Feedback";
import {
  FieldInput,
  FormFields,
  Display,
  splitDates,
} from "../../components/Fields";
import { History } from "./History";
import { Confirm } from "../../components/Confirm";
export function ResourceDetail() {
  const { resource = "", id = "novo" } = useParams(),
    navigate = useNavigate(),
    q = useQuery(() => resources.detail(resource, id), [resource, id]);
  const [error, setError] = useState<Error | null>(null),
    [busy, setBusy] = useState(false),
    [messages, setMessages] = useState<any[]>([]),
    [confirm, setConfirm] = useState<any>(null),
    [generation, setGeneration] = useState(0),
    [history, setHistory] = useState(false);
  const d = q.data;
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const data = new FormData(e.currentTarget);
    splitDates(data, [
      ...d.fields,
      ...d.inlines.flatMap((g: any) => g.forms.flatMap((f: any) => f.fields)),
    ]);
    try {
      const r = await resources.save(resource, id, data);
      setMessages([
        { level: "success", text: r.detail },
        ...(r.messages || []),
      ]);
      navigate(panelUrl(`${resource}/${r.id}`), { replace: true });
      q.reload();
    } catch (e) {
      if (e instanceof ApiError && e.data.fields) {
        q.setData(e.data);
        setGeneration((n) => n + 1);
        setError(new Error("Confira os campos destacados."));
      } else setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function remove(confirmed = false) {
    setBusy(true);
    setConfirm(null);
    try {
      const r = await resources.remove(resource, id, confirmed);
      if (r.confirmation_required) setConfirm(r.objects);
      else navigate(panelUrl(resource));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  function addInline(index: number) {
    const g = d.inlines[index],
      number = g.forms.length;
    const empty = JSON.parse(
      JSON.stringify(g.empty).replaceAll("__prefix__", String(number)),
    );
    q.setData({
      ...d,
      inlines: d.inlines.map((x: any, i: number) =>
        i === index
          ? {
              ...x,
              forms: [...x.forms, empty],
              management: x.management.map((f: any) =>
                f.name === "TOTAL_FORMS" ? { ...f, value: number + 1 } : f,
              ),
            }
          : x,
      ),
    });
  }
  const shown = new Set(d?.sections.flatMap((s: any) => s.fields) || []);
  return (
    <>
      <Link className="back" to={panelUrl(resource)}>
        ← Voltar
      </Link>
      <div className="page-heading">
        <h1>{id === "novo" ? "Novo cadastro" : d?.title || "Detalhes"}</h1>
        {d?.can_delete && (
          <button
            className="secondary danger-text"
            disabled={busy}
            onClick={() => remove()}
          >
            Excluir
          </button>
        )}
      </div>
      {id !== "novo" && (
        <button className="text-button" onClick={() => setHistory(!history)}>
          Histórico de alterações
        </button>
      )}
      {history && id !== "novo" && <History resource={resource} id={id} />}
      <Notice messages={messages} />
      <Feedback error={error}>
        <></>
      </Feedback>
      <Feedback loading={q.loading} error={q.error}>
        {d && (
          <form onSubmit={save} key={resource + id + generation}>
            {d.errors.map((e: string, i: number) => (
              <div className="alert error" role="alert" key={i}>
                {e}
              </div>
            ))}
            {d.sections.map((section: any, i: number) => (
              <section className="card" key={i}>
                <h2>{section.title}</h2>
                {section.description && (
                  <p className="muted">{section.description}</p>
                )}
                <div className="form-grid">
                  {section.fields.map((name: string) => {
                    const f = d.fields.find((x: any) => x.name === name),
                      r = d.readonly.find((x: any) => x.name === name);
                    return f ? (
                      <FieldInput key={name} field={f} />
                    ) : r ? (
                      <div key={name} className="field readonly">
                        <label>{r.label}</label>
                        <strong>
                          <Display value={r.value} />
                        </strong>
                      </div>
                    ) : null;
                  })}
                </div>
              </section>
            ))}
            {d.fields
              .filter((f: any) => !shown.has(f.name))
              .map((f: any) => (
                <FieldInput key={f.html_name} field={f} />
              ))}
            {d.inlines.map((g: any, i: number) => (
              <section className="card" key={g.prefix}>
                <h2>{g.title}</h2>
                {g.prefix.includes("payment") && (
                  <div className="alert">
                    <strong>Recebimento pela subconta Asaas</strong>
                    <p>
                      Pix e cartão de crédito serão recebidos na subconta da
                      loja, sem comissão do VemDeDelivery. O Asaas cobra suas
                      próprias tarifas, pode solicitar documentos e deve aprovar
                      o cadastro. As instruções de ativação serão enviadas ao
                      e-mail informado. A plataforma não armazena dados de
                      cartão; a chave técnica é protegida.
                    </p>
                    <Link to={panelUrl("taxas")}>Consultar tarifas</Link>
                  </div>
                )}
                {g.management.map((f: any) => (
                  <input
                    key={f.html_name}
                    type="hidden"
                    name={f.html_name}
                    value={f.value}
                  />
                ))}
                {g.errors.map((e: string, j: number) => (
                  <p className="field-error" key={j}>
                    {e}
                  </p>
                ))}
                {g.forms.map((row: any, j: number) => (
                  <div className="inline-row" key={j}>
                    <h3>
                      {g.title} · {j + 1}
                    </h3>
                    <FormFields row={row} />
                  </div>
                ))}
                {g.can_add && g.forms.length < g.max && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => addInline(i)}
                  >
                    + Adicionar {g.title.toLowerCase()}
                  </button>
                )}
              </section>
            ))}
            {d.can_save && (
              <div className="save-bar">
                <span>Confira as informações antes de salvar.</span>
                <button disabled={busy}>
                  {busy ? "Salvando…" : "Salvar alterações"}
                </button>
              </div>
            )}
          </form>
        )}
      </Feedback>
      {confirm && (
        <Confirm
          title="Excluir cadastro"
          details={confirm}
          onClose={() => setConfirm(null)}
          onConfirm={() => remove(true)}
        />
      )}
    </>
  );
}

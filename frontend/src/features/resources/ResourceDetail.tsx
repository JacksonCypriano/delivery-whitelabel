import { resourceDescription } from "./presentation";
import { panel, panelUrl } from "../../panel";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams } from "react-router-dom";
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
  const { resource = "", id = "novo" } = useParams();
  // A reused route must never carry form/preview/history state into another record.
  return <ResourceEditor key={`${resource}:${id}`} resource={resource} id={id} />;
}

function ResourceEditor({ resource, id }: { resource: string; id: string }) {
  const navigate = useNavigate();
  const original = useRef<any>(null);
  const loaded = useRef<any>(null);
  const loadGeneration = useRef(0);
  const alive = useRef(true);
  const form = useRef<HTMLFormElement>(null);
  const baseline = useRef<string | null>(null);
  const allowNavigation = useRef(false);
  const q = useQuery(async () => {
    const generation = ++loadGeneration.current;
    const data = await resources.detail(resource, id);
    if (alive.current && generation === loadGeneration.current) { original.current = structuredClone(data); loaded.current = data; }
    return data;
  }, [resource, id]);
  const [error, setError] = useState<Error | null>(null),
    [busy, setBusy] = useState(false),
    [messages, setMessages] = useState<any[]>([]),
    [confirm, setConfirm] = useState<any>(null),
    [generation, setGeneration] = useState(0),
    [history, setHistory] = useState(false);
  const [createPreview, setCreatePreview] = useState<any>(null);
  const [createData, setCreateData] = useState<FormData | null>(null);
  const [dirty, setDirty] = useState(false);
  const saving = useRef(false);
  const d = q.data;
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    !allowNavigation.current && (dirty || busy) &&
    (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));
  function fingerprint() {
    if (!form.current) return "";
    return JSON.stringify(Array.from(new FormData(form.current).entries(), ([name, value]) =>
      [name, typeof value === "string" ? value : !value.name && value.size === 0 ? null : [value.name, value.size, value.lastModified]]));
  }
  function updateDirty() {
    if (baseline.current !== null) setDirty(fingerprint() !== baseline.current);
  }
  useLayoutEffect(() => {
    if (d && d === loaded.current && !q.loading && form.current && baseline.current === null) baseline.current = fingerprint();
  }, [d, generation, q.loading]);
  useEffect(() => {
    alive.current = true;
    const forcedExit = () => { allowNavigation.current = true; };
    // Authentication redirects must never be blocked by an unsaved form.
    window.addEventListener("session-expired", forcedExit, true);
    window.addEventListener("password-required", forcedExit, true);
    return () => {
      alive.current = false;
      window.removeEventListener("session-expired", forcedExit, true);
      window.removeEventListener("password-required", forcedExit, true);
    };
  }, []);
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!allowNavigation.current && (dirty || busy)) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty, busy]);
  function discard() {
    if (!original.current || busy) return;
    if (!window.confirm("Descartar as alterações e restaurar os dados carregados deste cadastro?")) return;
    const restored = structuredClone(original.current);
    loaded.current = restored; baseline.current = null;
    q.setData(restored);
    setGeneration(value => value + 1);
    setDirty(false); setError(null); setMessages([]);
    setCreatePreview(null); setCreateData(null); setConfirm(null);
  }

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (saving.current) return;
    setBusy(true);
    setError(null);
    const data = new FormData(e.currentTarget);
    splitDates(data, [
      ...d.fields,
      ...d.inlines.flatMap((g: any) => g.forms.flatMap((f: any) => f.fields)),
    ]);
    await submitData(data);
  }
  async function submitData(data: FormData) {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError(null);
    try {
      const r = await resources.save(resource, id, data);
      if (!alive.current) return;
      if (r.free_days_preview) {
        setCreateData(data);
        setCreatePreview(r);
        return;
      }
      setMessages([
        { level: "success", text: r.detail },
        ...(r.messages || []),
      ]);
      // An existing record usually stays on the same route after saving.
      // Never leave the navigation bypass enabled in that situation.
      setDirty(false);
      baseline.current = null;
      loaded.current = null;
      setCreatePreview(null);
      setCreateData(null);
      if (id !== "novo" && String(r.id) === id) {
        allowNavigation.current = false;
        // Reload the persisted server values, remounting uncontrolled inputs.
        // This also resets conditional inline field state after a successful save.
        q.reload();
      } else {
        allowNavigation.current = true;
        navigate(panelUrl(`${resource}/${r.id}`), { replace: true });
      }
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof ApiError && e.data.fields) {
        q.setData(e.data);
        // Keep uncontrolled inputs and selected files mounted on validation errors.
        setError(new Error("Confira os campos destacados."));
      } else setError(e as Error);
    } finally {
      saving.current = false;
      if (alive.current) setBusy(false);
    }
  }
  async function remove(confirmed = false) {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setConfirm(null);
    try {
      const r = await resources.remove(resource, id, confirmed);
      if (!alive.current) return;
      if (r.confirmation_required) setConfirm(r.objects);
      else { allowNavigation.current = true; navigate(panelUrl(resource)); }
    } catch (e) {
      if (alive.current) setError(e as Error);
    } finally {
      saving.current = false;
      if (alive.current) setBusy(false);
    }
  }
  function addInline(index: number) {
    allowNavigation.current = false;
    setDirty(true);
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
      {blocker.state === "blocked" && <Confirm
        title={busy ? "Operação em andamento" : "Sair sem salvar?"}
        details={busy ? "A operação já foi enviada. Aguarde a conclusão para evitar dúvidas sobre o resultado." : "As alterações deste cadastro serão descartadas ao sair."}
        onClose={() => blocker.reset()}
        onConfirm={() => { if (busy) blocker.reset(); else blocker.proceed(); }}
      />}
      <Link className="back" to={panelUrl(resource)}>
        ← Voltar
      </Link>
      <div className="page-heading">
        <div><p className="eyebrow">{id === "novo" ? "Cadastrar" : "Editar cadastro"}</p><h1>{d?.title || (id === "novo" ? "Novo cadastro" : "Detalhes")}</h1><p className="muted">{resourceDescription(resource)}</p></div>
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
      {panel.kind === "superadmin" &&
        resource === "accounts-user" &&
        id !== "novo" && (
          <Link
            className="button secondary"
            to={panelUrl(`accounts-user/${id}/senha`)}
          >
            Alterar senha
          </Link>
        )}
      {d?.free_days_url && (
        <Link className="button" to={d.free_days_url}>
          Conceder dias gratuitos (quantidade personalizada)
        </Link>
      )}
      {id !== "novo" && (
        <button className="text-button" aria-expanded={history} onClick={() => setHistory(!history)}>
          Histórico de alterações
        </button>
      )}
      {createPreview && (
        <Confirm
          title="Confirmar cadastro com gratuidade"
          details={createPreview.details}
          onClose={() => setCreatePreview(null)}
          onConfirm={() => {
            if (createData) {
              createData.set(
                "free_days_preview",
                createPreview.free_days_preview,
              );
              setCreatePreview(null);
              void submitData(createData);
            }
          }}
        />
      )}
      {history && id !== "novo" && <History resource={resource} id={id} />}
      <Notice messages={messages} />
      <Feedback error={error}>
        <></>
      </Feedback>
      {q.error && <button type="button" className="secondary" onClick={q.reload}>Tentar carregar novamente</button>}
      <Feedback loading={q.loading} error={q.error}>
        {d && (
          <form ref={form} onSubmit={save} onChange={() => { allowNavigation.current = false; updateDirty(); }} onInput={() => { allowNavigation.current = false; updateDirty(); }} onClick={event => {
            if ((event.target as HTMLElement).closest(".relationship-choice button, .relationship-results button")) {
              allowNavigation.current = false;
              window.setTimeout(() => { if (alive.current) updateDirty(); }, 0);
            }
          }} aria-busy={busy} key={`${resource}:${id}:${loadGeneration.current}:${generation}`}>
            <fieldset className="editor-fields" disabled={busy}>
            {d.sections.length + d.inlines.length > 3 && <nav className="section-index" aria-label="Seções do cadastro">
              {d.sections.map((section: any, i: number) => <a key={i} href={`#resource-section-${i}`}>{section.title}</a>)}
              {d.inlines.map((group: any, i: number) => <a key={group.prefix} href={`#resource-inline-${i}`}>{group.title}</a>)}
            </nav>}
            {d.can_save && <p className="muted">Campos com * são obrigatórios. As alterações são aplicadas ao salvar.</p>}
            {d.errors.map((e: string, i: number) => (
              <div className="alert error" role="alert" key={i}>
                {e}
              </div>
            ))}
            {d.sections.map((section: any, i: number) => (
              <section className="card form-section" id={`resource-section-${i}`} key={i}>
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
              <section className="card form-section" id={`resource-inline-${i}`} key={g.prefix}>
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
                <span role="status">{busy ? "Salvando alterações…" : dirty ? "Você tem alterações não salvas." : "Confira as informações antes de salvar."}</span>
                <button type="button" className="secondary" disabled={busy || !dirty} onClick={discard}>Cancelar alterações</button>
                <button disabled={busy}>
                  {busy ? "Salvando…" : "Salvar alterações"}
                </button>
              </div>
            )}
            </fieldset>
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

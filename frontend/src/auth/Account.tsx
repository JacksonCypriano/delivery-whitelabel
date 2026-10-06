import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { request, post, ApiError } from "../api/client";
import { panel, panelUrl } from "../panel";
export function Account({ password = false }: { password?: boolean }) {
  const navigate = useNavigate(),
    [errors, setErrors] = useState<Record<string, string[]>>({}),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [ready, setReady] = useState(false),
    [store, setStore] = useState("");
  useEffect(() => {
    request("session/")
      .then((d) => {
        setReady(true);
        setStore(d.store || "");
      })
      .catch((e) => setError(e.message));
  }, []);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setErrors({});
    try {
      const d = await post(
        password ? "password/" : "session/",
        new FormData(e.currentTarget),
      );
      navigate(d.password_change_required ? panelUrl("senha") : panelUrl(), {
        replace: true,
      });
    } catch (e) {
      if (e instanceof ApiError) setErrors(e.data.errors || {});
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const fields = password
    ? [
        ["old_password", "Senha atual"],
        ["new_password1", "Nova senha"],
        ["new_password2", "Confirme a nova senha"],
      ]
    : [
        ["username", "Usuário"],
        ["password", "Senha"],
      ];
  return (
    <div className="auth-page">
      <section className="card">
        <div className="brand">
          Vem<span>DeDelivery</span>
        </div>
        <p className="eyebrow">{store || panel.title}</p>
        <h1>{password ? "Altere sua senha" : "Bem-vindo de volta"}</h1>
        <p className="muted">
          {password
            ? "Escolha uma senha pessoal para continuar."
            : panel.kind === "superadmin" ? "Acesse a administração global da plataforma." : "Acesse sua loja para cuidar da operação."}
        </p>
        <form onSubmit={submit}>
          {fields.map(([name, label]) => (
            <label className="field" key={name}>
              {label}
              <input
                name={name}
                type={name === "username" ? "text" : "password"}
                autoComplete={
                  name === "username"
                    ? "username"
                    : name.startsWith("new_")
                      ? "new-password"
                      : "current-password"
                }
                required
                aria-invalid={!!errors[name]}
              />
              {errors[name]?.map((e, i) => (
                <small className="field-error" key={i}>
                  {e}
                </small>
              ))}
            </label>
          ))}
          {errors.__all__?.map((e, i) => (
            <p className="field-error" key={i}>
              {e}
            </p>
          ))}
          {error && (
            <p role="alert" className="field-error">
              {error}
            </p>
          )}
          <button disabled={!ready || busy}>
            {busy
              ? "Aguarde…"
              : password
                ? "Salvar nova senha"
                : panel.kind === "superadmin" ? "Entrar na administração" : "Entrar na loja"}
          </button>
        </form>
      </section>
    </div>
  );
}
export function Logout() {
  const navigate = useNavigate(),
    [error, setError] = useState("");
  return (
    <div className="auth-page">
      <section className="card">
        <h1>Sair da conta?</h1>
        <button
          onClick={() =>
            request("session/", { method: "DELETE" })
              .then(() => navigate(panelUrl("login"), { replace: true }))
              .catch((e) => setError(e.message))
          }
        >
          Sair
        </button>
        <button className="secondary" onClick={() => navigate(panelUrl())}>
          Voltar
        </button>
        {error && <p role="alert">{error}</p>}
      </section>
    </div>
  );
}

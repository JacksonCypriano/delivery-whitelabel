import { panel, panelUrl } from "../../panel";
import { Link, useOutletContext } from "react-router-dom";
export function Dashboard() {
  const d = useOutletContext<any>();
  if (panel.kind === "superadmin") {
    return (
      <>
        <div className="page-heading">
          <div>
            <p className="eyebrow">Visão geral</p>
            <h1>Administração global</h1>
            <p className="muted">Gestão central da plataforma VemDeDelivery.</p>
          </div>
        </div>
        <div className="stats">
          <section className="card"><span>Módulos disponíveis</span><strong>{d.stats?.resources || 0}</strong></section>
          <section className="card"><span>Áreas administrativas</span><strong>{Object.keys(d.groups || {}).length}</strong></section>
        </div>
        <div className="cards">
          {d.resources.map((r: any) => (
            <Link className="card shortcut" key={r.key} to={panelUrl(r.key)}>
              <h3>{r.title}</h3><span>Acessar →</span>
            </Link>
          ))}
        </div>
      </>
    );
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Visão geral</p>
          <h1>Olá, {d.store}</h1>
          <p className="muted">Tudo para cuidar da sua loja, em um só lugar.</p>
        </div>
        <a
          className="button secondary"
          href={d.public_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Ver minha loja ↗
        </a>
      </div>
      <div className="stats">
        <Link to={panelUrl("products")} className="card">
          <span>Produtos</span>
          <strong>{d.stats.products}</strong>
        </Link>
        <Link to={panelUrl("categories")} className="card">
          <span>Categorias</span>
          <strong>{d.stats.categories}</strong>
        </Link>
        <Link to={panelUrl("assinatura")} className="card">
          <span>Minha assinatura</span>
          <strong>{d.subscription.situation}</strong>
        </Link>
      </div>
      <section className="card">
        <div className="page-heading">
          <h2>
            {d.setup.complete
              ? "Sua loja está pronta para publicar"
              : "Vamos preparar sua loja"}
          </h2>
          <strong>{d.setup.percent}%</strong>
        </div>
        <progress value={d.setup.percent} max={100} />
        <div className="checklist">
          {d.setup.steps
            .filter((s: any) => s.required)
            .map((s: any) => (
              <Link key={s.key} to={s.url}>
                <span className={"check " + (s.complete ? "done" : "")}>
                  {s.complete ? "✓" : "○"}
                </span>
                <div>
                  <strong>{s.title}</strong>
                  <p>{s.description}</p>
                </div>
                <span>→</span>
              </Link>
            ))}
        </div>
      </section>
      <div className="cards">
        {d.resources.map((r: any) => (
          <Link className="card shortcut" key={r.key} to={panelUrl(r.key)}>
            <h3>{r.title}</h3>
            <span>Acessar →</span>
          </Link>
        ))}
      </div>
    </>
  );
}

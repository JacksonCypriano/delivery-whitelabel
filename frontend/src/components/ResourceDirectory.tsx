import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { panelUrl } from "../panel";

type Resource = { key: string; title: string; group: string };
const titles: Record<string, string> = {
  tenants: "Lojas", accounts: "Acessos e segurança", billing: "Cobrança",
  fiscal: "Fiscal", integrations: "Integrações", marketplace: "Marketplace",
  marketing: "Marketing", prospecting: "Prospecção", orders: "Operação",
  catalog: "Cardápio", customers: "Relacionamento", settings: "Minha loja",
};
const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");

export function ResourceDirectory({ resources }: { resources: Resource[] }) {
  const [search, setSearch] = useState("");
  const id = useId();
  const visible = resources.filter(resource => normalize(`${resource.title} ${titles[resource.group] || resource.group}`).includes(normalize(search.trim())));
  const groups = Array.from(new Set(visible.map(resource => resource.group)));
  return <section className="resource-directory" aria-labelledby={id}>
    <div className="page-heading">
      <div><h2 id={id}>Áreas de gestão</h2><p className="muted">Encontre os cadastros e as configurações disponíveis para sua conta.</p></div>
      <label className="directory-search">Buscar área
        <input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Ex.: produtos, cobrança…" />
      </label>
    </div>
    {search && <p role="status" className="muted">{visible.length} área(s) encontrada(s).</p>}
    {groups.map(group => <section key={group} className="directory-group">
      <h3>{titles[group] || group}</h3>
      <div className="cards">{visible.filter(resource => resource.group === group).map(resource =>
        <Link className="card shortcut" key={resource.key} to={panelUrl(resource.key)}>
          <strong>{resource.title}</strong><span>Acessar →</span>
        </Link>)}
      </div>
    </section>)}
    {!visible.length && <div className="empty">Nenhuma área encontrada. <button type="button" className="text-button" onClick={() => setSearch("")}>Limpar busca</button></div>}
  </section>;
}

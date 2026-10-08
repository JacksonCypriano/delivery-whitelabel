import { useState, useEffect } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { request } from "../api/client";
import { useQuery } from "../hooks/useQuery";
import { Feedback } from "../components/Feedback";
import { panel, panelUrl } from "../panel";

const merchantGroups = [
  ["orders", "Operação"],
  ["catalog", "Cardápio"],
  ["customers", "Relacionamento"],
  ["marketing", "Marketing"],
  ["settings", "Minha loja"],
];

const adminGroups = [
  ["tenants", "Lojas"],
  ["accounts", "Acessos e segurança"],
  ["billing", "Cobrança"],
  ["fiscal", "Fiscal"],
  ["integrations", "Integrações"],
  ["marketplace", "Marketplace"],
  ["marketing", "Marketing"],
  ["prospecting", "Prospecção"],
];

export function MerchantLayout() {
  const navigate = useNavigate(),
    location = useLocation(),
    [open, setOpen] = useState(false),
    q = useQuery(async () => {
      const s = await request("session/");
      if (!s.authenticated) {
        navigate(panelUrl("login"), { replace: true });
        throw new Error("Entre na sua conta para continuar.");
      }
      if (s.password_change_required) {
        navigate(panelUrl("senha"), { replace: true });
        throw new Error("Altere sua senha para continuar.");
      }
      return request("dashboard/");
    });
  useEffect(() => setOpen(false), [location.pathname]);
  const d = q.data;
  const groups = panel.kind === "superadmin" ? adminGroups : merchantGroups;

  return (
    <Feedback loading={q.loading} error={q.error}>
      {d && (
        <div className="app-shell">
          <aside className={open ? "sidebar open" : "sidebar"}>
            <NavLink className="brand" to={panelUrl()}>
              Vem<span>DeDelivery</span>
            </NavLink>
            <div className="store-label">{d.store}</div>
            <nav aria-label="Menu principal">
              <NavLink to={panelUrl()} end>
                ◈ Visão geral
              </NavLink>
              {panel.kind === "merchant" && <NavLink to={panelUrl("operacao")}>⚡ Pedidos ativos</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("atendimento")}>Atendimento humano</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("crm")}>CRM e fidelidade</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("logistica")}>Logística</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("automacoes")}>Automações</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("cozinha")}>Cozinha / KDS</NavLink>}
              {groups.map(([group, title]) => {
                const links = d.resources.filter((r: any) => r.group === group);
                if (!links.length) return null;
                return (
                  <details className="nav-group" key={group} open>
                    <summary className="nav-label">{title}</summary>
                    {links.map((r: any) => (
                      <NavLink key={r.key} to={panelUrl(r.key)}>
                        {r.title}
                      </NavLink>
                    ))}
                  </details>
                );
              })}
              {panel.kind === "merchant" && (
                <>
                  <details className="nav-group" open><summary className="nav-label">Atendimento e financeiro</summary>
                  <NavLink to={panelUrl("whatsapp")}>WhatsApp e agente</NavLink>
                  <NavLink to={panelUrl("assinatura")}>Minha assinatura</NavLink>
                  <NavLink to={panelUrl("notas")}>Notas fiscais</NavLink>
                  {d.online_payments_allowed && (
                    <NavLink to={panelUrl("taxas")}>Tarifas Asaas · consulta</NavLink>
                  )}</details>
                </>
              )}
              <details className="nav-group" open><summary className="nav-label">Conta</summary>
              <NavLink to={panelUrl("senha")}>Alterar senha</NavLink>
              <NavLink to={panelUrl("logout")}>Sair</NavLink></details>
            </nav>
          </aside>
          {open && (
            <button
              aria-label="Fechar menu"
              className="scrim"
              onClick={() => setOpen(false)}
            />
          )}
          <div className="main-column">
            <header>
              <button
                className="menu-toggle secondary"
                aria-expanded={open}
                onClick={() => setOpen(!open)}
              >
                ☰ Menu
              </button>
              <span>{panel.title}</span>
              {panel.kind === "merchant" && d.public_url && (
                <a href={d.public_url} target="_blank" rel="noopener noreferrer">
                  Ver loja ↗
                </a>
              )}
            </header>
            <main id="main">
              <Outlet context={d} />
            </main>
            <footer>VemDeDelivery · Sua operação, em um só lugar.</footer>
          </div>
        </div>
      )}
    </Feedback>
  );
}

import { useState, useEffect, useRef } from "react";
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
    [commercialPending, setCommercialPending] = useState(0),
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
  useEffect(() => {
    setOpen(false);
    if (document.activeElement?.closest(".sidebar")) document.getElementById("main")?.focus();
  }, [location.pathname]);
  useEffect(() => {
    if (panel.kind !== 'superadmin') return;
    let active = true;
    const update = () => {
      void request('commercial/?alerts_only=1')
        .then((response: any) => { if (active) setCommercialPending(Math.max(0, Number(response.pending_count) || 0)); })
        .catch(() => { /* Navigation remains available if polling fails. */ });
    };
    update();
    const timer = window.setInterval(update, 30000);
    return () => { active = false; window.clearInterval(timer); };
  }, [location.pathname]);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const relativePath = location.pathname.slice(panel.basePath.length).replace(/^\/|\/$/g, "");
  const operational = ["orders", "operacao", "cozinha"].includes(relativePath) || relativePath.startsWith("orders/");
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebar.current?.querySelector<HTMLElement>("a")?.focus();
    const close = () => { setOpen(false); menuButton.current?.focus(); };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key === "Tab") {
        const items = Array.from(sidebar.current?.querySelectorAll<HTMLElement>("a, button, summary") || [])
          .filter(node => node.getClientRects().length > 0);
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    const desktop = window.matchMedia("(min-width: 761px)");
    const onResize = () => { if (desktop.matches) close(); };
    document.addEventListener("keydown", onKey);
    desktop.addEventListener("change", onResize);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKey);
      desktop.removeEventListener("change", onResize);
    };
  }, [open]);
  const d = q.data;
  const groups = panel.kind === "superadmin" ? adminGroups : merchantGroups;

  return (
    <Feedback loading={q.loading} error={q.error}>
      {d && (
        <div className="app-shell">
          <a className="skip-link" href="#main">Pular para o conteúdo</a>
          <aside ref={sidebar} id="panel-navigation" className={open ? "sidebar open" : "sidebar"}>
            <NavLink className="brand" to={panelUrl()}>
              Vem<span>DeDelivery</span>
            </NavLink>
            <button type="button" className="sidebar-close secondary" onClick={() => { setOpen(false); menuButton.current?.focus(); }}>Fechar menu ×</button>
            <div className="store-label">{d.store}</div>
            <nav aria-label="Menu principal">
              <NavLink to={panelUrl()} end>
                ◈ Visão geral
              </NavLink>
              {panel.kind === "superadmin" && <><NavLink to={panelUrl("comercial")} end>Agente comercial</NavLink><NavLink to={panelUrl("comercial/inbox")}>Inbox comercial{commercialPending>0&&<span className="commercial-nav-count" aria-label={`${commercialPending} atendimentos pendentes`}>{commercialPending}</span>}</NavLink></>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("operacao")}>⚡ Pedidos ativos</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("atendimento")}>Atendimento humano</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("crm")}>CRM e fidelidade</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("logistica")}>Logística</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("automacoes")}>Automações</NavLink>}
              {panel.kind === "merchant" && <NavLink to={panelUrl("impressao")}>Impressão</NavLink>}
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
                  <details className="nav-group" open><summary className="nav-label">Integrações</summary>
                  <NavLink to={panelUrl("integracoes/ifood")}>iFood</NavLink>
                  <NavLink to={panelUrl("integracoes/99food")}>99Food</NavLink>
                  <NavLink to={panelUrl("whatsapp")}>WhatsApp e agente</NavLink>
                  </details><details className="nav-group" open><summary className="nav-label">Financeiro</summary><NavLink to={panelUrl("assinatura")}>Minha assinatura</NavLink>
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
                ref={menuButton}
                type="button"
                aria-controls="panel-navigation"
                className="menu-toggle secondary"
                aria-expanded={open}
                onClick={() => setOpen(!open)}
              >
                ☰ Menu
              </button>
              <span>{panel.title}</span>
              {panel.kind === "superadmin" && <NavLink className="commercial-header-alert" to={panelUrl("comercial/inbox")} aria-label={`Atendimentos comerciais: ${commercialPending} pendentes`}>🔔 {commercialPending>0?`${commercialPending} pendente${commercialPending===1?'':'s'}`:'Inbox comercial'}</NavLink>}
              {panel.kind === "merchant" && d.public_url && (
                <a href={d.public_url} target="_blank" rel="noopener noreferrer">
                  Ver loja ↗
                </a>
              )}
            </header>
            <main id="main" tabIndex={-1} className={operational ? "operational-content" : relativePath === "comercial/inbox" ? "inbox-content" : "admin-content"}>
              <Outlet context={d} />
            </main>
            <footer>VemDeDelivery · Sua operação, em um só lugar.</footer>
          </div>
        </div>
      )}
    </Feedback>
  );
}

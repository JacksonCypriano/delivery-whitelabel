import { useEffect } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { MerchantLayout } from "../layouts/MerchantLayout";
import { Account, Logout } from "../auth/Account";
import { Dashboard } from "../features/dashboard/Dashboard";
import { ResourceList } from "../features/resources/ResourceList";
import { ResourceDetail } from "../features/resources/ResourceDetail";
import { Finance } from "../features/finance/Finance";
import { Whatsapp } from "../features/whatsapp/Whatsapp";
import { panel, panelUrl } from "../panel";

export function App() {
  const navigate = useNavigate();
  useEffect(() => {
    const expired = () => navigate(panelUrl("login"), { replace: true });
    const password = () => navigate(panelUrl("senha"), { replace: true });
    window.addEventListener("session-expired", expired);
    window.addEventListener("password-required", password);
    return () => {
      window.removeEventListener("session-expired", expired);
      window.removeEventListener("password-required", password);
    };
  }, [navigate]);

  return (
    <Routes>
      <Route path={panelUrl("login")} element={<Account />} />
      <Route path={panelUrl("senha")} element={<Account password />} />
      <Route path={panelUrl("logout")} element={<Logout />} />
      <Route path={panel.basePath} element={<MerchantLayout />}>
        <Route index element={<Dashboard />} />
        {panel.kind === "merchant" && (
          <>
            <Route path="whatsapp" element={<Whatsapp />} />
            <Route path="assinatura" element={<Finance mode="assinatura" />} />
            <Route path="notas" element={<Finance mode="notas" />} />
            <Route path="taxas" element={<Finance mode="taxas" />} />
            <Route path="cobrancas/:id" element={<Finance mode="cobrancas" />} />
          </>
        )}
        <Route path=":resource" element={<ResourceList />} />
        <Route path=":resource/:id" element={<ResourceDetail />} />
      </Route>
      <Route
        path="*"
        element={
          <div className="card">
            <h1>Página não encontrada</h1>
            <a href={panelUrl()}>Voltar ao painel</a>
          </div>
        }
      />
    </Routes>
  );
}

import React from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { App } from "./routes/App";
import "./style.css";
function PanelError() {
  return (
      <div className="card" role="alert">
        <h1>Não foi possível abrir esta tela.</h1>
        <p>Atualize a página para tentar novamente.</p>
        <button onClick={() => location.reload()}>Atualizar</button>
      </div>
  );
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <PanelError />
    ) : (
      this.props.children
    );
  }
}
// Data-router context enables useBlocker; App retains all existing nested routes.
const router = createBrowserRouter([{ path: "*", element: <App />, errorElement: <PanelError /> }]);

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
    </ErrorBoundary>
  </React.StrictMode>,
);

import "./panel-design.css";

import "./admin-workspace.css";

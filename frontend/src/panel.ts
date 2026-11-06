export type PanelKind = "merchant" | "superadmin";

declare global {
  interface Window {
    __VDD_PANEL__?: {
      kind?: PanelKind;
      basePath?: string;
      apiBase?: string;
      title?: string;
    };
  }
}

const injected = window.__VDD_PANEL__ || {};

export const panel = {
  kind: injected.kind || "merchant",
  basePath: (injected.basePath || "/painel").replace(/\/$/, ""),
  apiBase: injected.apiBase || "/api/merchant/",
  title: injected.title || "Painel da loja",
};

export const panelUrl = (path = "") =>
  `${panel.basePath}${path ? `/${path.replace(/^\//, "")}` : "/"}`;

import { request } from "./client";

const jsonPost = <T = any>(path: string, data: any) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

export const orders = {
  board: () => request("orders/"),
  detail: (id: string | number) => request(`orders/${id}/`),
  transition: (
    id: string | number,
    status: string,
    options: { prep_minutes?: number; note?: string } = {},
  ) => jsonPost(`orders/${id}/transition/`, { status, ...options }),
  estimate: (id: string | number, minutes: number) =>
    jsonPost(`orders/${id}/estimate/`, { minutes }),
  settings: () => request("orders/settings/"),
  saveSettings: (data: any) => jsonPost("orders/settings/", data),
  manualCatalog: () => request("orders/manual/catalog/"),
  quoteManual: (data: any) => jsonPost("orders/manual/quote/", data),
  createManual: (data: any) => jsonPost("orders/manual/", data),
};

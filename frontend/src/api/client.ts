import { panel } from "../panel";
export class ApiError extends Error {
  constructor(
    public status: number,
    public data: any,
  ) {
    super(
      data.detail && typeof data.detail === "string"
        ? data.detail
        : status === 403
          ? "Você não tem permissão para esta ação."
          : status === 401
            ? "Sua sessão expirou. Entre novamente."
            : "Confira os dados e tente novamente.",
    );
  }
}
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function request<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 90000);
  const url = path.startsWith("/api/cep/") ? path : panel.apiBase + path;
  try {
    const response = await fetch(url, {
      ...options,
      credentials: "same-origin",
      signal: options.signal || controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.method && options.method !== "GET"
          ? { "X-CSRFToken": csrf }
          : {}),
        ...options.headers,
      },
    });
    const data = await response
      .json()
      .catch(() => ({
        detail: "Não foi possível carregar a resposta. Tente novamente.",
      }));
    if (!response.ok) {
      if (response.status === 401)
        window.dispatchEvent(new Event("session-expired"));
      if (
        data.code === "password_change_required" ||
        data.detail?.code === "password_change_required"
      )
        window.dispatchEvent(new Event("password-required"));
      throw new ApiError(response.status, data);
    }
    if (data.csrf) setCsrf(data.csrf);
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new Error(
      "Não foi possível conectar. Confira sua conexão e tente novamente.",
    );
  } finally {
    window.clearTimeout(timer);
  }
}
export function formData(data: Record<string, string | string[]>) {
  const form = new FormData();
  for (const [key, value] of Object.entries(data)) {
    for (const v of Array.isArray(value) ? value : [value]) form.append(key, v);
  }
  return form;
}
export const post = (path: string, data: FormData) =>
  request(path, { method: "POST", body: data });

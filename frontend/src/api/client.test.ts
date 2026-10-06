// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { request, setCsrf, ApiError } from "./client";
afterEach(() => vi.unstubAllGlobals());
describe("Cliente centralizado", () => {
  it("envia sessão e CSRF nas mutações", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetch);
    setCsrf("csrf-test");
    await request("resources/products/1/", {
      method: "POST",
      body: new FormData(),
    });
    expect(fetch.mock.calls[0][0]).toBe("/api/merchant/resources/products/1/");
    expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("csrf-test");
  });
  it("sinaliza sessão expirada sem perder status e erros", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 401,
          json: async () => ({ detail: "Sessão expirada" }),
        }),
    );
    const event = vi.fn();
    window.addEventListener("session-expired", event, { once: true });
    await expect(request("dashboard/")).rejects.toBeInstanceOf(ApiError);
    expect(event).toHaveBeenCalledOnce();
  });
  it("preserva erros de campos retornados pelo backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 400,
          json: async () => ({ errors: { price: ["Valor inválido"] } }),
        }),
    );
    try {
      await request("resources/products/1/");
    } catch (e) {
      expect((e as ApiError).data.errors.price).toEqual(["Valor inválido"]);
    }
  });
});

// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { request, setCsrf, ApiError } from "./client";
afterEach(() => vi.unstubAllGlobals());
describe("Cliente centralizado", () => {
  it("envia sessão e CSRF nas mutações", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, headers: new Headers(), json: async () => ({ ok: true }) });
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

describe('Exportação autenticada', () => {
  it('baixa a resposta binária com o nome retornado pelo servidor', async () => {
    const create = vi.fn(() => 'blob:export');
    Object.defineProperty(URL, 'createObjectURL', {configurable:true,value:create});
    Object.defineProperty(URL, 'revokeObjectURL', {configurable:true,value:vi.fn()});
    const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
    const blob=new Blob(['loja;valor\nTeste;149'],{type:'text/csv'});
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,headers:new Headers({'Content-Disposition':'attachment; filename="conferencia.csv"'}),blob:async()=>blob}));
    await request('resources/billing-fiscalinvoice/actions/',{method:'POST',body:new FormData()});
    expect(create).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledOnce();
    expect((click.mock.instances[0] as unknown as HTMLAnchorElement).download).toBe('conferencia.csv');
    click.mockRestore();
  });
});

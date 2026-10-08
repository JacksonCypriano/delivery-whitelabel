// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { claimOrderAlerts } from "./orderAlerts";
beforeEach(() => { localStorage.clear(); });
describe("Deduplicação de alertas", () => {
  it("não alerta de novo por pedido já reclamado em outra aba", async () => {
    expect(await claimOrderAlerts([11, 12])).toEqual([11, 12]);
    expect(await claimOrderAlerts([12, 13])).toEqual([13]);
  });
  it("usa exclusão mútua do navegador quando disponível", async () => {
    const request = vi.fn(async (_name, callback) => callback());
    Object.defineProperty(navigator, "locks", { configurable: true, value: { request } });
    expect(await claimOrderAlerts([22])).toEqual([22]);
    expect(request).toHaveBeenCalledWith("vdd-order-alerts", expect.any(Function));
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
  });
  it("não repete alertas se o armazenamento estiver corrompido", async () => {
    localStorage.setItem("vdd_order_alert_claims", "bad-json");
    expect(await claimOrderAlerts([33])).toEqual([]);
  });
});

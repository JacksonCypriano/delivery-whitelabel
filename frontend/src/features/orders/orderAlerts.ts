// Same-origin tabs share a claim for each incoming order. Web Locks serialize
// the storage update where available; unsupported browsers still dedupe locally.
export async function claimOrderAlerts(ids: number[]): Promise<number[]> {
  const claim = () => {
    const key = "vdd_order_alert_claims";
    try {
      const stored = JSON.parse(localStorage.getItem(key) || "{}");
      const claims: Record<string, number> = stored && typeof stored === "object" && !Array.isArray(stored) ? stored : {};
      const now = Date.now();
      for (const id of Object.keys(claims)) if (now - claims[id] > 86400000) delete claims[id];
      const fresh = ids.filter((id) => !claims[id]);
      for (const id of fresh) claims[id] = now;
      localStorage.setItem(key, JSON.stringify(claims));
      return fresh;
    } catch { return []; }
  };
  if (navigator.locks) return navigator.locks.request("vdd-order-alerts", claim);
  return claim();
}

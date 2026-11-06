import { describe, expect, it } from "vitest";
import { formatDateBR, formatDateTimeBR } from "./dates";

describe("datas administrativas no padrão brasileiro", () => {
  it("converte datas ISO sem aplicar conversão de fuso horário", () => {
    expect(formatDateBR("2026-10-06")).toBe("06/10/2026");
    expect(formatDateBR("2027-05-26")).toBe("26/05/2027");
    expect(formatDateBR(null)).toBe("—");
    expect(formatDateBR("Sem vencimento")).toBe("Sem vencimento");
  });
  it("mostra instantes em São Paulo e preserva o dia local", () => {
    expect(formatDateTimeBR("2026-10-26T02:00:00Z")).toMatch(/25\/10\/2026/);
  });
});

import { describe, it, expect } from "vitest";
import {
  formatWhatsapp,
  formatPhone,
  formatDocument,
  normalizeTime,
} from "./masks";
describe("Máscaras preservadas do painel anterior", () => {
  it("mantém país para WhatsApp e remove no telefone Asaas", () => {
    expect(formatWhatsapp("11999991111")).toBe("+55 (11) 99999-1111");
    expect(formatPhone("5511999991111")).toBe("(11) 99999-1111");
  });
  it("aceita CPF e CNPJ alfanumérico como o script anterior", () => {
    expect(formatDocument("12345678901")).toBe("123.456.789-01");
    expect(formatDocument("AB123456000190")).toBe("AB.123.456/0001-90");
  });
  it("normaliza horários curtos sem aceitar horários impossíveis", () => {
    expect(normalizeTime("7")).toBe("07:00");
    expect(normalizeTime("730")).toBe("07:30");
    expect(normalizeTime("29:80")).toBe("29:80");
  });
});

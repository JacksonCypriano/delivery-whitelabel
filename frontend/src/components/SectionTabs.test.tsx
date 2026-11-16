// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SectionTabs } from "./SectionTabs";

afterEach(cleanup);
const sections = [
  { id: "settings", label: "Configuração", content: <label>Rascunho<input defaultValue="Original" /></label> },
  { id: "history", label: "Histórico", content: <button>Ver registro</button> },
];

it("preserves draft values while switching tabs and hides inactive actions", () => {
  render(<SectionTabs label="Área" sections={sections} />);
  expect(screen.queryByRole("button", { name: "Ver registro" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Rascunho"), { target: { value: "Não salvo" } });
  fireEvent.click(screen.getByRole("tab", { name: "Histórico" }));
  expect(screen.getByRole("button", { name: "Ver registro" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "Configuração" }));
  expect((screen.getByLabelText("Rascunho") as HTMLInputElement).value).toBe("Não salvo");
});

it("moves keyboard focus and selection together", () => {
  render(<SectionTabs label="Área" sections={sections} />);
  const first = screen.getByRole("tab", { name: "Configuração" });
  const last = screen.getByRole("tab", { name: "Histórico" });
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowRight" });
  expect(document.activeElement).toBe(last);
  expect(last.getAttribute("aria-selected")).toBe("true");
  fireEvent.keyDown(last, { key: "Home" });
  expect(document.activeElement).toBe(first);
  expect(first.getAttribute("aria-selected")).toBe("true");
});

// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { FieldInput, splitDates } from "./Fields";
import type { Field } from "../types/forms";
afterEach(cleanup);
const field: Field = {
  name: "name",
  html_name: "name",
  label: "Nome",
  kind: "text",
  value: "Produto",
  required: true,
  disabled: false,
  help: "Nome no cardápio",
  choices: [],
  errors: [],
  split: false,
};
describe("Formulários do lojista", () => {
  it("exibe erro próximo ao campo e mantém valor enviado", () => {
    render(<FieldInput field={{ ...field, errors: ["Nome já utilizado."] }} />);
    expect(screen.getByLabelText("Nome *").getAttribute("aria-invalid")).toBe(
      "true",
    );
    expect(screen.getByRole("alert").textContent).toBe("Nome já utilizado.");
    expect((screen.getByLabelText("Nome *") as HTMLInputElement).value).toBe(
      "Produto",
    );
  });
  it("mantém seleção múltipla de dias como valores separados", () => {
    render(
      <form data-testid="form">
        <FieldInput
          field={{
            ...field,
            name: "available_days",
            html_name: "available_days",
            kind: "multiple",
            value: [0, 2],
            choices: [
              { value: "0", label: "Segunda" },
              { value: "1", label: "Terça" },
              { value: "2", label: "Quarta" },
            ],
          }}
        />
      </form>,
    );
    const data = new FormData(screen.getByTestId("form") as HTMLFormElement);
    expect(data.getAll("available_days")).toEqual(["0", "2"]);
  });
  it("permite manter imagem atual sem reenviar arquivo obrigatório", () => {
    render(
      <FieldInput
        field={{
          ...field,
          kind: "file",
          value: { url: "/media/test.png", label: "test.png" },
        }}
      />,
    );
    expect((screen.getByLabelText("Nome *") as HTMLInputElement).required).toBe(
      false,
    );
  });
  it("converte data e hora para o formulário Django sem mudar o horário", () => {
    const data = new FormData();
    data.set("starts_at", "2026-10-05T18:30");
    splitDates(data, [{ ...field, html_name: "starts_at", split: true }]);
    expect(data.get("starts_at_0")).toBe("2026-10-05");
    expect(data.get("starts_at_1")).toBe("18:30");
    expect(data.has("starts_at")).toBe(false);
  });
  it("checkbox desmarcado fica ausente do FormData", () => {
    render(
      <form data-testid="form">
        <FieldInput field={{ ...field, kind: "checkbox", value: true }} />
      </form>,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    expect(
      new FormData(screen.getByTestId("form") as HTMLFormElement).has("name"),
    ).toBe(false);
  });
});

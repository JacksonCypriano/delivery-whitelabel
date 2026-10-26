// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { RelationshipInput } from "./RelationshipInput";
import { FormFields } from "./Fields";
import { request } from "../api/client";
import type { Field } from "../types/forms";
vi.mock("../api/client", () => ({ request: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const field: Field = {
  name: "customer",
  html_name: "assignments-0-customer",
  label: "Cliente",
  kind: "relationship",
  value: "",
  required: true,
  disabled: false,
  choices: [],
  help: "",
  errors: [],
  split: false,
  lookup: "resources/coupons/1/relationships/?field=customer",
};
describe("Busca de relacionamentos e campos condicionais", () => {
  it("pesquisa remotamente, pagina, seleciona e limpa com validação", async () => {
    vi.mocked(request).mockImplementation(async (url: any) => ({
      results: [
        {
          value: url.includes("page=2") ? "2" : "1",
          label: url.includes("page=2") ? "Segundo" : "Primeiro",
        },
      ],
      more: !url.includes("page=2"),
    }));
    render(
      <form data-testid="form">
        <RelationshipInput field={field} />
      </form>,
    );
    const input = screen.getByLabelText(
      "Pesquisar Cliente",
    ) as HTMLInputElement;
    expect(input.validity.valid).toBe(false);
    fireEvent.change(input, { target: { value: "Ana" } });
    await screen.findByText("Primeiro");
    expect(vi.mocked(request).mock.calls.at(-1)?.[0]).toContain("q=Ana");
    fireEvent.click(screen.getByText("Próxima"));
    fireEvent.click(await screen.findByText("Segundo"));
    await waitFor(() => expect(input.validity.valid).toBe(true));
    expect(
      new FormData(screen.getByTestId("form") as HTMLFormElement).get(
        field.html_name,
      ),
    ).toBe("2");
    fireEvent.click(screen.getByLabelText("Remover Segundo"));
    await waitFor(() => expect(input.validity.valid).toBe(false));
  });
  it("preserva múltiplos registros selecionados", () => {
    render(
      <form data-testid="form">
        <RelationshipInput
          field={{
            ...field,
            disabled: true,
            multiple: true,
            choices: [
              { value: "1", label: "Ana" },
              { value: "2", label: "Bia" },
            ],
          }}
        />
      </form>,
    );
    expect(screen.getByText("Ana")).toBeTruthy();
    expect(screen.getByText("Bia")).toBeTruthy();
  });
  it("retira obrigatoriedade dos horários quando a loja fecha", () => {
    const closed = {
      ...field,
      name: "is_closed",
      html_name: "is_closed",
      label: "Fechado",
      kind: "checkbox",
      value: false,
      required: false,
    };
    const time = {
      ...field,
      name: "opening_time",
      html_name: "opening_time",
      label: "Abertura",
      kind: "time",
    };
    render(
      <FormFields row={{ fields: [closed, time], readonly: [], errors: [] }} />,
    );
    expect(
      (screen.getByLabelText("Abertura *") as HTMLInputElement).required,
    ).toBe(true);
    fireEvent.click(screen.getByLabelText("Fechado"));
    expect(
      (screen.getByLabelText("Abertura") as HTMLInputElement).required,
    ).toBe(false);
  });
});

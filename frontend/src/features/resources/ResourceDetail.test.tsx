// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ResourceDetail } from "./ResourceDetail";
import { resources } from "../../api/resources";
import { ApiError } from "../../api/client";

vi.mock("../../api/resources", () => ({ resources: { detail: vi.fn(), save: vi.fn(), remove: vi.fn() } }));
const routers: ReturnType<typeof createMemoryRouter>[] = [];
const dialogMethods = {
  showModal: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal"),
  close: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close"),
};
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
});
afterAll(() => {
  for (const name of ["showModal", "close"] as const) {
    const descriptor = dialogMethods[name];
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  }
});

function schema(name = "Original") {
  const common = { required: false, disabled: false, help: "", choices: [], errors: [], split: false };
  return {
    title: "Produto", can_save: true, can_delete: false,
    fields: [
      { ...common, name: "name", html_name: "name", label: "Nome", kind: "text", value: name },
      { ...common, name: "image", html_name: "image", label: "Imagem", kind: "file", value: null },
    ],
    sections: [{ title: "Dados", fields: ["name", "image"] }],
    readonly: [], errors: [] as string[], inlines: [],
  };
}
beforeEach(() => {
  vi.mocked(resources.detail).mockImplementation(async () => schema());
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("Unexpected network access"); }));
});
afterEach(() => {
  cleanup();
  routers.splice(0).forEach(router => router.dispose());
  vi.restoreAllMocks(); vi.resetAllMocks(); vi.unstubAllGlobals();
});

async function openEditor() {
  // Mirror App's /painel/:resource and /painel/:resource/:id routes.
  // The editor needs the :resource param for both Back and post-save navigation.
  const router = createMemoryRouter([{
    path: "/painel",
    children: [
      { path: ":resource", element: <h1>Lista de produtos</h1> },
      { path: ":resource/:id", element: <ResourceDetail /> },
    ],
  }], { initialEntries: ["/painel/products/1"] });
  routers.push(router);
  render(<RouterProvider router={router} />);
  await screen.findByLabelText("Nome");
  expect(resources.detail).toHaveBeenCalledWith("products", "1");
  return router;
}

it("blocks leaving a dirty form and discards only after explicit confirmation", async () => {
  await openEditor();
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Editado" } });
  fireEvent.click(screen.getByRole("link", { name: "← Voltar" }));
  await screen.findByRole("heading", { name: "Sair sem salvar?" });
  fireEvent.click(screen.getByRole("button", { name: "Continuar neste cadastro" }));
  expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Editado");
  fireEvent.click(screen.getByRole("link", { name: "← Voltar" }));
  fireEvent.click(await screen.findByRole("button", { name: "Descartar e sair" }));
  await screen.findByRole("heading", { name: "Lista de produtos" });
  expect(resources.save).not.toHaveBeenCalled();
});

it("cancel restores loaded values and clears the unsaved navigation guard", async () => {
  await openEditor();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Editado" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancelar alterações" }));
  expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Original");
  fireEvent.click(screen.getByRole("link", { name: "← Voltar" }));
  await screen.findByRole("heading", { name: "Lista de produtos" });
  expect(screen.queryByText("Sair sem salvar?")).toBeNull();
});

it("preserves text and the selected file input after API validation errors", async () => {
  await openEditor();
  const fileInput = screen.getByLabelText("Imagem") as HTMLInputElement;
  const file = new File(["image"], "photo.png", { type: "image/png" });
  fireEvent.change(fileInput, { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Editado" } });
  const invalid = schema("Editado");
  invalid.errors = ["Nome já utilizado."];
  vi.mocked(resources.save).mockRejectedValue(new ApiError(400, invalid));
  fireEvent.submit(fileInput.form!);
  await screen.findByText("Confira os campos destacados.");
  expect(screen.getByLabelText("Imagem")).toBe(fileInput);
  expect(fileInput.files?.[0]).toBe(file);
  expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Editado");
  fireEvent.click(screen.getByRole("link", { name: "← Voltar" }));
  await screen.findByRole("heading", { name: "Sair sem salvar?" });
});

it("reloads persisted values after successful save and allows leaving", async () => {
  await openEditor();
  vi.mocked(resources.save).mockResolvedValue({ id: 1, detail: "Salvo." });
  vi.mocked(resources.detail).mockResolvedValue(schema("Nome salvo"));
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Nome salvo" } });
  fireEvent.submit((screen.getByLabelText("Nome") as HTMLInputElement).form!);
  await waitFor(() => expect(resources.detail).toHaveBeenCalledTimes(2));
  await waitFor(() => expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Nome salvo"));
  const body = vi.mocked(resources.save).mock.calls[0][2];
  expect(body.get("name")).toBe("Nome salvo");
  fireEvent.click(screen.getByRole("link", { name: "← Voltar" }));
  await screen.findByRole("heading", { name: "Lista de produtos" });
  expect(screen.queryByText("Sair sem salvar?")).toBeNull();
});

it("does not offer discard or submit twice while a save is pending", async () => {
  await openEditor();
  let resolveSave!: (value: any) => void;
  vi.mocked(resources.save).mockImplementation(() => new Promise(resolve => { resolveSave = resolve; }));
  const form = (screen.getByLabelText("Nome") as HTMLInputElement).form!;
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Editado" } });
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(resources.save).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("link", { name: "← Voltar" }));
  await screen.findByRole("heading", { name: "Operação em andamento" });
  expect(screen.queryByRole("button", { name: "Descartar e sair" })).toBeNull();
  await act(async () => { resolveSave({ id: 1, detail: "Salvo." }); });
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Operação em andamento" })).toBeNull());
});

// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TransitionDialog } from "./TransitionDialog";

afterEach(cleanup);
beforeAll(() => { HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); }; });
const settings = { default_delivery_minutes: 40, default_pickup_minutes: 20, default_prep_minutes: 30, allow_skip_notification: true };
const order = { id: 17, customer_name: "Ana", customer_phone: "5511999999999", delivery_type: "delivery", delivery_label: "Entrega", allowed_transitions: [{ value: "out_for_delivery", label: "Saiu para entrega", message: "Seu pedido saiu.", notification_enabled: true }] };
function setup(extra: Record<string, any> = {}) {
  const onConfirm = vi.fn();
  render(<TransitionDialog order={order} status="out_for_delivery" settings={settings} busy={false} onConfirm={onConfirm} onClose={() => {}} {...extra} />);
  return onConfirm;
}
describe("Confirmação operacional", () => {
  it("delega o prazo padrão e mensagem padrão ao backend", () => {
    const confirm = setup();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar alteração" }));
    expect(confirm).toHaveBeenCalledWith({ message: undefined, complement: "", send_notification: true });
  });
  it("envia prazo manual, mensagem editada e complemento", () => {
    const confirm = setup();
    fireEvent.click(screen.getByLabelText("Informar prazo manual"));
    fireEvent.change(screen.getByLabelText("Prazo de entrega (minutos)"), { target: { value: "55" } });
    fireEvent.change(screen.getByLabelText("Mensagem"), { target: { value: "O entregador está a caminho." } });
    fireEvent.change(screen.getByLabelText("Complemento opcional"), { target: { value: "Pela entrada lateral." } });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar alteração" }));
    expect(confirm).toHaveBeenCalledWith({ fulfillment_minutes: 55, message: "O entregador está a caminho.", complement: "Pela entrada lateral.", send_notification: true });
  });
  it("registra opção de não avisar sem modificar o status escolhido", () => {
    const confirm = setup();
    fireEvent.click(screen.getByLabelText("Avisar cliente pelo WhatsApp"));
    expect(screen.queryByLabelText("Mensagem")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar alteração" }));
    expect(confirm.mock.calls[0][0].send_notification).toBe(false);
  });
  it("respeita configuração que exige aviso", () => {
    setup({ settings: { ...settings, allow_skip_notification: false } });
    expect(screen.queryByLabelText("Avisar cliente pelo WhatsApp")).toBeNull();
    expect(screen.getByLabelText("Mensagem")).toBeTruthy();
  });
  it("não permite novo envio enquanto salva e exibe erro sem descartar edição", () => {
    setup({ busy: true, error: new Error("Status alterado por outro operador.") });
    expect((screen.getByRole("button", { name: "Salvando…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("outro operador");
  });
});

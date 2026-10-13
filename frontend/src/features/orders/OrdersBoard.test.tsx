// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { OrdersBoard } from "./OrdersBoard";
const pendingCancel = {id:22,source:'ifood',channel:'ifood',cancellation_pending:true,cancellation_requested_at:new Date().toISOString(),customer_name:'Cliente cancelamento',created_at:new Date().toISOString(),delivery_type:'delivery',delivery_label:'Entrega',payment:{label:'Pago no marketplace'},payment_label:'Pagamento iFood',status:'confirmed',status_label:'Confirmado',items:[],allowed_transitions:[],total:'10'};
const card = { id: 2, customer_name: "Cliente da retirada", created_at: new Date().toISOString(), delivery_type: "pickup", delivery_label: "Retirada", payment: { label: "Pix confirmado" }, status: "ready_for_pickup", status_label: "Pronto para retirada", items: [{ id: 1, name: "Pizza", quantity: 1, notes: "Sem cebola", combination_details: { customizations: [{ option_name: "Borda" }] } }], allowed_transitions: [{ value: "delivered", label: "Entregue" }], total: "30" };
vi.mock("../../hooks/useQuery", () => ({ useQuery: () => ({ data: { columns: [{ status: "ready_for_pickup", label: "Pronto para retirada", orders: [card] }, {status:'awaiting_cancellation',label:'Aguardando cancelamento',orders:[pendingCancel]}], finished: [{ id: 99, customer_name: "Finalizado", status_label: "Entregue", total: "10" }], notification_settings: { default_prep_minutes: 30 } }, reload: vi.fn(), loading: false, error: null }) }));
beforeAll(() => { vi.stubGlobal("WebSocket", class { close() {} }); });
afterEach(cleanup);
describe("Operação rápida", () => {
  it("oculta histórico e mostra observações e adicionais nos cartões", () => {
    render(<MemoryRouter><OrdersBoard activeOnly /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Pedidos ativos" })).toBeTruthy();
    expect(screen.queryByText(/Pedidos finalizados recentemente/)).toBeNull();
    expect(screen.getByText("Obs.: Sem cebola")).toBeTruthy();
    expect(screen.getByText("Borda")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Marcar entregue" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Saiu para entrega" })).toBeNull();
  });
  it("exibe coluna de cancelamento sem perder a etapa definitiva do pedido", () => {
    const {container} = render(<MemoryRouter><OrdersBoard activeOnly /></MemoryRouter>);
    const lane = container.querySelector('.status-awaiting_cancellation');
    expect(lane?.textContent).toContain('Aguardando cancelamento');
    expect(lane?.textContent).toContain('#22');
    expect(lane?.textContent).toContain('iFood');
  });
  it("preserva histórico na rota anterior", () => {
    render(<MemoryRouter><OrdersBoard /></MemoryRouter>);
    expect(screen.getByText("Pedidos finalizados recentemente (1)")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Pedidos e histórico" })).toBeTruthy();
  });
});

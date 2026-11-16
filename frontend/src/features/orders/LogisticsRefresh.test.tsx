// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Logistics } from "./Logistics";
import { request } from "../../api/client";

const query = vi.hoisted(() => ({ data: null as any, loading: false, reload: vi.fn() }));
vi.mock("../../hooks/useQuery", () => ({ useQuery: () => query }));
vi.mock("./OrdersBoard", () => ({ useOrderRealtime: () => "online" }));
vi.mock("../../api/client", () => ({ request: vi.fn() }));

beforeEach(() => {
  query.loading = false;
  query.data = {
    couriers: [{ id: 1, name: "Ana", active: true }, { id: 2, name: "Beto", active: true }],
    orders: [{ id: 10, courier_id: 1, status: "out_for_delivery", customer_name: "Cliente" }],
    marketplace_orders: [], history: [], integrations: [],
  };
  vi.mocked(request).mockResolvedValue({ detail: "OK" });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("uses the refreshed assignment when the same order changes remotely", async () => {
  const view = render(<MemoryRouter><Logistics /></MemoryRouter>);
  expect((screen.getByLabelText("Entregador") as HTMLSelectElement).value).toBe("1");
  fireEvent.change(screen.getByLabelText("Quem recebeu"), { target: { value: "Maria" } });
  query.data = { ...query.data, orders: [{ ...query.data.orders[0], courier_id: 2 }] };
  view.rerender(<MemoryRouter><Logistics /></MemoryRouter>);
  expect((screen.getByLabelText("Entregador") as HTMLSelectElement).value).toBe("2");
  expect((screen.getByLabelText("Quem recebeu") as HTMLInputElement).value).toBe("Maria");
  fireEvent.click(screen.getByRole("button", { name: "Atribuir entregador" }));
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  const options = vi.mocked(request).mock.calls[0][1];
  expect(JSON.parse(String(options?.body))).toEqual({ action: "assign", order: 10, courier: 2 });
});

it("preserves an unsent selection across refreshes with unchanged assignment", () => {
  const view = render(<MemoryRouter><Logistics /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Entregador"), { target: { value: "2" } });
  query.loading = true;
  view.rerender(<MemoryRouter><Logistics /></MemoryRouter>);
  query.loading = false;
  query.data = { ...query.data, orders: [{ ...query.data.orders[0] }] };
  view.rerender(<MemoryRouter><Logistics /></MemoryRouter>);
  expect((screen.getByLabelText("Entregador") as HTMLSelectElement).value).toBe("2");
  expect(request).not.toHaveBeenCalled();
});

it("clears the selection if the server removes the assignment", () => {
  const view = render(<MemoryRouter><Logistics /></MemoryRouter>);
  query.data = { ...query.data, orders: [{ ...query.data.orders[0], courier_id: null }] };
  view.rerender(<MemoryRouter><Logistics /></MemoryRouter>);
  expect((screen.getByLabelText("Entregador") as HTMLSelectElement).value).toBe("");
});

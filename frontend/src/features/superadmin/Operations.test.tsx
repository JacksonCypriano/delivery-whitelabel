// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Credit, Prospecting, Evolution } from "./Operations";
import { FreeDays } from "./FreeDays";
import { FieldInput } from "../../components/Fields";
import { request, post } from "../../api/client";
vi.mock("../../api/client", () => ({
  request: vi.fn(),
  post: vi.fn(),
  formData: (data: any) => {
    const f = new FormData();
    Object.entries(data).forEach(([k, v]) => f.append(k, String(v)));
    return f;
  },
}));
HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const field = {
  name: "upload",
  html_name: "upload",
  label: "Arquivo",
  kind: "file",
  required: true,
  disabled: false,
  help: "",
  choices: [],
  errors: [],
  split: false,
  value: null,
};
describe("Operações globais", () => {
  it("respeita formatos de upload do backend", () => {
    render(<FieldInput field={{ ...field, accept: ".csv" }} />);
    expect(screen.getByLabelText("Arquivo *").getAttribute("accept")).toBe(
      ".csv",
    );
  });
  it("exibe prévia antes de conceder meses", async () => {
    vi.mocked(request).mockResolvedValue({
      tenant: "Loja",
      status: "Ativa",
      valid_until: "2026-12-01",
      fields: [],
    });
    vi.mocked(post)
      .mockResolvedValueOnce({
        preview: "signed",
        months: 2,
        previous: "2026-12-01",
        until: "2027-02-01",
        reason: "Cortesia",
      })
      .mockResolvedValueOnce({
        detail: "Meses registrados",
        valid_until: "2027-02-01",
      });
    render(
      <MemoryRouter>
        <Credit />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("Conferir resultado"));
    expect(await screen.findByText(/2026-12-01 → 2027-02-01/)).toBeTruthy();
    expect(post).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await screen.findByText(/Meses registrados/);
    expect(vi.mocked(post).mock.calls[1][1].get("preview")).toBe("signed");
  });
  it("confirma dias livres com período e impacto antes de executar", async () => {
    vi.mocked(request).mockResolvedValue({
      tenant: "Loja",
      status: "Ativa",
      active: true,
      fields: [],
      history: [],
      impact: { billing: "Cobranças preservadas", access: "Acesso liberado" },
      total_days: 0,
      page: 1,
      pages: 1,
    });
    vi.mocked(post)
      .mockResolvedValueOnce({
        preview: "signed-days",
        days: 730,
        start: "2026-10-26",
        end: "2028-10-25",
        reason: "Cortesia",
        impact: { billing: "Cobranças preservadas", access: "Acesso liberado" },
      })
      .mockResolvedValueOnce({
        detail: "Dias registrados",
        grant: {
          start: "2026-10-26",
          end: "2028-10-25",
          access_after: { active: true },
        },
      });
    render(
      <MemoryRouter>
        <FreeDays />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("Conferir período"));
    await screen.findByText(/730 dias: 2026-10-26/);
    expect(post).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await screen.findByText(/Dias registrados/);
    expect(vi.mocked(post).mock.calls[1][1].get("preview")).toBe("signed-days");
  });
  it("confirma início da campanha e mantém os dados enviados", async () => {
    vi.mocked(request).mockResolvedValue({
      enabled: false,
      pending_count: 3,
      sent_count: 2,
      queue_name: "prospecting",
      timezone: "America/Sao_Paulo",
      start_time: "09:00",
      end_time: "18:00",
      messages_per_minute: 1,
      weekdays: [0],
      batches: [],
    });
    vi.mocked(post)
      .mockResolvedValueOnce({
        confirmation_required: true,
        objects: ["Iniciar envios"],
      })
      .mockResolvedValueOnce({ messages: [] });
    render(
      <MemoryRouter>
        <Prospecting />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("Iniciar campanha"));
    await screen.findByText(/Iniciar envios/);
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(vi.mocked(post).mock.calls[1][1].get("confirmed")).toBe("yes");
  });
  it("oculta pareamento quando não permitido", async () => {
    vi.mocked(request).mockResolvedValue({
      connection: {
        instance: "plataforma",
        environment: "sandbox",
        status: "open",
        attempts: 0,
      },
      pair_allowed: false,
      events: [],
      alerts: [],
    });
    render(
      <MemoryRouter>
        <Evolution />
      </MemoryRouter>,
    );
    expect(
      ((await screen.findByText("Exibir QR Code")) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    vi.mocked(post).mockResolvedValue({ messages: [] });
    fireEvent.click(screen.getByText("Consultar conexão"));
    await waitFor(() => expect(post).toHaveBeenCalled());
  });
});

import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ManifestEntry } from "../../api/types";
import {
  CATALOG,
  apiError,
  mockApi,
  pickMonth,
  renderPage,
} from "../../test/utils";
import { StatusPage, formatDateTime, type SyncStatus } from "./StatusPage";

// Generous async timeouts: the full suite runs many jsdom files in parallel.
configure({ asyncUtilTimeout: 10000 });
vi.setConfig({ testTimeout: 20000 });

function entry(
  over: Partial<ManifestEntry>,
): ManifestEntry & { label: string } {
  return {
    path: "faturas/a.pdf",
    sha256: "sha",
    kind: "fatura",
    format: "pdf",
    profile_id: "inter",
    card_id: "card_x",
    account_id: null,
    invoice_month: "2026-10",
    total: "150.00",
    amount_due: null,
    open_invoice: false,
    status: "confirmed",
    label: "confirmado",
    error: null,
    warnings: [],
    supersedes_candidate: null,
    superseded_by: null,
    duplicate_of: null,
    paid_by_fingerprints: [],
    ...over,
  };
}

const STATUS: SyncStatus = {
  last_scan: "2026-10-12T10:00:00",
  last_report: { new: ["faturas/b.pdf"], changed: [], errors: [] },
  files: [
    entry({}),
    entry({
      path: "faturas/b.pdf",
      status: "awaiting_card",
      label: "aguardando cartão",
      card_id: null,
      invoice_month: null,
      warnings: ["unknown_card_hint:9999"],
    }),
    entry({
      path: "extratos/c.pdf",
      kind: "extrato",
      status: "awaiting_card",
      label: "aguardando cartão",
      card_id: null,
    }),
    entry({
      path: "faturas/d.pdf",
      status: "error",
      label: "erro",
      error: "senha incorreta",
    }),
  ],
  jobs: [
    {
      id: "j1",
      kind: "scan",
      status: "error",
      created_at: "2026-10-12T10:00:00",
      finished_at: null,
      result: null,
      error: "boom",
    },
  ],
};

const routes = (extra: Record<string, unknown> = {}) => ({
  ...CATALOG,
  "GET /api/sync/status": STATUS,
  "POST /api/sync/scan": { id: "j2", status: "queued" },
  "POST /api/sync/reprocess": { id: "j3", status: "done" },
  "POST /api/sync/choose-owner": { id: "j4", status: "done" },
  ...extra,
});

describe("StatusPage", () => {
  it("r3_10 lists files with status labels, errors, warnings and jobs", async () => {
    mockApi(routes());
    renderPage(<StatusPage />, "/status");
    expect(await screen.findByText("faturas/a.pdf")).toBeInTheDocument();
    expect(screen.getByText("confirmado")).toBeInTheDocument();
    expect(screen.getAllByText("aguardando cartão")).toHaveLength(2);
    expect(screen.getByText("senha incorreta")).toBeInTheDocument();
    expect(
      screen.getByText("Cartão final 9999 não cadastrado"),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 novos/)).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    mockApi(
      routes({
        "GET /api/sync/status": {
          files: [],
          last_scan: null,
          last_report: null,
          jobs: [],
        },
      }),
    );
    renderPage(<StatusPage />, "/status");
    expect(
      await screen.findByText("Nenhum arquivo na pasta de entrada."),
    ).toBeInTheDocument();
    expect(screen.getByText("nunca")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma tarefa recente.")).toBeInTheDocument();
  });

  it("shows the load error", async () => {
    mockApi(
      routes({
        "GET /api/sync/status": () => apiError(500, "x", "fora do ar"),
      }),
    );
    renderPage(<StatusPage />, "/status");
    expect(await screen.findByRole("alert")).toHaveTextContent("fora do ar");
  });

  it("scans now and reprocesses a file; reports errors", async () => {
    const { calls } = mockApi(
      routes({
        "POST /api/sync/scan": () =>
          apiError(409, "sync_unavailable", "sync service not running"),
      }),
    );
    const user = userEvent.setup();
    renderPage(<StatusPage />, "/status");
    await user.click(
      await screen.findByRole("button", { name: "Varrer agora" }),
    );
    expect(await screen.findByText("sync service not running")).toBeVisible();
    expect(
      calls.some((c) => c.method === "POST" && c.path === "/api/sync/scan"),
    ).toBe(true);
    await user.click(
      screen.getByRole("button", { name: "Reprocessar faturas/d.pdf" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/sync/reprocess")?.body).toEqual(
        {
          path: "faturas/d.pdf",
        },
      ),
    );
    expect(
      await screen.findByText("Reprocessado: faturas/d.pdf"),
    ).toBeVisible();
  });

  it("r4_8 chooses the card (with month) for an invoice awaiting card", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<StatusPage />, "/status");
    await user.click(
      await screen.findByRole("button", {
        name: "Escolher cartão para faturas/b.pdf",
      }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Escolher cartão",
    });
    await user.click(within(dialog).getByRole("button", { name: "Definir" }));
    expect(await within(dialog).findByText("Escolha o cartão")).toBeVisible();
    await user.click(within(dialog).getByRole("textbox", { name: /Cartão/ }));
    await user.click(await screen.findByRole("option", { name: "Cartão X" }));
    await pickMonth(
      user,
      within(dialog).getByLabelText("Mês da fatura (opcional)"),
      "2026-09",
    );
    await user.click(within(dialog).getByRole("button", { name: "Definir" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/sync/choose-owner")?.body,
      ).toEqual({
        path: "faturas/b.pdf",
        card_id: "card_x",
        invoice_month: "2026-09",
      }),
    );
  });

  it("r4_8 chooses the account for a statement awaiting owner", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<StatusPage />, "/status");
    await user.click(
      await screen.findByRole("button", {
        name: "Escolher conta para extratos/c.pdf",
      }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Escolher conta",
    });
    await user.click(within(dialog).getByRole("textbox", { name: /Conta/ }));
    await user.click(await screen.findByRole("option", { name: "Conta X" }));
    await user.click(within(dialog).getByRole("button", { name: "Definir" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/sync/choose-owner")?.body,
      ).toEqual({
        path: "extratos/c.pdf",
        account_id: "acc_x",
      }),
    );
  });

  it("formats date-times", () => {
    expect(formatDateTime(null)).toBe("nunca");
    expect(formatDateTime("garbage")).toBe("garbage");
  });
});

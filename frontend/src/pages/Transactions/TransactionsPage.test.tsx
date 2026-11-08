import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type {
  InstallmentPlan,
  RecurringPurchase,
  Transaction,
} from "../../api/types";
import {
  CATALOG,
  apiError,
  mockApi,
  pickDate,
  renderPage,
} from "../../test/utils";
import { nextDate } from "./RecurringTab";
import { TransactionsPage } from "./TransactionsPage";
import { transactionsQuery } from "./EntriesTab";

// Generous async timeouts: the full suite runs many jsdom files in parallel.
configure({ asyncUtilTimeout: 10000 });
vi.setConfig({ testTimeout: 20000 });

function tx(over: Partial<Transaction>): Transaction {
  return {
    id: "tx1",
    fingerprint: "fp1",
    kind: "expense",
    source: { type: "import", sha256: "s", path: "faturas/a.pdf", line: 1 },
    provisional: false,
    payment_method: "credit",
    card_id: "card_x",
    account_id: null,
    purchase_date: "2026-10-01",
    invoice_month: "2026-10",
    description: "Mercado",
    amount: "100.00",
    category_id: "cat_casa",
    installment: null,
    links: {},
    allocations: null,
    allocation_origin: null,
    note: null,
    tag: null,
    review: null,
    ...over,
  };
}

const TXS = [
  tx({}),
  tx({
    id: "tx2",
    description: "Padaria",
    source: { type: "manual", sha256: null, path: null, line: null },
    provisional: true,
    category_id: null,
    amount: "12.50",
  }),
];

function plan(over: Partial<InstallmentPlan>): InstallmentPlan {
  return {
    id: "plan1",
    origin: { type: "import", fingerprint: "fp" },
    card_id: "card_x",
    description: "TV",
    total_installments: 10,
    first_invoice_month: "2026-08",
    total_amount: "1000.00",
    installment_amount: "100.00",
    category_id: "cat_casa",
    allocations: null,
    status_override: null,
    anticipation: null,
    warnings: [],
    ...over,
  };
}

function rec(over: Partial<RecurringPurchase>): RecurringPurchase {
  return {
    id: "rec1",
    description: "Ração",
    match_description: null,
    estimated_amount: "180.00",
    every: { value: 45, unit: "days" },
    last_date: "2026-09-01",
    payment_method: "credit",
    card_id: "card_x",
    account_id: null,
    category_id: "cat_casa",
    allocations: null,
    active: true,
    skipped_dates: [],
    next_date: null,
    ...over,
  };
}

describe("TransactionsPage — entries", () => {
  it("lists the selected month with badges and filters", async () => {
    const { calls } = mockApi({ ...CATALOG, "GET /api/transactions": TXS });
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos");
    expect(await screen.findByText("Mercado")).toBeInTheDocument();
    expect(screen.getByText("importado")).toBeInTheDocument();
    expect(screen.getByText("previsto")).toBeInTheDocument();
    expect(screen.getByText("sem categoria")).toBeInTheDocument();
    expect(screen.getByText("R$ 12,50", { exact: false })).toBeInTheDocument();
    expect(
      calls.some((c) => c.path === "/api/transactions?month=2026-10"),
    ).toBe(true);
    await user.click(screen.getByRole("switch", { name: "Só previstos" }));
    await user.type(screen.getByRole("textbox", { name: "Buscar" }), "pad");
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path === "/api/transactions?month=2026-10&q=pad&provisional=true",
        ),
      ).toBe(true),
    );
  });

  it("shows the empty and error states", async () => {
    mockApi({ ...CATALOG, "GET /api/transactions": [] });
    renderPage(<TransactionsPage />, "/lancamentos");
    expect(
      await screen.findByText("Nenhum lançamento com esses filtros."),
    ).toBeInTheDocument();
  });

  it("shows the API error", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/transactions": () => apiError(500, "boom", "falhou"),
    });
    renderPage(<TransactionsPage />, "/lancamentos");
    expect(await screen.findByRole("alert")).toHaveTextContent("falhou");
  });

  it("r1_12 recategorizes in batch, uncategorized ignores the month", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions": TXS,
      "POST /api/transactions/recategorize": { updated: 2 },
    });
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?uncategorized=1");
    expect(await screen.findByText("Mercado")).toBeInTheDocument();
    expect(
      calls.some((c) => c.path === "/api/transactions?uncategorized=true"),
    ).toBe(true);
    expect(screen.getByRole("switch", { name: "Sem categoria" })).toBeChecked();
    await user.click(
      screen.getByRole("checkbox", { name: "Selecionar todos" }),
    );
    await user.click(screen.getByRole("textbox", { name: /Nova categoria/ }));
    await user.click(await screen.findByRole("option", { name: "Lazer" }));
    await user.click(screen.getByRole("button", { name: "Recategorizar (2)" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/transactions/recategorize")?.body,
      ).toEqual({ ids: ["tx1", "tx2"], category_id: "cat_lazer" }),
    );
    expect(
      await screen.findByText(/2 item\(ns\) recategorizado/),
    ).toBeVisible();
    await user.click(screen.getByRole("switch", { name: "Sem categoria" }));
    await waitFor(() =>
      expect(
        calls.some((c) => c.path === "/api/transactions?month=2026-10"),
      ).toBe(true),
    );
  });

  it("edits an imported line (classification only) and a manual one", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions": TXS,
      "PATCH /api/transactions/tx1": TXS[0],
      "PATCH /api/transactions/tx2": TXS[1],
    });
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos");
    await user.click(
      await screen.findByRole("button", { name: "Editar Mercado" }),
    );
    let dialog = await screen.findByRole("dialog", {
      name: "Editar lançamento",
    });
    expect(
      within(dialog).queryByRole("textbox", { name: "Descrição" }),
    ).not.toBeInTheDocument();
    await user.type(
      within(dialog).getByRole("textbox", { name: "Nota" }),
      "ok",
    );
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        category_id: "cat_casa",
        allocations: null,
        note: "ok",
        kind: "expense",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Editar Padaria" }));
    dialog = await screen.findByRole("dialog", { name: "Editar lançamento" });
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(
      await within(dialog).findByText("Categoria é obrigatória"),
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("textbox", { name: /Categoria/ }),
    );
    await user.click(await screen.findByRole("option", { name: "Lazer" }));
    const amount = within(dialog).getByRole("textbox", { name: "Valor" });
    await user.clear(amount);
    await user.type(amount, "13,00");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/transactions/tx2")?.body,
      ).toEqual({
        category_id: "cat_lazer",
        allocations: null,
        note: null,
        kind: "expense",
        description: "Padaria",
        amount: "13.00",
        purchase_date: "2026-10-01",
      }),
    );
  });

  it("r14_23 a manual entry can move from the card to PIX on an account", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions": TXS,
      "PATCH /api/transactions/tx2": TXS[1],
    });
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos");
    await user.click(
      await screen.findByRole("button", { name: "Editar Padaria" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Editar lançamento",
    });
    await user.click(
      within(dialog).getByRole("textbox", { name: /Categoria/ }),
    );
    await user.click(await screen.findByRole("option", { name: "Lazer" }));
    await user.selectOptions(
      within(dialog).getByLabelText("Meio de pagamento"),
      "pix",
    );
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(
      await within(dialog).findByText("Escolha a conta"),
    ).toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText(/^Conta/), "acc_x");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/transactions/tx2")?.body,
      ).toMatchObject({
        payment_method: "pix",
        card_id: null,
        account_id: "acc_x",
      }),
    );
  });

  it("deletes only manual entries", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions": TXS,
      "DELETE /api/transactions/tx2": { deleted: "tx2" },
    });
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos");
    await screen.findByText("Mercado");
    expect(
      screen.queryByRole("button", { name: "Excluir Mercado" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Excluir Padaria" }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "DELETE" && c.path === "/api/transactions/tx2",
        ),
      ).toBe(true),
    );
  });

  it("builds the query string", () => {
    expect(
      transactionsQuery("2026-10", false, {
        card_id: "c",
        account_id: "a",
        payment_method: "pix",
        q: " x ",
        provisional: false,
      }),
    ).toBe("month=2026-10&card_id=c&account_id=a&payment_method=pix&q=x");
  });
});

describe("TransactionsPage — plans", () => {
  const routes = (plans: InstallmentPlan[]) => ({
    ...CATALOG,
    "GET /api/installment-plans": plans,
    "GET /api/installment-plans-status": {
      plan1: "em andamento",
      plan2: "terminando",
    },
    "POST /api/installment-plans/plan1/anticipate": plans[0],
    "POST /api/installment-plans/plan1/cancel": plans[0],
    "POST /api/installment-plans/plan1/anticipated-at-bank": plans[0],
    "DELETE /api/installment-plans/plan2/anticipation": plans[1],
  });

  it("r1_3 shows status and warnings; empty state", async () => {
    mockApi(
      routes([
        plan({ warnings: ["origem removida"] }),
        plan({ id: "plan2", description: "Sofá" }),
      ]),
    );
    renderPage(<TransactionsPage />, "/lancamentos?tab=parcelamentos");
    expect(await screen.findByText("TV")).toBeInTheDocument();
    expect(await screen.findByText("em andamento")).toBeInTheDocument();
    expect(screen.getByText("terminando")).toBeInTheDocument();
    expect(screen.getByText("origem removida")).toBeInTheDocument();
  });

  it("shows empty plans", async () => {
    mockApi(routes([]));
    renderPage(<TransactionsPage />, "/lancamentos?tab=parcelamentos");
    expect(await screen.findByText("Nenhum parcelamento.")).toBeInTheDocument();
  });

  it("r7_1 anticipates with optional fields", async () => {
    const { calls } = mockApi(routes([plan({})]));
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?tab=parcelamentos");
    await user.click(
      await screen.findByRole("button", { name: "Antecipar TV" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Antecipar parcelamento",
    });
    await user.type(
      within(dialog).getByRole("textbox", {
        name: "Parcela inicial (opcional)",
      }),
      "11",
    );
    await user.click(within(dialog).getByRole("button", { name: "Confirmar" }));
    expect(
      await within(dialog).findByText("Parcela entre 1 e 10"),
    ).toBeVisible();
    const n = within(dialog).getByRole("textbox", {
      name: "Parcela inicial (opcional)",
    });
    await user.clear(n);
    await user.type(n, "4");
    await user.type(
      within(dialog).getByRole("textbox", { name: /Valor cobrado/ }),
      "550,00",
    );
    await user.click(within(dialog).getByRole("button", { name: "Confirmar" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/installment-plans/plan1/anticipate")
          ?.body,
      ).toEqual({ from_n: 4, amount: "550.00" }),
    );
  });

  it("cancels from n and marks anticipated at bank", async () => {
    const { calls } = mockApi(routes([plan({})]));
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?tab=parcelamentos");
    await user.click(
      await (async () => {
        await user.click(
          await screen.findByRole("button", { name: "Mais ações de TV" }),
        );
        return screen.findByRole("menuitem", { name: "Cancelar TV" });
      })(),
    );
    let dialog = await screen.findByRole("dialog", {
      name: "Cancelar parcelamento",
    });
    await user.click(within(dialog).getByRole("button", { name: "Confirmar" }));
    expect(await within(dialog).findByText("Informe a parcela")).toBeVisible();
    await user.type(
      within(dialog).getByRole("textbox", { name: "A partir da parcela" }),
      "5",
    );
    await user.click(within(dialog).getByRole("button", { name: "Confirmar" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/installment-plans/plan1/cancel")
          ?.body,
      ).toEqual({ from_n: 5 }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    await user.click(
      await (async () => {
        await user.click(
          screen.getByRole("button", { name: "Mais ações de TV" }),
        );
        return screen.findByRole("menuitem", {
          name: "Antecipada no banco: TV",
        });
      })(),
    );
    dialog = await screen.findByRole("dialog", { name: "Antecipada no banco" });
    await user.type(
      within(dialog).getByRole("textbox", { name: "A partir da parcela" }),
      "3",
    );
    await user.click(within(dialog).getByRole("button", { name: "Confirmar" }));
    await waitFor(() =>
      expect(
        calls.find(
          (c) => c.path === "/api/installment-plans/plan1/anticipated-at-bank",
        )?.body,
      ).toEqual({ from_n: 3 }),
    );
  });

  it("undoes an anticipation unless lines are already linked", async () => {
    const anticipation = {
      from_n: 4,
      target_month: "2026-11",
      amount: "500.00",
      linked_fingerprints: [],
    };
    const { calls } = mockApi(
      routes([
        plan({
          anticipation: { ...anticipation, linked_fingerprints: ["fp9"] },
        }),
        plan({ id: "plan2", description: "Sofá", anticipation }),
      ]),
    );
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?tab=parcelamentos");
    expect(
      await screen.findByRole("button", { name: "Desfazer antecipação de TV" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Desfazer antecipação de Sofá" }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.method === "DELETE" &&
            c.path === "/api/installment-plans/plan2/anticipation",
        ),
      ).toBe(true),
    );
  });
});

describe("TransactionsPage — recurring", () => {
  const routes = (recs: RecurringPurchase[]) => ({
    ...CATALOG,
    "GET /api/recurring-purchases": recs,
    "POST /api/recurring-purchases/rec1/action": recs[0],
  });

  it("computes the next expected date", () => {
    expect(nextDate(rec({}))).toBe("2026-10-16");
    expect(nextDate(rec({ next_date: "2026-11-02" }))).toBe("2026-11-02");
    expect(
      nextDate(
        rec({ last_date: "2026-01-31", every: { value: 1, unit: "months" } }),
      ),
    ).toBe("2026-02-28");
    expect(
      nextDate(
        rec({ last_date: "2026-01-01", every: { value: 2, unit: "weeks" } }),
      ),
    ).toBe("2026-01-15");
  });

  it("r12_4 postpones, skips and ends a recurring purchase", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = mockApi(routes([rec({})]));
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?tab=recorrentes");
    expect(await screen.findByText("16/10/2026")).toBeInTheDocument();
    const actions = () =>
      calls.filter((c) => c.path === "/api/recurring-purchases/rec1/action");

    await user.click(
      screen.getByRole("button", { name: "Pular Ração de 16/10/2026" }),
    );
    await waitFor(() =>
      expect(actions()[0]?.body).toEqual({
        action: "skip",
        date: "2026-10-16",
      }),
    );

    await user.click(screen.getByRole("button", { name: "Adiar Ração" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Adiar gasto recorrente",
    });
    const input = within(dialog).getByLabelText(/Nova data prevista/);
    await pickDate(user, input, "2026-10-25");
    await user.click(within(dialog).getByRole("button", { name: "Adiar" }));
    await waitFor(() =>
      expect(actions()[1]?.body).toEqual({
        action: "postpone",
        date: "2026-10-25",
      }),
    );

    // R14.10: "Desativar" (reversible), no confirmation needed
    await user.click(screen.getByRole("button", { name: "Desativar Ração" }));
    await waitFor(() => expect(actions()[2]?.body).toEqual({ action: "end" }));
  });

  it("r14_10 an inactive purchase only offers Ativar", async () => {
    const { calls } = mockApi(routes([rec({ active: false })]));
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?tab=recorrentes");
    expect(await screen.findByText("desativada")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adiar Ração" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Ativar Ração" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        action: "resume",
      }),
    );
  });

  it("r14_11 a purchase paused this month shows as desativada", async () => {
    mockApi(
      routes([rec({ pauses: [{ from_month: "2026-01", until_month: null }] })]),
    );
    renderPage(<TransactionsPage />, "/lancamentos?tab=recorrentes");
    expect(await screen.findByText("desativada")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ativar Ração" }),
    ).toBeInTheDocument();
  });

  it("switches tabs through the URL", async () => {
    mockApi({ ...routes([]), "GET /api/transactions": [] });
    const user = userEvent.setup();
    renderPage(<TransactionsPage />, "/lancamentos?tab=recorrentes");
    expect(
      await screen.findByText("Nenhum gasto recorrente."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Lançamentos" }));
    expect(
      await screen.findByText("Nenhum lançamento com esses filtros."),
    ).toBeInTheDocument();
  });
});

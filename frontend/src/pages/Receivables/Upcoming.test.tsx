import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ReceivableItem, Receivables, Settlement } from "../../api/types";
import { apiError, CATALOG, mockApi, renderPage } from "../../test/utils";
import { ReceivablesPage } from "./ReceivablesPage";
import { byDeadline, findSettlement } from "./Upcoming";

// R14.28: the page opens on next month's deadlines; these tests look at every open item
const showAll = async () =>
  userEvent.click(
    await screen.findByRole("radio", { name: "Todos em aberto" }),
  );

const EMPTY_BALANCES = { user_id: "eu", incomplete_months: [], people: [] };

function item(extra: Partial<ReceivableItem>): ReceivableItem {
  return {
    counterparty_user_id: "ana",
    direction: "receive",
    card_id: "card_x",
    account_id: null,
    invoice_month: "2026-10",
    due_date: "2026-10-10",
    amount: "100.00",
    overdue: false,
    settled_month_total: "0.00",
    settled: "0.00",
    remaining: extra.amount ?? "100.00",
    status: "open",
    ...extra,
  };
}

const REPORT: Receivables = {
  user_id: "eu",
  items: [
    item({ invoice_month: "2026-11", due_date: "2026-11-10", amount: "80.00" }),
    item({
      due_date: "2026-10-10",
      amount: "120.50",
      overdue: true,
      settled_month_total: "20.00",
    }),
    item({
      direction: "pay",
      card_id: null,
      account_id: "acc_x",
      due_date: null,
      amount: "45.00",
    }),
  ],
  totals: { receive: "200.50", pay: "45.00" },
};

describe("Próximos recebimentos", () => {
  it("r13_11 lists receivables by deadline, split into Receber and Pagar, with totals", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": REPORT,
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    const receive = await screen.findByRole("table", { name: "Receber" });
    const rows = within(receive).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    // Earliest deadline first, overdue flagged, card name resolved, invoice month formatted.
    expect(rows[0]).toHaveTextContent("10/10/2026");
    expect(within(rows[0] as HTMLElement).getByText("vencido")).toBeVisible();
    expect(rows[0]).toHaveTextContent("Ana");
    expect(rows[0]).toHaveTextContent("Cartão X");
    expect(rows[0]).toHaveTextContent("out/2026");
    expect(rows[0]).toHaveTextContent("R$ 120,50");
    expect(rows[0]).toHaveTextContent("já acertado no mês: R$ 20,00");
    expect(rows[1]).toHaveTextContent("10/11/2026");
    expect(within(rows[1] as HTMLElement).queryByText("vencido")).toBeNull();

    const pay = screen.getByRole("table", { name: "Pagar" });
    expect(pay).toHaveTextContent("Conta X");
    expect(pay).toHaveTextContent("—");
    expect(screen.getAllByText("R$ 200,50").length).toBeGreaterThan(0);
    // Total a pagar, the row, and Ana's per-person total (R14.28)
    expect(screen.getAllByText("R$ 45,00").length).toBe(3);
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/receivables?user_id=eu",
    );

    // The pending switch is forwarded.
    await userEvent.click(screen.getByLabelText("Incluir não confirmados"));
    await screen.findByRole("table", { name: "Receber" });
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/receivables?user_id=eu&include_pending=true",
    );
  });

  it("r13_11 shows an empty message, empty sides and API errors", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        user_id: "eu",
        items: [],
        totals: { receive: "0.00", pay: "0.00" },
      },
    });
    const { unmount } = renderPage(<ReceivablesPage />);
    // R14.28: on next month's deadlines it says how to see the rest
    expect(
      await screen.findByText(/Nada vence nesse período/),
    ).toBeInTheDocument();
    await showAll();
    expect(
      await screen.findByText("Nada pendente para receber ou pagar."),
    ).toBeInTheDocument();
    unmount();

    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        ...REPORT,
        items: [item({})],
      },
    });
    const second = renderPage(<ReceivablesPage />);
    await showAll();
    expect(await screen.findByText("Nada a pagar.")).toBeInTheDocument();
    second.unmount();

    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        ...REPORT,
        items: [item({ direction: "pay" })],
      },
    });
    const third = renderPage(<ReceivablesPage />);
    await showAll();
    expect(await screen.findByText("Nada a receber.")).toBeInTheDocument();
    third.unmount();

    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": () =>
        apiError(500, "boom", "Falhou recebimentos"),
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    expect(await screen.findByText("Falhou recebimentos")).toBeInTheDocument();
  });

  it("r13_11 sorts by due date (unknown last) then invoice month", () => {
    const a = item({ due_date: null, invoice_month: "2026-01" });
    const b = item({ due_date: "2026-12-01" });
    const c = item({ due_date: null, invoice_month: "2025-12" });
    const d = item({ due_date: "2026-01-05" });
    expect([a, b, c, d].sort(byDeadline)).toEqual([d, b, c, a]);
  });

  it("r13_16 marks a receivable as received and keeps the line visible with Desfazer", async () => {
    let marked = false;
    const routes = {
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": () => ({
        ...REPORT,
        items: [
          item({
            amount: "120.50",
            overdue: true,
            ...(marked
              ? { status: "received", settled: "120.50", remaining: "0.00" }
              : {}),
          }),
          item({ direction: "pay", card_id: null, account_id: "acc_x" }),
        ],
      }),
      "POST /api/reports/receivables/mark-received": (body: unknown) => {
        marked = true;
        return { id: "set_1", ...(body as object) };
      },
    };
    const { calls } = mockApi(routes);
    renderPage(<ReceivablesPage />);
    await showAll();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Marcar como recebido: Ana, Cartão X, out/2026",
      }),
    );
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/reports/receivables/mark-received")
          ?.body,
      ).toEqual({
        user_id: "eu",
        counterparty_user_id: "ana",
        direction: "receive",
        card_id: "card_x",
        account_id: null,
        invoice_month: "2026-10",
      }),
    );
    const receive = screen.getByRole("table", { name: "Receber" });
    const row = (await within(receive).findByText("recebido")).closest(
      "tr",
    ) as HTMLElement;
    expect(row).toHaveAttribute("data-status", "received");
    expect(row).toHaveClass("et-settle-flash");
    // Overdue no longer matters once received.
    expect(within(row).queryByText("vencido")).toBeNull();
    expect(
      within(row).getByRole("button", { name: /^Desfazer/ }),
    ).toBeInTheDocument();
    expect(
      within(row).queryByRole("button", { name: /Marcar como/ }),
    ).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Marcado como recebido.",
    );

    // Payables use "Marcar como pago" and send direction "pay" with the account.
    await userEvent.click(
      screen.getByRole("button", {
        name: "Marcar como pago: Ana, Conta X, out/2026",
      }),
    );
    await waitFor(() =>
      expect(
        calls.filter(
          (c) => c.path === "/api/reports/receivables/mark-received",
        )[1]?.body,
      ).toMatchObject({
        direction: "pay",
        card_id: null,
        account_id: "acc_x",
      }),
    );
    expect(screen.getByRole("status")).toHaveTextContent("Marcado como pago.");
  });

  it("r13_16 hides received lines unless 'Mostrar recebidos' and shows partial progress", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        ...REPORT,
        items: [
          item({
            invoice_month: "2026-09",
            status: "received",
            settled: "100.00",
            remaining: "0.00",
          }),
          item({
            amount: "120.50",
            settled: "50.00",
            remaining: "70.50",
            status: "partial",
          }),
          item({
            direction: "pay",
            status: "received",
            settled: "100.00",
            remaining: "0.00",
          }),
        ],
        totals: { receive: "70.50", pay: "0.00" },
      },
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    const receive = await screen.findByRole("table", { name: "Receber" });
    let rows = within(receive).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    const partial = rows[0] as HTMLElement;
    expect(partial).toHaveTextContent("R$ 70,50");
    expect(partial).toHaveTextContent("R$ 50,00 de R$ 120,50");
    expect(within(partial).getByText("parcial")).toBeInTheDocument();
    // A partial line can be completed or undone.
    expect(
      within(partial).getByRole("button", { name: /^Marcar como recebido/ }),
    ).toBeInTheDocument();
    expect(
      within(partial).getByRole("button", { name: /^Desfazer/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Tudo pago.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Pagar" })).toBeNull();

    const toggle = screen.getByRole("switch", { name: "Mostrar recebidos" });
    expect(toggle).not.toBeChecked();
    await userEvent.click(toggle);
    rows = within(screen.getByRole("table", { name: "Receber" }))
      .getAllByRole("row")
      .slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByText("recebido")).toBeVisible();
    const pay = screen.getByRole("table", { name: "Pagar" });
    expect(within(pay).getByText("pago")).toBeInTheDocument();
  });

  it("r13_16 'Desfazer' deletes the settlement with the same pair, card and month", async () => {
    const settlements: Partial<Settlement>[] = [
      // Same card/month but the other direction: must not be picked.
      {
        id: "set_wrong_dir",
        from_user_id: "eu",
        to_user_id: "ana",
        card_id: "card_x",
        account_id: null,
        invoice_month: "2026-10",
        date: "2026-10-12",
      },
      {
        id: "set_ok",
        from_user_id: "ana",
        to_user_id: "eu",
        card_id: "card_x",
        account_id: null,
        invoice_month: "2026-10",
        date: "2026-10-11",
      },
    ];
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        ...REPORT,
        items: [
          item({ status: "received", settled: "100.00", remaining: "0.00" }),
        ],
      },
      "GET /api/settlements": settlements,
      "DELETE /api/settlements/set_ok": () => undefined,
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    await userEvent.click(
      await screen.findByRole("switch", { name: "Mostrar recebidos" }),
    );
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Desfazer: Ana, Cartão X, out/2026",
      }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "DELETE" && c.path === "/api/settlements/set_ok",
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Marcação desfeita.",
      ),
    );
  });

  it("r13_16 shows readable errors when marking fails or the settlement is gone", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        ...REPORT,
        items: [
          item({}),
          item({
            invoice_month: "2026-09",
            status: "partial",
            settled: "10.00",
            remaining: "90.00",
          }),
        ],
      },
      "POST /api/reports/receivables/mark-received": () =>
        apiError(422, "nothing_to_settle", "Nada a acertar neste item"),
      "GET /api/settlements": [],
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Marcar como recebido: Ana, Cartão X, out/2026",
      }),
    );
    expect(
      await screen.findByText("Nada a acertar neste item"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Desfazer: Ana, Cartão X, set/2026" }),
    );
    expect(
      await screen.findByText(/Acerto deste recebimento não encontrado/),
    ).toBeInTheDocument();
  });

  it("r13_16 findSettlement matches account receivables and picks the newest", () => {
    const base = {
      origin: { type: "manual" as const, fingerprint: null },
      amount: "10.00",
      month: "2026-10",
      note: null,
      warnings: [],
      from_user_id: "eu",
      to_user_id: "ana",
      card_id: null,
      account_id: "acc_x",
      invoice_month: "2026-10",
    };
    const old: Settlement = { ...base, id: "old", date: "2026-10-01" };
    const neu: Settlement = { ...base, id: "new", date: "2026-10-05" };
    const other: Settlement = {
      ...base,
      id: "other",
      date: "2026-10-09",
      invoice_month: "2026-09",
    };
    const legacy: Settlement = {
      ...base,
      id: "legacy",
      date: "2026-10-10",
      card_id: undefined,
      account_id: undefined,
      invoice_month: undefined,
    };
    const it = item({
      direction: "pay",
      card_id: null,
      account_id: "acc_x",
    });
    expect(findSettlement([neu, other, old, legacy], "eu", it)?.id).toBe("new");
    expect(findSettlement([legacy], "eu", it)).toBeNull();
  });
});

describe("Previsto (R14.15)", () => {
  it("r14_15 lists forecast debts by month, apart from the confirmed totals", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        user_id: "eu",
        items: [],
        totals: { receive: "0.00", pay: "0.00" },
        forecast: {
          items: [
            {
              counterparty_user_id: "ana",
              direction: "receive",
              card_id: "card_x",
              account_id: null,
              invoice_month: "2026-11",
              due_date: "2026-11-10",
              amount: "20.00",
            },
            {
              counterparty_user_id: "ana",
              direction: "receive",
              card_id: "card_x",
              account_id: null,
              invoice_month: "2026-10",
              due_date: null,
              amount: "20.00",
            },
          ],
          totals: { receive: "40.00", pay: "0.00" },
        },
      } satisfies Receivables,
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    const table = await screen.findByRole("table", { name: "Previsto" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent),
    ).toEqual(["out/2026", "nov/2026"]);
    expect(within(rows[0]!).getByText("te deve")).toBeInTheDocument();
    expect(screen.getByText("Previsto a receber")).toBeInTheDocument();
    expect(screen.getByText("R$ 40,00")).toBeInTheDocument();
    // a forecast cannot be marked as received
    expect(
      within(table).queryByRole("button", { name: /Marcar/ }),
    ).not.toBeInTheDocument();
  });

  it("r14_15 hides the panel when there is nothing forecast", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": REPORT,
    });
    renderPage(<ReceivablesPage />);
    await showAll();
    await screen.findByRole("table", { name: "Receber" });
    expect(
      screen.queryByRole("table", { name: "Previsto" }),
    ).not.toBeInTheDocument();
  });
});

describe("A receber por pessoa e período (R14.28)", () => {
  it("r14_28 filters by person and by deadline month, with per-person totals", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        user_id: "eu",
        items: [
          item({
            due_date: "2026-11-10",
            invoice_month: "2026-11",
            amount: "80.00",
          }),
          item({ due_date: "2026-10-10", amount: "120.00" }),
        ],
        totals: { receive: "200.00", pay: "0.00" },
      } satisfies Receivables,
    });
    const user = userEvent.setup();
    renderPage(<ReceivablesPage />);
    // default: next month (today is 2026-10-12 in tests) -> only the 11-10 one
    const table = await screen.findByRole("table", { name: "Receber" });
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(1);
    expect(within(table).getByText("10/11/2026")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Este mês/ }));
    expect(
      await within(screen.getByRole("table", { name: "Receber" })).findByText(
        "10/10/2026",
      ),
    ).toBeInTheDocument();
    await showAll();
    const byPerson = screen.getByLabelText("Por pessoa");
    expect(within(byPerson).getByText("R$ 200,00")).toBeInTheDocument();
    await user.click(
      within(byPerson).getByRole("button", { name: "Ver só Ana" }),
    );
    expect(screen.queryByLabelText("Por pessoa")).not.toBeInTheDocument();
  });
});

describe("A receber: uma aba por pessoa (R14.28)", () => {
  it("r14_28 a person who only owes by subscription has a tab with her previsto", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/balances": EMPTY_BALANCES,
      "GET /api/reports/receivables": {
        user_id: "eu",
        items: [],
        totals: { receive: "0.00", pay: "0.00" },
        forecast: {
          items: [
            {
              counterparty_user_id: "ana",
              direction: "receive",
              card_id: "card_x",
              account_id: null,
              invoice_month: "2026-11",
              due_date: "2026-11-10",
              amount: "27.95",
            },
          ],
          totals: { receive: "27.95", pay: "0.00" },
        },
      } satisfies Receivables,
    });
    const user = userEvent.setup();
    renderPage(<ReceivablesPage />);
    const tabs = await screen.findByRole("tablist", { name: "Pessoa" });
    expect(within(tabs).getByRole("tab", { name: "Todas" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.click(await within(tabs).findByRole("tab", { name: "Ana" }));
    const summary = await screen.findByLabelText("Resumo de Ana");
    expect(summary).toHaveTextContent("R$ 0,00");
    expect(summary).toHaveTextContent("R$ 27,95");
    expect(screen.getByRole("table", { name: "Previsto" })).toHaveTextContent(
      "Ana",
    );
    await user.click(within(tabs).getByRole("tab", { name: "Todas" }));
    expect(screen.queryByLabelText("Resumo de Ana")).not.toBeInTheDocument();
  });
});

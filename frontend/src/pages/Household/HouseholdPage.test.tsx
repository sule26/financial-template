import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { HouseholdPage, type HouseholdBill } from "./HouseholdPage";

function bill(over: Partial<HouseholdBill>): HouseholdBill {
  return {
    source: "recurring",
    id: "rec_luz",
    description: "LUZ",
    category_id: "cat_casa",
    payment_method: "boleto",
    card_id: null,
    account_id: "acc_x",
    allocations: { split_id: "split_casal" },
    due_date: "2026-10-10",
    expected: "180.00",
    paid: "0.00",
    status: "atrasada",
    transaction_ids: [],
    ...over,
  };
}

const REPORT = {
  month: "2026-10",
  items: [
    bill({}),
    bill({
      id: "rec_agua",
      description: "AGUA",
      expected: "90.00",
      paid: "92.10",
      status: "paga",
    }),
  ],
  totals: { expected: "270.00", paid: "92.10" },
};

describe("Contas da casa (R14.26)", () => {
  it("r14_26 lists the month bills with due date, expected, paid and status", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/reports/household": REPORT,
    });
    renderPage(<HouseholdPage />, "/contas-da-casa");
    const table = await screen.findByRole("table", { name: "Contas da casa" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]!).getByText("atrasada")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("10/10/2026")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("paga")).toBeInTheDocument();
    // a paid bill has no "Registrar pagamento"
    expect(
      within(rows[1]!).queryByRole("button", { name: /Registrar/ }),
    ).not.toBeInTheDocument();
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/household?month=2026-10",
    );
  });

  it("r14_26 registering a payment posts a manual entry linked to the bill", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/reports/household": REPORT,
      "POST /api/transactions": { transaction: { id: "tx1" } },
    });
    const user = userEvent.setup();
    renderPage(<HouseholdPage />, "/contas-da-casa");
    await user.click(
      await screen.findByRole("button", { name: "Registrar pagamento de LUZ" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Registrar pagamento",
    });
    const value = within(dialog).getByRole("textbox", { name: "Valor pago" });
    await user.clear(value);
    await user.type(value, "0");
    await user.click(within(dialog).getByRole("button", { name: "Registrar" }));
    expect(
      await within(dialog).findByText("Valor inválido"),
    ).toBeInTheDocument();
    await user.clear(value);
    await user.type(value, "195,30");
    await user.click(within(dialog).getByRole("button", { name: "Registrar" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        purchase_date: "2026-10-10",
        amount: "195.30",
        description: "LUZ",
        category_id: "cat_casa",
        payment_method: "boleto",
        recurring_purchase_id: "rec_luz",
        recurring_month: "2026-10",
        account_id: "acc_x",
        allocations: { split_id: "split_casal" },
      }),
    );
  });

  it("r14_26 explains how to add a bill when there is none", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/household": {
        month: "2026-10",
        items: [],
        totals: { expected: "0.00", paid: "0.00" },
      },
    });
    renderPage(<HouseholdPage />, "/contas-da-casa");
    expect(
      await screen.findByText(/Nenhuma conta da casa neste mês/),
    ).toBeInTheDocument();
  });
});

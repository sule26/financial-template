import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CATALOG, mockApi, pickMonth, renderPage } from "../../test/utils";
import { CatalogPage } from "./CatalogPage";
import {
  allocationIn,
  checkAllocationHistory,
  describePrice,
  describeSplit,
} from "./schedule";
import type { RecurringPurchase } from "../../api/types";
import { inPeriod } from "../Receivables/Upcoming";
import { nextDate } from "../Transactions/RecurringTab";

// Written by the same agent as the code (single-agent session); reviewed independently.

// Intl puts a no-break space after "R$"
const plain = (s: string) => s.replace(/\u00a0/g, " ");
const EU = [{ user_id: "eu", pct: "100.00" }];
const CASAL = { split_id: "split_casal" };

describe("price shown in the lists (R14.9)", () => {
  it("r14_9 shows the reajuste in force with its month", () => {
    expect(
      plain(
        describePrice(
          "40.00",
          [{ from_month: "2026-03", amount: "44.90" }],
          "2026-06",
        ),
      ),
    ).toBe("R$ 44,90 (desde mar/2026)");
    expect(plain(describePrice("40.00", [], "2026-06"))).toBe("R$ 40,00");
  });

  it("r14_9 shows the latest reajuste as the main price even when it starts later", () => {
    expect(
      plain(
        describePrice(
          "40.00",
          [
            { from_month: "2027-01", amount: "50.00" },
            { from_month: "2026-03", amount: "44.90" },
          ],
          "2026-06",
        ),
      ),
    ).toBe("R$ 50,00 a partir de jan/2027 (hoje R$ 44,90)");
  });
});

describe("split history (R14.27)", () => {
  it("r14_27 picks the split in force in the month", () => {
    const history = [
      { from_month: "2027-01", allocations: CASAL },
      { from_month: "2027-06", allocations: null },
    ];
    expect(allocationIn(EU, history, "2026-12")).toBe(EU);
    expect(allocationIn(EU, history, "2027-01")).toBe(CASAL);
    expect(allocationIn(EU, history, "2027-07")).toBeNull();
  });

  it("r14_27 describes the current split and the next change", () => {
    const describe = (a: unknown) =>
      a === null ? "Padrão" : JSON.stringify(a);
    expect(
      describeSplit(
        EU,
        [{ from_month: "2027-01", allocations: CASAL }],
        "2026-10",
        describe,
      ),
    ).toBe(
      `${JSON.stringify(EU)} → ${JSON.stringify(CASAL)} a partir de jan/2027`,
    );
    expect(
      describeSplit(
        EU,
        [{ from_month: "2026-01", allocations: null }],
        "2026-10",
        describe,
      ),
    ).toBe("Padrão");
  });

  it("r14_27 validates month, sum and repeated months", () => {
    expect(checkAllocationHistory([])).toBeNull();
    expect(
      checkAllocationHistory([{ from_month: "", allocations: CASAL }]),
    ).toBe("Mudança de divisão: escolha o mês");
    expect(
      checkAllocationHistory([
        {
          from_month: "2027-01",
          allocations: [{ user_id: "eu", pct: "60.00" }],
        },
      ]),
    ).toBe("Mudança de divisão: a soma precisa ser 100%");
    expect(
      checkAllocationHistory([
        { from_month: "2027-01", allocations: CASAL },
        { from_month: "2027-01", allocations: null },
      ]),
    ).toBe("Mudança de divisão: meses repetidos");
  });

  it("r14_27 a gasto recorrente gets a new split from January and the list shows it", async () => {
    const rec = {
      id: "rec_luz",
      description: "Conta de luz",
      match_description: null,
      estimated_amount: "180.00",
      every: { value: 1, unit: "months" },
      last_date: "2026-09-10",
      payment_method: "pix",
      card_id: null,
      account_id: "acc_x",
      category_id: null,
      allocations: EU,
      active: true,
      skipped_dates: [],
      next_date: "2026-10-10",
      group: "household",
    };
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/recurring-purchases": [
        {
          ...rec,
          allocation_history: [{ from_month: "2099-01", allocations: CASAL }],
        },
      ],
      "PUT /api/recurring-purchases/rec_luz": (body: unknown) => body,
    });
    renderPage(<CatalogPage />, "/cadastros?tab=recorrentes");
    expect(
      await screen.findByText(/→ Casal a partir de jan\/2099/),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Editar Conta de luz" }),
    );
    const modal = await screen.findByRole("dialog");
    const changes = within(modal).getByRole("group", {
      name: "Mudanças de divisão",
    });
    await userEvent.click(
      within(changes).getByRole("button", { name: "+ mudança de divisão" }),
    );
    await pickMonth(
      userEvent,
      within(changes).getByLabelText(/A partir de \(mudança 2\)/),
      "2027-01",
    );
    await userEvent.click(
      within(changes).getAllByText("100% para…")[1] as HTMLElement,
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")).toBeDefined(),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      allocations: EU,
      allocation_history: [
        { from_month: "2099-01", allocations: CASAL },
        {
          from_month: "2027-01",
          allocations: [{ user_id: "eu", pct: "100.00" }],
        },
      ],
    });
  });
});

describe("second review (R14.26, R14.28)", () => {
  it("r14_28 with two upcoming reajustes it also says the nearer one", () => {
    expect(
      plain(
        describePrice(
          "40.00",
          [
            { from_month: "2027-07", amount: "55.00" },
            { from_month: "2027-01", amount: "50.00" },
          ],
          "2026-10",
        ),
      ),
    ).toBe(
      "R$ 55,00 a partir de jul/2027 (hoje R$ 40,00; R$ 50,00 em jan/2027)",
    );
  });

  it("r14_28 an overdue open receivable shows in every period", () => {
    const base = { due_date: "2026-08-10", invoice_month: "2026-08" };
    expect(inPeriod(base, "next", "2026-10")).toBe(false);
    expect(
      inPeriod({ ...base, overdue: true, status: "open" }, "next", "2026-10"),
    ).toBe(true);
    expect(
      inPeriod(
        { ...base, overdue: true, status: "received" },
        "this",
        "2026-10",
      ),
    ).toBe(false);
    expect(
      inPeriod({ due_date: null, invoice_month: "2026-11" }, "next", "2026-10"),
    ).toBe(true);
  });

  it("r14_26 a conta da casa's next due date is from this month on, not last_date + every", () => {
    const bill = {
      last_date: "2026-07-10",
      every: { value: 1, unit: "months" as const },
      next_date: null,
      skipped_dates: ["2026-10-10"],
      group: "household" as const,
    } as unknown as RecurringPurchase;
    expect(nextDate(bill, "2026-10")).toBe("2026-11-10"); // October skipped
    expect(nextDate({ ...bill, group: "purchase" }, "2026-10")).toBe(
      "2026-08-10",
    );
  });
});

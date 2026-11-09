import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Transaction } from "../api/types";
import { PayBillForm } from "../pages/Household/HouseholdPage";
import { EditTransactionForm } from "../pages/Transactions/EntriesTab";
import { TransactionsPage } from "../pages/Transactions/TransactionsPage";
import { CATALOG, mockApi, renderPage } from "../test/utils";

// R14.32: which benefit of a benefit card paid it, in the edit form, the list and the bill payment

const CAJU = {
  id: "acc_caju",
  name: "Caju",
  type: "benefit",
  owners: [{ user_id: "eu", pct: "100.00" }],
  responsible_user_id: "eu",
  profile_id: null,
  account_hint: null,
  confirm_manual_after_days: null,
};
const benefit = (id: string, name: string, active = true) => ({
  id,
  name,
  user_id: "eu",
  destination: "card",
  account_id: "acc_caju",
  amount_history: [],
  active,
});
const ROUTES = {
  ...CATALOG,
  "GET /api/accounts": [...CATALOG["GET /api/accounts"], CAJU],
  "GET /api/benefits": [
    benefit("ben_vr", "VR"),
    benefit("ben_ho", "Home office"),
  ],
};

function tx(extra: Partial<Transaction>): Transaction {
  return {
    id: "tx1",
    fingerprint: null,
    kind: "expense",
    source: { type: "manual", sha256: null, path: null, line: null },
    provisional: false,
    payment_method: "benefit",
    card_id: null,
    account_id: "acc_caju",
    purchase_date: "2026-10-05",
    invoice_month: "2026-10",
    description: "ALMOCO",
    amount: "30.00",
    category_id: "cat_casa",
    installment: null,
    links: {},
    allocations: null,
    allocation_origin: null,
    note: null,
    benefit_id: "ben_vr",
    ...extra,
  } as Transaction;
}

const pick = async (label: RegExp, option: string) => {
  await userEvent.click(await screen.findByRole("textbox", { name: label }));
  await userEvent.click(await screen.findByRole("option", { name: option }));
};
const saveAndBody = async (
  calls: { method: string; body: unknown }[],
  method: string,
) => {
  await waitFor(() =>
    expect(calls.some((c) => c.method === method)).toBe(true),
  );
  return calls.find((c) => c.method === method)?.body as Record<
    string,
    unknown
  >;
};

describe("benefício usado (R14.32)", () => {
  it("r14_32 the list shows the benefit in the payment column", async () => {
    mockApi({ ...ROUTES, "GET /api/transactions": [tx({})] });
    renderPage(<TransactionsPage />, "/lancamentos");
    const row = (await screen.findByText("ALMOCO")).closest(
      "tr",
    ) as HTMLElement;
    expect(
      await within(row).findByText(/Cartão de benefícios · VR/),
    ).toBeInTheDocument();
  });

  it("r14_32 editing a manual entry changes the benefit", async () => {
    const { calls } = mockApi({
      ...ROUTES,
      "PATCH /api/transactions/tx1": (body: unknown) => body,
    });
    renderPage(<EditTransactionForm tx={tx({})} onDone={() => {}} />);
    await pick(/Qual benefício/, "Home office");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect((await saveAndBody(calls, "PATCH")).benefit_id).toBe("ben_ho");
  });

  it("r14_32 an imported benefit line only sends the benefit", async () => {
    const { calls } = mockApi({
      ...ROUTES,
      "PATCH /api/transactions/tx1": (body: unknown) => body,
    });
    renderPage(
      <EditTransactionForm
        tx={tx({
          source: {
            type: "import",
            sha256: "s",
            path: "faturas/x.pdf",
            line: 1,
          },
          benefit_id: null,
        })}
        onDone={() => {}}
      />,
    );
    await pick(/Qual benefício/, "Home office");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    const body = await saveAndBody(calls, "PATCH");
    expect(body.benefit_id).toBe("ben_ho");
    expect(body).not.toHaveProperty("payment_method");
    expect(body).not.toHaveProperty("amount");
  });

  it("r14_32 an old choice of a benefit switched off since is kept", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/benefits": [
        benefit("ben_vr", "VR", false),
        benefit("ben_ho", "Home office"),
      ],
    });
    renderPage(<EditTransactionForm tx={tx({})} onDone={() => {}} />);
    expect(
      await screen.findByRole("textbox", { name: /Qual benefício/ }),
    ).toHaveValue("VR (desativado)");
  });

  it("r14_32 paying a conta da casa lets me choose the benefit", async () => {
    const { calls } = mockApi({
      ...ROUTES,
      "POST /api/transactions": {
        transaction: { id: "t" },
        reconciliation: { status: "projected" },
      },
    });
    renderPage(
      <PayBillForm
        bill={{
          source: "recurring",
          id: "rec_net",
          description: "INTERNET",
          category_id: "cat_casa",
          payment_method: "benefit",
          card_id: null,
          account_id: "acc_caju",
          benefit_id: "ben_vr",
          allocations: null,
          due_date: "2026-10-10",
          expected: "100.00",
          paid: "0.00",
          status: "pendente",
          transaction_ids: [],
        }}
        month="2026-10"
        onDone={() => {}}
      />,
    );
    expect(
      await screen.findByRole("textbox", { name: /Qual benefício/ }),
    ).toHaveValue("VR");
    await pick(/Qual benefício/, "Home office");
    await userEvent.click(screen.getByRole("button", { name: "Registrar" }));
    expect((await saveAndBody(calls, "POST")).benefit_id).toBe("ben_ho");
  });
});

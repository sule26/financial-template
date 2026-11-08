import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CATALOG, apiError, mockApi, renderPage } from "../test/utils";
import {
  METHOD_STORAGE_KEY,
  QuickEntryButton,
  ownerStorageKey,
  reconciliationMessage,
} from "./QuickEntry";

// Generous async timeouts: the full suite runs many jsdom files in parallel.
configure({ asyncUtilTimeout: 10000 });
vi.setConfig({ testTimeout: 20000 });

const ACCOUNTS = [
  ...CATALOG["GET /api/accounts"],
  {
    id: "acc_vr",
    name: "VR",
    type: "benefit",
    owners: [{ user_id: "eu", pct: "100.00" }],
    responsible_user_id: "eu",
    profile_id: null,
    account_hint: null,
    confirm_manual_after_days: null,
  },
];

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const SUGGEST = {
  category_id: "cat_lazer",
  category_origin: "history",
  allocations: { split_id: "split_casal" },
  allocation_origin: "rule:r1",
  descriptions: ["Padaria Pão Quente"],
};

async function pick(
  user: ReturnType<typeof userEvent.setup>,
  label: RegExp | string,
  option: string,
) {
  await user.click(screen.getByRole("textbox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

async function openForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "+ Lançar" }));
  return screen.findByRole("dialog", { name: "Lançamento rápido" });
}

describe("QuickEntry", () => {
  beforeEach(() => window.localStorage.clear());

  it("r14_17 an entry landing in another month switches the app to that month", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/transactions/suggest": SUGGEST,
      "POST /api/transactions": {
        transaction: { id: "tx1", invoice_month: "2030-01" },
        reconciliation: { status: "projected" },
      },
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    await openForm(user);
    await user.type(screen.getByRole("textbox", { name: /Valor/ }), "90,00");
    await user.type(
      screen.getByRole("textbox", { name: /Descrição/ }),
      "Dentista",
    );
    await pick(user, /Categoria/, "Casa");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(
      await screen.findByText(
        /Entrou na fatura\/mês de jan\/2030: mostrando esse mês/,
      ),
    ).toBeInTheDocument();
  });

  it("r10_1 sends the manual entry with the right body", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/transactions/suggest": {
        ...SUGGEST,
        category_id: null,
        allocations: null,
      },
      "POST /api/transactions": {
        transaction: { id: "tx1" },
        reconciliation: { status: "projected" },
      },
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    await openForm(user);
    await user.type(screen.getByRole("textbox", { name: /Valor/ }), "12,50");
    await user.type(screen.getByRole("textbox", { name: /Descrição/ }), "Pão");
    await pick(user, /Categoria/, "Casa");
    await user.type(screen.getByRole("textbox", { name: "Nota" }), "café");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    const post = calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/api/transactions");
    expect(post?.body).toEqual({
      purchase_date: today(),
      amount: "12.50",
      description: "Pão",
      category_id: "cat_casa",
      payment_method: "credit",
      card_id: "card_x",
      note: "café",
    });
    expect(
      await screen.findByText(/Lançamento previsto salvo/),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem(METHOD_STORAGE_KEY)).toBe("credit");
    expect(window.localStorage.getItem(ownerStorageKey("credit"))).toBe(
      "card_x",
    );
  });

  it("r1_11 blocks submission without category", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions/suggest": {
        ...SUGGEST,
        category_id: null,
        allocations: null,
      },
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    await openForm(user);
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(
      await screen.findByText("Categoria é obrigatória"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Informe um valor válido/)).toBeInTheDocument();
    expect(screen.getByText("Informe a descrição")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("r10_2 prefills category and allocation from the suggestion", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions/suggest": SUGGEST,
      "POST /api/transactions": {
        transaction: { id: "tx1" },
        reconciliation: {
          status: "absorbed",
          into: "st1",
          document: "faturas/x.pdf",
        },
      },
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    await openForm(user);
    await user.type(screen.getByRole("textbox", { name: /Valor/ }), "8");
    await user.type(screen.getByRole("textbox", { name: /Descrição/ }), "Pad");
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /Categoria/ })).toHaveValue(
        "Lazer",
      ),
    );
    expect(await screen.findByText("sugerida pela descrição")).toBeVisible();
    expect(
      calls.some(
        (c) =>
          c.path.startsWith("/api/transactions/suggest?description=Pad") &&
          c.path.includes("card_id=card_x") &&
          c.path.includes("amount=8.00"),
      ),
    ).toBe(true);
    // the autocomplete offers known descriptions
    await user.click(screen.getByRole("textbox", { name: /Descrição/ }));
    expect(
      await screen.findByRole("option", { name: "Padaria Pão Quente" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    const body = calls.find((c) => c.method === "POST")?.body as Record<
      string,
      unknown
    >;
    expect(body.category_id).toBe("cat_lazer");
    // suggested allocation stays "Padrão": the backend precedence decides
    expect(body).not.toHaveProperty("allocations");
    expect(
      await screen.findByText(/casado com a linha importada/),
    ).toBeVisible();
  });

  it("opens with the N shortcut, but not while typing in an input", async () => {
    mockApi({ ...CATALOG });
    const user = userEvent.setup();
    renderPage(
      <>
        <input aria-label="outro campo" />
        <QuickEntryButton />
      </>,
    );
    await user.type(screen.getByLabelText("outro campo"), "n");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(document.body);
    await user.keyboard("n");
    expect(
      await screen.findByRole("dialog", { name: "Lançamento rápido" }),
    ).toBeInTheDocument();
  });

  it("uses accounts of the right type for non-credit methods and sends installments only for credit", async () => {
    window.localStorage.setItem(METHOD_STORAGE_KEY, "benefit");
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/transactions/suggest": { ...SUGGEST, allocations: null },
      "POST /api/transactions": {
        transaction: { id: "tx1" },
        reconciliation: {
          status: "not_in_document",
          document: "extratos/vr.pdf",
          message: "não está no documento extratos/vr.pdf",
        },
      },
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    const dialog = await openForm(user);
    expect(
      within(dialog).queryByRole("textbox", { name: /Parcelas/ }),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: /^Cartão de benefício/ }),
      ).toHaveValue("VR"),
    );
    await user.type(screen.getByRole("textbox", { name: /Valor/ }), "30");
    await user.type(
      screen.getByRole("textbox", { name: /Descrição/ }),
      "Almoço",
    );
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /Categoria/ })).toHaveValue(
        "Lazer",
      ),
    );
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    const body = calls.find((c) => c.method === "POST")?.body as Record<
      string,
      unknown
    >;
    expect(body.payment_method).toBe("benefit");
    expect(body.account_id).toBe("acc_vr");
    expect(body).not.toHaveProperty("card_id");
    expect(body).not.toHaveProperty("installments");
    expect(await screen.findByText(/não está no documento/)).toBeVisible();
  });

  it("creates an installment plan and blocks an invalid custom split", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/transactions/suggest": {
        ...SUGGEST,
        category_id: "cat_casa",
        allocations: null,
      },
      "POST /api/transactions": {
        plan: { id: "plan1", description: "TV", total_installments: 10 },
      },
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    await openForm(user);
    await user.type(screen.getByRole("textbox", { name: /Valor/ }), "1000");
    await user.type(screen.getByRole("textbox", { name: /Descrição/ }), "TV");
    const parcelas = screen.getByRole("textbox", { name: /Parcelas/ });
    await user.clear(parcelas);
    await user.type(parcelas, "10");
    await user.click(screen.getByRole("radio", { name: "Personalizada" }));
    await user.clear(screen.getByRole("textbox", { name: "Percentual 1" }));
    await user.type(
      screen.getByRole("textbox", { name: "Percentual 1" }),
      "70",
    );
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText(/Divisão inválida/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.clear(screen.getByRole("textbox", { name: "Percentual 1" }));
    await user.type(
      screen.getByRole("textbox", { name: "Percentual 1" }),
      "50",
    );
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    const body = calls.find((c) => c.method === "POST")?.body as Record<
      string,
      unknown
    >;
    expect(body.installments).toBe(10);
    expect(body.allocations).toEqual([
      { user_id: "eu", pct: "50.00" },
      { user_id: "ana", pct: "50.00" },
    ]);
    expect(await screen.findByText(/TV em 10x/)).toBeVisible();
  });

  it("shows the API error and keeps the form open", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/transactions/suggest": SUGGEST,
      "POST /api/transactions": () =>
        apiError(422, "method_not_allowed", "pix not allowed"),
    });
    const user = userEvent.setup();
    renderPage(<QuickEntryButton />);
    await openForm(user);
    await user.type(screen.getByRole("textbox", { name: /Valor/ }), "5");
    await user.type(screen.getByRole("textbox", { name: /Descrição/ }), "Café");
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /Categoria/ })).toHaveValue(
        "Lazer",
      ),
    );
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("pix not allowed")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("formats reconciliation messages", () => {
    expect(reconciliationMessage({})).toBe("Lançamento salvo.");
  });
});

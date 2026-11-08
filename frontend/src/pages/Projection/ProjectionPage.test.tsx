import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Commitment, Projection } from "../../api/types";
import { apiError, CATALOG, mockApi, renderPage } from "../../test/utils";
import { ProjectionPage, type MonthItem } from "./ProjectionPage";

function commitment(
  m: string,
  ratio: string | null,
  band: Commitment["band"],
): Commitment {
  return {
    month: m,
    spent: "4000.00",
    income: ratio ? "9000.00" : null,
    ratio,
    band,
    benefit_spent: "0.00",
    benefit_income: null,
    benefit_ratio: null,
  };
}

const PROJECTION: Projection = {
  months: [
    {
      month: "2026-10",
      total: "1300.00",
      by_card: { card_x: "1000.00", acc_x: "300.00" },
      by_method: { credit: "1000.00", account: "300.00" },
      by_category: { cat_casa: "1000.00", __none__: "300.00" },
      states: { card_x: "open", acc_x: "missing" },
    },
    {
      month: "2026-11",
      total: "700.00",
      by_card: { card_x: "700.00" },
      by_method: { credit: "700.00" },
      by_category: { cat_lazer: "700.00" },
      states: { card_x: "projected" },
    },
  ],
  committed_income: [
    {
      user_id: "eu",
      months: [
        commitment("2026-10", "85.00", "red"),
        commitment("2026-11", "40.00", "green"),
      ],
    },
  ],
};

const ITEMS: MonthItem[] = [
  {
    month: "2026-10",
    description: "Netflix",
    amount: "55.90",
    kind: "expense",
    payment_method: "credit",
    origin: "subscription",
    card_id: "card_x",
    account_id: null,
    category_id: "cat_lazer",
    ref_id: "sub_1",
    purchase_date: null,
    provisional: false,
    forecast: true,
  },
  {
    month: "2026-10",
    description: "Mercado",
    amount: "200.00",
    kind: "expense",
    payment_method: "credit",
    origin: "transaction",
    card_id: "card_x",
    account_id: null,
    category_id: "cat_casa",
    ref_id: "tx_1",
    purchase_date: "2026-09-28",
    provisional: false,
    forecast: false,
  },
];

const ROUTES = {
  ...CATALOG,
  "GET /api/reports/projection": PROJECTION,
  "GET /api/reports/month-items": ITEMS,
};

describe("ProjectionPage", () => {
  it("r8_5 r8_9 renders month × card table with states and totals", async () => {
    mockApi(ROUTES);
    renderPage(<ProjectionPage />);
    const table = await screen.findByRole("table", {
      name: "Projeção por mês e cartão",
    });
    expect(await within(table).findByText("Cartão X")).toBeInTheDocument();
    expect(within(table).getByText("Conta X")).toBeInTheDocument();
    expect(within(table).getByText("fatura aberta")).toBeInTheDocument();
    expect(within(table).getByText("faltando")).toBeInTheDocument();
    expect(within(table).getByText("projetado")).toBeInTheDocument();
    expect(screen.getByTestId("projection-total")).toHaveTextContent(
      "R$ 2.000,00",
    );
    // card column total 1000 + 700
    expect(within(table).getByText("R$ 1.700,00")).toBeInTheDocument();
    expect(screen.getByText("Por categoria")).toBeInTheDocument();
  });

  it("r1_9 shows committed income per month with band", async () => {
    mockApi(ROUTES);
    renderPage(<ProjectionPage />);
    const table = await screen.findByRole("table", {
      name: "Renda comprometida por mês",
    });
    const high = within(table).getByText(/85%/);
    expect(high.closest("[data-band]")).toHaveAttribute("data-band", "red");
    expect(high).toHaveTextContent("alto");
    expect(within(table).getByText(/40%/)).toHaveTextContent("confortável");
  });

  it("r1_13 r5_5 filters change the projection query", async () => {
    const { calls } = mockApi(ROUTES);
    renderPage(<ProjectionPage />);
    await screen.findByRole("table", { name: "Projeção por mês e cartão" });
    const paths = () => calls.map((c) => c.path);
    expect(paths()).toContain("/api/reports/projection");
    await userEvent.click(
      screen.getByRole("switch", { name: "Incluir não confirmados" }),
    );
    await userEvent.click(screen.getByRole("textbox", { name: "Pessoas" }));
    await userEvent.click(await screen.findByRole("option", { name: "Eu" }));
    await waitFor(() =>
      expect(paths()).toContain(
        "/api/reports/projection?user_id=eu&include_pending=true",
      ),
    );
  });

  it("r1_13 with a person sends user_id and shows only the columns the API returns", async () => {
    const forAna: Projection = {
      months: [
        {
          month: "2026-10",
          total: "250.00",
          by_card: { acc_x: "250.00" },
          by_method: { account: "250.00" },
          by_category: { cat_casa: "250.00" },
          states: { acc_x: "real" },
        },
      ],
      committed_income: [],
    };
    const { calls } = mockApi({
      ...ROUTES,
      "GET /api/reports/projection": (_body: unknown, url: URL) =>
        url.searchParams.get("user_id") === "ana" ? forAna : PROJECTION,
    });
    renderPage(<ProjectionPage />);
    const table = await screen.findByRole("table", {
      name: "Projeção por mês e cartão",
    });
    expect(await within(table).findByText("Cartão X")).toBeInTheDocument();
    expect(within(table).getByText("Total dos cartões")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("textbox", { name: "Pessoas" }));
    await userEvent.click(await screen.findByRole("option", { name: "Ana" }));
    await waitFor(() =>
      expect(calls.map((c) => c.path)).toContain(
        "/api/reports/projection?user_id=ana",
      ),
    );
    expect(
      await screen.findByText(/Parte de Ana nos cartões dele\(a\)/),
    ).toBeInTheDocument();
    const filtered = screen.getByRole("table", {
      name: "Projeção por mês e cartão",
    });
    await waitFor(() =>
      expect(within(filtered).queryByText("Cartão X")).not.toBeInTheDocument(),
    );
    const headers = within(filtered)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers.slice(0, 3)).toEqual([
      "Mês",
      "Conta X",
      "Total dos cartões",
    ]);
    expect(screen.getByTestId("projection-total")).toHaveTextContent(
      "R$ 250,00",
    );
  });

  it("clicking a month lists its items with origin and forecast flag", async () => {
    const { calls } = mockApi(ROUTES);
    renderPage(<ProjectionPage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Ver itens de out/2026" }),
    );
    const items = await screen.findByRole("table", {
      name: "Itens de out/2026",
    });
    expect(within(items).getByText("Netflix")).toBeInTheDocument();
    expect(within(items).getByText("assinatura")).toBeInTheDocument();
    expect(within(items).getByText("previsto")).toBeInTheDocument();
    expect(within(items).getByText("transação")).toBeInTheDocument();
    expect(within(items).getByText("28/09/2026")).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/month-items?month=2026-10&cards_only=true",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Fechar itens do mês" }),
    );
    expect(
      screen.queryByRole("table", { name: "Itens de out/2026" }),
    ).not.toBeInTheDocument();
  });

  it("r14_2 month items follow the selected person and show their part of the whole", async () => {
    const part = [{ ...ITEMS[1]!, amount: "100.00", total_amount: "200.00" }];
    const { calls } = mockApi({
      ...ROUTES,
      "GET /api/reports/month-items": part,
    });
    renderPage(<ProjectionPage />);
    await userEvent.click(
      await screen.findByRole("textbox", { name: "Pessoas" }),
    );
    await userEvent.click(await screen.findByRole("option", { name: "Ana" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Ver itens de out/2026" }),
    );
    const items = await screen.findByRole("table", {
      name: "Itens de out/2026 · parte de Ana",
    });
    expect(within(items).getByText("R$ 100,00")).toBeInTheDocument();
    expect(within(items).getByText("de R$ 200,00")).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/month-items?month=2026-10&cards_only=true&user_id=ana",
    );
  });

  it("shows empty month items", async () => {
    mockApi({ ...ROUTES, "GET /api/reports/month-items": [] });
    renderPage(<ProjectionPage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Ver itens de nov/2026" }),
    );
    expect(
      await screen.findByText("Nenhum item neste mês."),
    ).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/projection": { months: [], committed_income: [] },
    });
    renderPage(<ProjectionPage />);
    expect(
      await screen.findByText("Sem dados de projeção."),
    ).toBeInTheDocument();
  });

  it("shows the API error", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/projection": () => apiError(500, "boom", "falhou"),
    });
    renderPage(<ProjectionPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("falhou");
  });

  it("hides committed income when no user has income and handles no categories", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/projection": {
        months: [{ ...PROJECTION.months[1], by_category: {} }],
        committed_income: [],
      },
    });
    renderPage(<ProjectionPage />);
    expect(
      await screen.findByText("Sem gastos projetados."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Renda comprometida")).not.toBeInTheDocument();
  });
});

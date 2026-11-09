import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { MonthSeries, Projection, Summary } from "../../api/types";
import { formatMoney } from "../../lib/format";
import { apiError, CATALOG, mockApi, renderPage } from "../../test/utils";
import { SummaryPage } from "./SummaryPage";
import { buildQuery, plotValue, moneyTooltip } from "./shared";

function month(
  m: string,
  total: string,
  extra: Partial<MonthSeries> = {},
): MonthSeries {
  return {
    month: m,
    total,
    income: "9000.00",
    by_card: { card_x: total },
    by_method: { credit: total },
    states: { card_x: "real" },
    ...extra,
  };
}

const SUMMARY: Summary = {
  month: "2026-10",
  total: "1500.00",
  by_category: { cat_casa: "1000.00", __none__: "500.00" },
  uncategorized_key: "__none__",
  by_card: { card_x: "1200.00", acc_x: "300.00" },
  by_method: { credit: "1200.00", account: "300.00" },
  states: { card_x: "open", acc_x: "missing" },
  series: [
    month("2026-09", "800.00"),
    month("2026-10", "1500.00", {
      by_card: { card_x: "1200.00", acc_x: "300.00" },
      by_method: { credit: "1200.00", account: "300.00" },
    }),
  ],
  annual: {
    "2026-09": { cat_casa: "800.00" },
    "2026-10": { cat_casa: "1000.00", __none__: "500.00" },
  },
  goals: { goal_res: { target: "500.00", achieved: "200.00" } },
};

const PROJECTION: Projection = {
  months: [],
  committed_income: [
    {
      user_id: "eu",
      months: [
        {
          month: "2026-10",
          spent: "6300.00",
          income: "9000.00",
          ratio: "70.00",
          band: "yellow",
          benefit_spent: "0.00",
          benefit_income: null,
          benefit_ratio: null,
        },
      ],
    },
  ],
};

const ROUTES = {
  ...CATALOG,
  "GET /api/savings-goals": [
    {
      id: "goal_res",
      name: "Reserva",
      monthly_amount: "500.00",
      user_id: null,
    },
  ],
  "GET /api/reports/summary": SUMMARY,
  "GET /api/reports/projection": PROJECTION,
};

describe("SummaryPage", () => {
  it("r1_6 renders total, category pie table, annual table, goals and card states", async () => {
    mockApi(ROUTES);
    renderPage(<SummaryPage />);
    expect(await screen.findByTestId("month-total")).toHaveTextContent(
      "R$ 1.500,00",
    );
    const cats = screen.getByRole("table", { name: "Gastos por categoria" });
    expect(await within(cats).findByText("Casa")).toBeInTheDocument();
    expect(within(cats).getByText("Sem categoria")).toBeInTheDocument();
    expect(screen.getByText("Gasto x renda (12 meses)")).toBeInTheDocument();
    expect(screen.getByText("Por cartão/conta")).toBeInTheDocument();

    const annual = screen.getByRole("table", {
      name: "Resumo anual por categoria",
    });
    expect(within(annual).getByText("Sem categoria")).toBeInTheDocument();
    // Casa row total 800 + 1000; grand total 2300
    expect(within(annual).getByText("R$ 1.800,00")).toBeInTheDocument();
    expect(within(annual).getByText("R$ 2.300,00")).toBeInTheDocument();

    expect(await screen.findByText("Reserva")).toBeInTheDocument();
    expect(screen.getByText("R$ 200,00 de R$ 500,00")).toBeInTheDocument();

    // R14.33: the card/account states left the Resumo (the alerts banner covers them)
    expect(
      screen.queryByRole("table", { name: "Estado por cartão/conta" }),
    ).toBeNull();
  });

  it("r1_9 shows committed income of the selected month with its band", async () => {
    mockApi(ROUTES);
    renderPage(<SummaryPage />);
    const table = await screen.findByRole("table", {
      name: "Gasto por pessoa no mês",
    });
    expect(within(table).getByText("Eu")).toBeInTheDocument();
    const badge = within(table).getByText(/70%/);
    expect(badge.closest("[data-band]")).toHaveAttribute("data-band", "yellow");
    expect(badge).toHaveTextContent("atenção");
  });

  it("r14_33 'Gasto por pessoa' lists people without income too", async () => {
    const row = (income: string | null) => ({
      month: "2026-10",
      spent: "300.00",
      income,
      ratio: income ? "3.33" : null,
      band: income ? ("green" as const) : null,
      benefit_spent: "0.00",
      benefit_income: null,
      benefit_ratio: null,
    });
    mockApi({
      ...ROUTES,
      "GET /api/reports/projection": {
        months: [],
        committed_income: [{ user_id: "eu", months: [row("9000.00")] }],
        people: [
          { user_id: "eu", months: [row("9000.00")] },
          { user_id: "ana", months: [row(null)] },
        ],
      },
    });
    renderPage(<SummaryPage />);
    const table = await screen.findByRole("table", {
      name: "Gasto por pessoa no mês",
    });
    const ana = within(table).getByText("Ana").closest("tr") as HTMLElement;
    expect(ana).toHaveTextContent("R$ 300,00");
    expect(within(ana).getByText("sem renda cadastrada")).toBeInTheDocument();
    const eu = within(table).getByText("Eu").closest("tr") as HTMLElement;
    expect(eu).toHaveTextContent("R$ 9.000,00");
    expect(eu).toHaveTextContent("3,33%");
  });

  it("r14_36 annual tables by category and card, current month marked, totals with/without benefit", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/summary": {
        ...SUMMARY,
        annual_by_card: {
          "2026-09": { card_x: "800.00" },
          "2026-10": { card_x: "1200.00", acc_x: "300.00" },
        },
        annual_benefit: { "2026-09": "0.00", "2026-10": "300.00" },
      },
    });
    renderPage(<SummaryPage />);
    const byCard = await screen.findByRole("table", {
      name: "Resumo anual por cartão/conta",
    });
    expect(await within(byCard).findByText("Cartão X")).toBeInTheDocument();
    // today is 2026-10-12 in tests
    const head = within(byCard).getByRole("columnheader", { name: "out/2026" });
    expect(head).toHaveAttribute("aria-current", "date");
    expect(head).toHaveClass("et-current-month");
    const without = within(byCard)
      .getByText("Total sem benefício")
      .closest("tr") as HTMLElement;
    expect(without).toHaveTextContent("R$ 1.200,00"); // 1500 − 300 in October
    const withB = within(byCard)
      .getByText("Total com benefício")
      .closest("tr") as HTMLElement;
    expect(withB).toHaveTextContent("R$ 1.500,00");
    const byCat = screen.getByRole("table", {
      name: "Resumo anual por categoria",
    });
    expect(within(byCat).getByText("Total sem benefício")).toBeInTheDocument();
  });

  it("r5_5 r11_4 filters change the summary query string", async () => {
    const { calls } = mockApi(ROUTES);
    renderPage(<SummaryPage />);
    await screen.findByTestId("month-total");
    const summaryCalls = () =>
      calls
        .filter((c) => c.path.startsWith("/api/reports/summary"))
        .map((c) => c.path);
    expect(summaryCalls()[0]).toBe("/api/reports/summary?month=2026-10");

    await userEvent.click(
      screen.getByRole("switch", { name: "Incluir não confirmados" }),
    );
    await waitFor(() =>
      expect(summaryCalls()).toContain(
        "/api/reports/summary?month=2026-10&include_pending=true",
      ),
    );

    await userEvent.click(
      screen.getByRole("textbox", { name: "Meio de pagamento" }),
    );
    await userEvent.click(
      await screen.findByRole("option", { name: "Cartão de benefícios" }),
    );
    await waitFor(() =>
      expect(summaryCalls()).toContain(
        "/api/reports/summary?month=2026-10&include_pending=true&payment_method=benefit",
      ),
    );

    await userEvent.click(screen.getByRole("textbox", { name: "Pessoas" }));
    await userEvent.click(await screen.findByRole("option", { name: "Ana" }));
    await waitFor(() =>
      expect(summaryCalls()).toContain(
        "/api/reports/summary?month=2026-10&user_id=ana&include_pending=true&payment_method=benefit",
      ),
    );
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/projection?user_id=ana&include_pending=true",
    );
  });

  it("shows empty panels when the month has no spending", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/summary": {
        ...SUMMARY,
        total: "0.00",
        by_category: {},
        states: {},
        series: [{ ...month("2026-10", "0.00"), by_card: {}, by_method: {} }],
        annual: {},
        goals: {},
      },
    });
    renderPage(<SummaryPage />);
    expect(
      await screen.findByText("Sem gastos neste mês."),
    ).toBeInTheDocument();
    // by card, by payment method and the category history (R14.37)
    expect(screen.getAllByText("Sem gastos no período.")).toHaveLength(3);
    expect(screen.getByText("Sem gastos no ano.")).toBeInTheDocument();
    expect(screen.queryByText("Metas de poupança")).not.toBeInTheDocument();
  });

  it("shows the API error", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/summary": () =>
        apiError(422, "invalid", "mês inválido"),
    });
    renderPage(<SummaryPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("mês inválido");
  });
});

describe("report helpers", () => {
  it("buildQuery skips empty values and false flags", () => {
    expect(buildQuery({ a: "1", b: null, c: false, d: true, e: "" })).toBe(
      "?a=1&d=true",
    );
    expect(buildQuery({})).toBe("");
  });
  it("plotValue and moneyTooltip", () => {
    expect(plotValue("12.50")).toBe(12.5);
    expect(plotValue("x")).toBe(0);
    expect(plotValue(null)).toBe(0);
    expect(moneyTooltip(12.5)).toBe(formatMoney("12.50"));
    expect(moneyTooltip("3.00")).toBe(formatMoney("3.00"));
  });
});

describe("SummaryPage dynamic catalog", () => {
  it("r1_7 shows a newly created category without any other action", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/categories": [
        ...CATALOG["GET /api/categories"],
        { id: "cat_pets", name: "Pets", color: "#FAB005", budget: null },
      ],
      "GET /api/reports/summary": {
        ...SUMMARY,
        by_category: { ...SUMMARY.by_category, cat_pets: "120.00" },
      },
    });
    renderPage(<SummaryPage />);
    const cats = await screen.findByRole("table", {
      name: "Gastos por categoria",
    });
    expect(await within(cats).findByText("Pets")).toBeInTheDocument();
  });
});

describe("Histórico por categoria (R14.37)", () => {
  const withCats = {
    ...SUMMARY,
    series: [
      month("2026-09", "800.00", { by_category: { cat_casa: "200.00" } }),
      month("2026-10", "1500.00", {
        by_category: { cat_casa: "1000.00", __none__: "500.00" },
      }),
    ],
  };

  it("r14_37 with nothing chosen shows every category, and the month shares in the list", async () => {
    mockApi({ ...ROUTES, "GET /api/reports/summary": withCats });
    renderPage(<SummaryPage />);
    const summary = await screen.findByLabelText("Resumo do histórico");
    // every category: (200 in September + 1500 in October) / 2 months
    expect(summary).toHaveTextContent("R$ 850,00");
    expect(summary).toHaveTextContent("todas (2)");
    // "Gastos por categoria": Casa is 1000 of 1500 in October
    const cats = screen.getByRole("table", { name: "Gastos por categoria" });
    const casa = (
      await within(cats).findByRole("button", { name: "Ver histórico de Casa" })
    ).closest("tr") as HTMLElement;
    expect(casa).toHaveTextContent("67%");
  });

  it("r14_37 clicking a category in 'Gastos por categoria' shows its history", async () => {
    mockApi({ ...ROUTES, "GET /api/reports/summary": withCats });
    renderPage(<SummaryPage />);
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Ver histórico de Sem categoria",
      }),
    );
    const summary = screen.getByLabelText("Resumo do histórico");
    // 0 + 500 over 2 months; 500 of 2300 = 21,7%
    expect(summary).toHaveTextContent("R$ 250,00");
    expect(summary).toHaveTextContent("21,7%");
  });
});

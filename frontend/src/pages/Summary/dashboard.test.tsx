import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Projection } from "../../api/types";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { committedIncome, percentChange, SummaryPage } from "./SummaryPage";

const PROJECTION: Projection = {
  months: [],
  committed_income: [
    {
      user_id: "eu",
      months: [
        {
          month: "2026-10",
          spent: "100.00",
          income: "9000.00",
          ratio: "1.00",
          band: "green",
          benefit_spent: "0.00",
          benefit_income: null,
          benefit_ratio: null,
        },
      ],
    },
    {
      user_id: "ana",
      months: [
        {
          month: "2026-10",
          spent: "0.00",
          income: "1000.00",
          ratio: "0.00",
          band: "green",
          benefit_spent: "0.00",
          benefit_income: null,
          benefit_ratio: null,
        },
      ],
    },
  ],
};

describe("dashboard helpers", () => {
  it("percentChange", () => {
    expect(percentChange("150.00", "100.00")).toBe(50);
    expect(percentChange("50.00", "100.00")).toBe(-50);
    expect(percentChange("50.00", "0.00")).toBeNull();
    expect(percentChange("50.00", null)).toBeNull();
  });

  it("committedIncome sums the month's incomes of every user", () => {
    expect(committedIncome(PROJECTION, "2026-10")).toBe("10000.00");
    expect(committedIncome(PROJECTION, "2026-11")).toBeNull();
    expect(committedIncome(undefined, "2026-10")).toBeNull();
  });
});

describe("Summary KPIs", () => {
  it("shows the banknote with delta vs previous month, income fallback and leftover", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/savings-goals": [],
      "GET /api/reports/projection": PROJECTION,
      "GET /api/reports/summary": {
        month: "2026-10",
        total: "1500.00",
        by_category: {},
        uncategorized_key: "__none__",
        by_card: {},
        by_method: {},
        states: {},
        series: [
          {
            month: "2026-09",
            total: "1000.00",
            income: null,
            by_card: {},
            by_method: {},
            states: {},
          },
          {
            month: "2026-10",
            total: "1500.00",
            income: null,
            by_card: {},
            by_method: {},
            states: {},
          },
        ],
        annual: {},
        goals: {},
      },
    });
    renderPage(<SummaryPage />);
    expect(await screen.findByTestId("month-total")).toHaveTextContent(
      "R$ 1.500,00",
    );
    expect(screen.getByText("+50%").closest("[data-trend]")).toHaveAttribute(
      "data-trend",
      "bad",
    );
    expect(screen.getByText("vs set/2026")).toBeInTheDocument();
    expect(screen.getByText("OUT · 2026")).toBeInTheDocument();
    expect(await screen.findByText("R$ 10.000,00")).toBeInTheDocument();
    const leftover = screen.getByText("R$ 8.500,00");
    expect(leftover).toHaveAttribute("data-tone", "positive");
    expect(
      screen.getByText("Nenhum cartão ou conta com movimento no mês."),
    ).toBeInTheDocument();
  });
});

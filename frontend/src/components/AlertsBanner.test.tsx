import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CATALOG, mockApi, renderPage } from "../test/utils";
import { AlertsBanner } from "./AlertsBanner";

describe("AlertsBanner", () => {
  it("r1_12 shows every global alert type", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/alerts": [
        { type: "uncategorized", count: 3, items: {} },
        {
          type: "recurring_overdue",
          description: "RACAO",
          planned_date: "2026-11-04",
        },
        { type: "missing_invoice", card_id: "card_x", month: "2026-08" },
        { type: "inconsistent_files", count: 1, paths: ["faturas/a.pdf"] },
        { type: "files_need_attention", count: 2, paths: [] },
      ],
    });
    renderPage(<AlertsBanner />);
    expect(
      await screen.findByText("3 itens sem categoria"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/RACAO prevista em 04\/11\/2026/),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Cartão X: fatura de 2026-08/),
    ).toBeInTheDocument();
    expect(screen.getByText("Arquivo sem lançamentos")).toBeInTheDocument();
    expect(
      screen.getByText("2 arquivo(s) precisam de atenção"),
    ).toBeInTheDocument();
  });

  it("renders nothing without alerts", async () => {
    mockApi({ ...CATALOG });
    const { container } = renderPage(<AlertsBanner />);
    await new Promise((r) => setTimeout(r, 50));
    expect(container.querySelector('[aria-label="Alertas"]')).toBeNull();
  });
});

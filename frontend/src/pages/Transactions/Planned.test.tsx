import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { PlannedInstallments } from "./EntriesTab";

const row = (extra: Record<string, unknown>) => ({
  description: "X",
  amount: "10.00",
  origin: "plan",
  card_id: "card_x",
  account_id: null,
  ref_id: "r",
  purchase_date: null,
  installment: null,
  ...extra,
});

describe("Previstos neste mês (R14.19, R14.29)", () => {
  it("r14_29 lists installments, subscriptions and gastos recorrentes not launched yet", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/month-items": [
        row({ description: "GELADEIRA", installment: { n: 3, of: 10 } }),
        row({
          description: "STREAMING",
          origin: "subscription",
          amount: "55.90",
        }),
        row({
          description: "LUZ",
          origin: "recurring",
          card_id: null,
          account_id: "acc_x",
          purchase_date: "2026-10-10",
        }),
        row({ description: "MERCADO", origin: "transaction" }), // already a lançamento
      ],
    });
    renderPage(<PlannedInstallments month="2026-10" />);
    const table = await screen.findByRole("table", {
      name: "Previstos neste mês",
    });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("parcela 3/10");
    expect(rows[1]).toHaveTextContent("assinatura");
    expect(rows[2]).toHaveTextContent("gasto recorrente");
    expect(rows[2]).toHaveTextContent("10/10/2026");
    expect(rows[2]).toHaveTextContent("Conta X");
    expect(table).not.toHaveTextContent("MERCADO");
  });

  it("r14_29 shows nothing when nothing is expected", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/reports/month-items": [row({ origin: "transaction" })],
    });
    renderPage(<PlannedInstallments month="2026-10" />);
    await new Promise((r) => setTimeout(r, 50));
    expect(
      screen.queryByRole("table", { name: "Previstos neste mês" }),
    ).toBeNull();
  });
});

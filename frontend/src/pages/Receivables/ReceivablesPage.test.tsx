import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Balances, Receivables, Settlement } from "../../api/types";
import {
  apiError,
  CATALOG,
  mockApi,
  pickDate,
  renderPage,
} from "../../test/utils";
import { balanceText, ReceivablesPage } from "./ReceivablesPage";

function settlement(extra: Partial<Settlement> = {}): Settlement {
  return {
    id: "set_1",
    origin: { type: "manual", fingerprint: null },
    from_user_id: "ana",
    to_user_id: "eu",
    amount: "40.00",
    date: "2026-10-05",
    month: "2026-09",
    note: "pix",
    warnings: [],
    ...extra,
  };
}

const BALANCES: Balances = {
  user_id: "eu",
  incomplete_months: ["2026-08"],
  people: [
    {
      user_id: "ana",
      net: "60.00",
      months: [
        {
          month: "2026-08",
          net: "-20.00",
          incomplete: true,
          lines: [{ ref_id: "tx_2", description: "Jantar", amount: "-20.00" }],
          settlements: [],
        },
        {
          month: "2026-09",
          net: "80.00",
          incomplete: false,
          lines: [{ ref_id: "tx_1", description: "Mercado", amount: "120.00" }],
          settlements: [
            settlement(),
            settlement({
              id: "set_2",
              origin: { type: "import", fingerprint: "fp" },
              amount: "10.00",
              note: null,
            }),
          ],
        },
      ],
    },
  ],
};

const RECEIVABLES: Receivables = {
  user_id: "eu",
  items: [],
  totals: { receive: "0.00", pay: "0.00" },
};

const ROUTES = {
  ...CATALOG,
  "GET /api/reports/balances": BALANCES,
  "GET /api/reports/receivables": RECEIVABLES,
};

async function openAna() {
  await userEvent.click(
    await screen.findByRole("button", { name: /Ana te deve/ }),
  );
  await screen.findByRole("region", { name: "Saldo de set/2026" });
}

describe("ReceivablesPage", () => {
  it("r6_5 shows balance per person, per month and per line", async () => {
    const { calls } = mockApi(ROUTES);
    renderPage(<ReceivablesPage />);
    expect(await screen.findByText("Ana te deve R$ 60,00")).toBeInTheDocument();
    expect(calls.map((c) => c.path)).toContain(
      "/api/reports/balances?user_id=eu",
    );
    expect(screen.getByText("Saldos incompletos")).toBeInTheDocument();
    await openAna();
    const aug = await screen.findByRole("region", {
      name: "Saldo de ago/2026",
    });
    expect(
      within(aug).getByText("Você deve R$ 20,00 a Ana"),
    ).toBeInTheDocument();
    expect(within(aug).getByText("incompleto")).toBeInTheDocument();
    const sep = screen.getByRole("region", { name: "Saldo de set/2026" });
    expect(within(sep).getByText("Mercado")).toBeInTheDocument();
    expect(
      within(sep).getByText(
        /Ana pagou R\$\s40,00 para Eu em 05\/10\/2026 — pix/,
      ),
    ).toBeInTheDocument();
    // imported settlements cannot be deleted here
    expect(
      within(sep).getAllByRole("button", { name: /Excluir acerto/ }),
    ).toHaveLength(1);
  });

  it("r6_5 'eu sou' and pending switch change the balances query", async () => {
    const { calls } = mockApi(ROUTES);
    renderPage(<ReceivablesPage />);
    await screen.findByText("Ana te deve R$ 60,00");
    await userEvent.click(
      screen.getByRole("switch", { name: "Incluir não confirmados" }),
    );
    await userEvent.click(screen.getByRole("textbox", { name: "Eu sou" }));
    await userEvent.click(await screen.findByRole("option", { name: "Ana" }));
    await waitFor(() =>
      expect(calls.map((c) => c.path)).toContain(
        "/api/reports/balances?user_id=ana&include_pending=true",
      ),
    );
  });

  it("r6_4 registers a settlement with the right body", async () => {
    const { calls } = mockApi({
      ...ROUTES,
      "POST /api/settlements": (body: unknown) => ({
        id: "set_9",
        ...(body as object),
      }),
    });
    renderPage(<ReceivablesPage />);
    await screen.findByText("Ana te deve R$ 60,00");
    await userEvent.click(
      screen.getByRole("button", { name: "Registrar acerto" }),
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Valor/), "1.234,5");
    const date = within(dialog).getByLabelText(/Data/);
    await pickDate(userEvent, date, "2026-10-11");
    await userEvent.type(
      within(dialog).getByLabelText("Nota"),
      "acerto de set",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Salvar acerto" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        from_user_id: "ana",
        to_user_id: "eu",
        amount: "1234.50",
        date: "2026-10-11",
        month: "2026-10",
        note: "acerto de set",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("r6_4 validates amount and distinct people, and shows API errors", async () => {
    const { calls } = mockApi({
      ...ROUTES,
      "POST /api/settlements": () =>
        apiError(422, "invalid", "acerto inválido"),
    });
    renderPage(<ReceivablesPage />);
    await screen.findByText("Ana te deve R$ 60,00");
    await userEvent.click(
      screen.getByRole("button", { name: "Registrar acerto" }),
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Salvar acerto" }),
    );
    expect(
      within(dialog).getByText("Informe um valor positivo"),
    ).toBeInTheDocument();

    await userEvent.click(
      within(dialog).getByRole("textbox", { name: /De \(quem pagou\)/ }),
    );
    await userEvent.click(await screen.findByRole("option", { name: "Eu" }));
    expect(
      within(dialog).getByText("Escolha pessoas diferentes"),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);

    await userEvent.click(
      within(dialog).getByRole("textbox", { name: /Para \(quem recebeu\)/ }),
    );
    await userEvent.click(await screen.findByRole("option", { name: "Ana" }));
    await userEvent.type(within(dialog).getByLabelText(/Valor/), "10");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Salvar acerto" }),
    );
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "acerto inválido",
    );
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      from_user_id: "eu",
      to_user_id: "ana",
      amount: "10.00",
      note: null,
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Cancelar" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("deletes a manual settlement after confirmation", async () => {
    const { calls } = mockApi({
      ...ROUTES,
      "DELETE /api/settlements/set_1": { deleted: "set_1" },
    });
    renderPage(<ReceivablesPage />);
    await openAna();
    await userEvent.click(
      screen.getByRole("button", { name: /Excluir acerto de R\$\s40,00/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Excluir acerto de R\$\s40,00/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar exclusão" }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "DELETE" && c.path === "/api/settlements/set_1",
        ),
      ).toBe(true),
    );
  });

  it("warns when the origin of a settlement was removed", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/balances": {
        ...BALANCES,
        incomplete_months: [],
        people: [
          {
            user_id: "ana",
            net: "0.00",
            months: [
              {
                month: "2026-09",
                net: "0.00",
                incomplete: false,
                lines: [],
                settlements: [
                  settlement({
                    warnings: ["origem removida: extrato apagado"],
                  }),
                ],
              },
            ],
          },
        ],
      },
    });
    renderPage(<ReceivablesPage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Vocês estão quites com Ana" }),
    );
    expect(screen.getByText("Origem removida")).toBeInTheDocument();
    expect(
      screen.getByText("origem removida: extrato apagado"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Saldos incompletos")).not.toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/balances": { ...BALANCES, people: [] },
    });
    renderPage(<ReceivablesPage />);
    expect(
      await screen.findByText("Nenhum saldo com outras pessoas."),
    ).toBeInTheDocument();
  });

  it("shows the API error", async () => {
    mockApi({
      ...ROUTES,
      "GET /api/reports/balances": () =>
        apiError(404, "not_found", "usuário não existe"),
    });
    renderPage(<ReceivablesPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "usuário não existe",
    );
  });

  it("balanceText covers positive, negative and zero", () => {
    expect(balanceText("10.00", "Ana")).toMatch(/^Ana te deve R\$\s10,00$/);
    expect(balanceText("-10.00", "Ana")).toMatch(
      /^Você deve R\$\s10,00 a Ana$/,
    );
    expect(balanceText("0.00", "Ana")).toBe("Vocês estão quites com Ana");
  });
});

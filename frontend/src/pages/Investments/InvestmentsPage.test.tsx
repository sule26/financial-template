import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Institution, InvestmentsReport } from "../../api/types";
import {
  apiError,
  CATALOG,
  mockApi,
  pickDate,
  renderPage,
} from "../../test/utils";
import { todayIso } from "./InvestmentForms";
import { chartData, InvestmentsPage } from "./InvestmentsPage";

const CDB = {
  id: "inv_cdb",
  name: "CDB Banco X",
  institution: "Banco X",
  type: "fixed_income",
  owners: [{ user_id: "eu", pct: "100.00" }],
  goal_id: null,
  account_id: null,
  snapshots: [{ date: "2026-08-01", balance: "20150.00" }],
  movements: [
    {
      date: "2026-07-01",
      type: "contribution",
      amount: "20000.00",
      origin: { type: "manual", fingerprint: null },
      warnings: [],
    },
  ],
  closed_at: null,
};
const PREV = {
  ...CDB,
  id: "inv_prev",
  name: "Prev XP",
  institution: null,
  type: "pension",
  snapshots: [],
  movements: [],
  closed_at: "2026-09-30",
};

const REPORT: InvestmentsReport = {
  total: "20150.00",
  yield_total: "150.00",
  by_type: { fixed_income: "20150.00", pension: "0.00" },
  by_user: { eu: "20150.00" },
  positions: [
    {
      investment_id: "inv_cdb",
      balance: "20150.00",
      balance_date: "2026-08-01",
      net_contributions: "20000.00",
      yield: "150.00",
      stale: true,
      estimated: false,
    },
    {
      investment_id: "inv_prev",
      balance: "500.00",
      balance_date: null,
      net_contributions: "500.00",
      yield: null,
      stale: false,
      estimated: true,
    },
  ],
  evolution: [
    { month: "2026-09", balance: "20150.00", contributions: "20000.00" },
    { month: "2026-10", balance: "20150.00", contributions: "20000.00" },
  ],
};

const routes = (extra: Record<string, unknown> = {}) => ({
  ...CATALOG,
  "GET /api/savings-goals": [
    { id: "g1", name: "Reserva", monthly_amount: "500.00", user_id: null },
  ],
  "GET /api/investments": [CDB, PREV],
  "GET /api/reports/investments": REPORT,
  ...extra,
});
const page = () => renderPage(<InvestmentsPage />, "/investimentos");
const lastBody = (calls: { method: string; body: unknown }[], method: string) =>
  [...calls].reverse().find((c) => c.method === method)?.body;

describe("InvestmentsPage", () => {
  it("r9_5 shows totals, per-user total, yield and positions with stale/estimated flags", async () => {
    mockApi(routes());
    page();
    expect(await screen.findByText("Total investido")).toBeInTheDocument();
    expect(
      screen.getByText("Rendimento acumulado").nextSibling,
    ).toHaveTextContent(/150,00/);
    expect(
      within(screen.getByLabelText("Total por usuário")).getByText("Eu"),
    ).toBeInTheDocument();
    const cdb = (await screen.findByText("CDB Banco X")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(cdb).getByText("01/08/2026")).toBeInTheDocument();
    expect(within(cdb).getByText("desatualizado")).toBeInTheDocument();
    expect(
      within(cdb).getAllByText(/20\.000,00|20\.150,00/).length,
    ).toBeGreaterThan(0);
    const prev = screen.getByText("Prev XP").closest("tr") as HTMLElement;
    expect(within(prev).getByText("estimado")).toBeInTheDocument();
    expect(
      within(prev).getByText("encerrado em 30/09/2026"),
    ).toBeInTheDocument();
    expect(
      within(prev).queryByRole("button", { name: /Encerrar/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /evolução do saldo/ }),
    ).toBeInTheDocument();
  });

  it("r9_5 builds numeric chart data and skips empty types", () => {
    const data = chartData(REPORT);
    expect(data.evolution[0]).toEqual({
      month: "set/2026",
      balance: 20150,
      contributions: 20000,
    });
    expect(data.byType).toEqual([{ name: "Renda fixa", value: 20150 }]);
  });

  it("shows empty state and report errors", async () => {
    mockApi(
      routes({
        "GET /api/investments": [],
        "GET /api/reports/investments": () =>
          apiError(500, "boom", "Relatório indisponível"),
      }),
    );
    page();
    expect(
      await screen.findByText("Relatório indisponível"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Nenhum investimento cadastrado/),
    ).toBeInTheDocument();
  });

  it("r9_1 creates an investment with type, owners and goal", async () => {
    const { calls } = mockApi(
      routes({
        "POST /api/investments": (body: unknown) => ({
          ...(body as object),
          id: "i1",
        }),
      }),
    );
    page();
    await screen.findByText("CDB Banco X");
    await userEvent.click(
      screen.getByRole("button", { name: "Novo investimento" }),
    );
    const modal = await screen.findByRole("dialog");
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "  ");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Nome: obrigatório"),
    ).toBeInTheDocument();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "Tesouro");
    await userEvent.selectOptions(
      within(modal).getByLabelText(/^Instituição/),
      "acc_x",
    );
    await userEvent.selectOptions(
      within(modal).getByLabelText("Tipo"),
      "emergency_reserve",
    );
    await userEvent.selectOptions(
      within(modal).getByLabelText("Meta de poupança"),
      "g1",
    );
    await userEvent.selectOptions(
      within(modal).getByLabelText("Conta de origem"),
      "acc_x",
    );
    await userEvent.click(within(modal).getByLabelText("Padrão de divisão"));
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() => expect(lastBody(calls, "POST")).toBeDefined());
    expect(calls.find((c) => c.method === "POST")?.path).toBe(
      "/api/investments",
    );
    expect(lastBody(calls, "POST")).toEqual({
      name: "Tesouro",
      institution_id: "acc_x",
      type: "emergency_reserve",
      owners: { split_id: "split_casal" },
      goal_id: "g1",
      account_id: "acc_x",
    });
  });

  it("r9_1 rejects custom owners that do not sum 100", async () => {
    const { calls } = mockApi(routes());
    page();
    await screen.findByText("CDB Banco X");
    await userEvent.click(
      screen.getByRole("button", { name: "Novo investimento" }),
    );
    const modal = await screen.findByRole("dialog");
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "X");
    await userEvent.click(within(modal).getByLabelText("Personalizada"));
    const pct = within(modal).getByLabelText("Percentual 1");
    await userEvent.clear(pct);
    await userEvent.type(pct, "10");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText(/soma precisa ser 100%/),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.click(
      within(modal).getByRole("button", { name: "Cancelar" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("r9_2 registering a balance appends a snapshot and keeps the previous ones", async () => {
    const { calls } = mockApi(
      routes({ "PUT /api/investments/inv_cdb": (b: unknown) => b }),
    );
    page();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Registrar saldo de CDB Banco X",
      }),
    );
    const modal = await screen.findByRole("dialog");
    const date = within(modal).getByLabelText(/^Data/);
    expect(date).toHaveTextContent(todayIso().split("-").reverse().join("/"));
    await pickDate(userEvent, date, "2026-10-31");
    await userEvent.type(within(modal).getByLabelText(/^Saldo na data/), "abc");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Valor inválido"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText(/^Saldo na data/));
    await userEvent.type(
      within(modal).getByLabelText(/^Saldo na data/),
      "20.890,00",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() => expect(lastBody(calls, "PUT")).toBeDefined());
    expect(lastBody(calls, "PUT")).toEqual({
      ...CDB,
      snapshots: [
        { date: "2026-08-01", balance: "20150.00" },
        { date: "2026-10-31", balance: "20890.00" },
      ],
    });
  });

  it("r9_3 registering a withdrawal appends a movement", async () => {
    const { calls } = mockApi(
      routes({ "PUT /api/investments/inv_cdb": (b: unknown) => b }),
    );
    page();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Registrar aporte ou resgate de CDB Banco X",
      }),
    );
    const modal = await screen.findByRole("dialog");
    await userEvent.click(within(modal).getByLabelText("Resgate"));
    await userEvent.type(within(modal).getByLabelText(/^Valor/), "0");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("O valor deve ser positivo"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText(/^Valor/));
    await userEvent.type(within(modal).getByLabelText(/^Valor/), "500");
    const date = within(modal).getByLabelText(/^Data/);
    await pickDate(userEvent, date, "2026-10-05");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() => expect(lastBody(calls, "PUT")).toBeDefined());
    const body = lastBody(calls, "PUT") as typeof CDB;
    expect(body.movements).toHaveLength(2);
    expect(body.movements[1]).toEqual({
      date: "2026-10-05",
      type: "withdrawal",
      amount: "500.00",
      warnings: [],
    });
    expect(body.snapshots).toEqual(CDB.snapshots);
  });

  it("closing sets closed_at and shows API errors", async () => {
    const { calls } = mockApi(
      routes({
        "PUT /api/investments/inv_cdb": () =>
          apiError(422, "validation_error", "Data no futuro"),
      }),
    );
    page();
    await userEvent.click(
      await screen.findByRole("button", { name: "Encerrar CDB Banco X" }),
    );
    const modal = await screen.findByRole("dialog");
    expect(
      within(modal).getByText(/continua no histórico/),
    ).toBeInTheDocument();
    const date = within(modal).getByLabelText(/^Data/);
    await pickDate(userEvent, date, "2026-10-12");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Data no futuro"),
    ).toBeInTheDocument();
    expect(lastBody(calls, "PUT")).toMatchObject({
      id: "inv_cdb",
      closed_at: "2026-10-12",
    });
  });

  it("todayIso pads month and day", () => {
    expect(todayIso(new Date(2026, 0, 5))).toBe("2026-01-05");
  });

  it("r13_15 shows the institution name from accounts or institutions, falling back to legacy text", async () => {
    mockApi(
      routes({
        "GET /api/institutions": [{ id: "ins_xp", name: "XP", type: "broker" }],
        "GET /api/investments": [
          { ...CDB, institution_id: "ins_xp", institution: "velho" },
          { ...PREV, institution_id: "acc_x" },
          {
            ...CDB,
            id: "inv_legacy",
            name: "Legado",
            institution: "Texto antigo",
            institution_id: null,
          },
          {
            ...CDB,
            id: "inv_gone",
            name: "Sumido",
            institution: "Fallback",
            institution_id: "deleted",
          },
        ],
      }),
    );
    page();
    const row = async (name: string) =>
      (await screen.findByText(name)).closest("tr") as HTMLElement;
    expect(within(await row("CDB Banco X")).getByText("XP")).toBeVisible();
    expect(within(await row("Prev XP")).getByText("Conta X")).toBeVisible();
    expect(within(await row("Legado")).getByText("Texto antigo")).toBeVisible();
    expect(within(await row("Sumido")).getByText("Fallback")).toBeVisible();
  });

  it("r13_15 groups accounts and institutions and creates a new institution inline", async () => {
    const institutions: Institution[] = [
      { id: "ins_xp", name: "XP", type: "broker" },
    ];
    const { calls } = mockApi(
      routes({
        "GET /api/institutions": () => institutions,
        "POST /api/institutions": (body: unknown) => {
          const created = { ...(body as Institution), id: "ins_new" };
          institutions.push(created);
          return created;
        },
        "POST /api/investments": (body: unknown) => ({
          ...(body as object),
          id: "i1",
        }),
      }),
    );
    page();
    await screen.findByText("CDB Banco X");
    await userEvent.click(
      screen.getByRole("button", { name: "Novo investimento" }),
    );
    const modal = await screen.findByRole("dialog");
    const select = within(modal).getByLabelText(/^Instituição/);
    const groups = within(select)
      .getAllByRole("group")
      .map((g) => g.getAttribute("label"));
    expect(groups).toEqual(["Contas", "Instituições"]);
    expect(
      within(select).getByRole("option", { name: "+ nova instituição" }),
    ).toBeInTheDocument();

    await userEvent.selectOptions(select, "__new__");
    const inline = within(modal).getByRole("group", {
      name: "Nova instituição",
    });
    // Empty name is rejected without a request.
    await userEvent.click(
      within(inline).getByRole("button", { name: "Criar instituição" }),
    );
    expect(within(inline).getByRole("alert")).toHaveTextContent(
      "Nome: obrigatório",
    );
    await userEvent.type(
      within(inline).getByLabelText(/^Nome da instituição/),
      "Binance",
    );
    await userEvent.selectOptions(
      within(inline).getByLabelText("Tipo da instituição"),
      "exchange",
    );
    // Enter creates the institution instead of submitting the investment form.
    await userEvent.type(
      within(inline).getByLabelText(/^Nome da instituição/),
      "{Enter}",
    );
    await waitFor(() =>
      expect(
        calls.find((c) => c.method === "POST" && c.path === "/api/institutions")
          ?.body,
      ).toEqual({ name: "Binance", type: "exchange" }),
    );
    expect(
      calls.some((c) => c.path === "/api/investments" && c.method === "POST"),
    ).toBe(false);
    await waitFor(() =>
      expect(
        within(modal).queryByRole("group", { name: "Nova instituição" }),
      ).toBeNull(),
    );
    expect(select).toHaveValue("ins_new");

    await userEvent.type(within(modal).getByLabelText(/^Nome/), "BTC");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(lastBody(calls, "POST")).toMatchObject({
        name: "BTC",
        institution_id: "ins_new",
      }),
    );
  });

  it("r13_15 inline institution form shows API errors and can be cancelled", async () => {
    mockApi(
      routes({
        "GET /api/institutions": [],
        "POST /api/institutions": () =>
          apiError(409, "conflict", "Já existe uma instituição com esse nome"),
      }),
    );
    page();
    await screen.findByText("CDB Banco X");
    await userEvent.click(
      screen.getByRole("button", { name: "Novo investimento" }),
    );
    const modal = await screen.findByRole("dialog");
    const select = within(modal).getByLabelText(/^Instituição/);
    expect(
      within(select)
        .getAllByRole("group")
        .map((g) => g.getAttribute("label")),
    ).toEqual(["Contas"]);
    await userEvent.selectOptions(select, "__new__");
    const inline = within(modal).getByRole("group", {
      name: "Nova instituição",
    });
    await userEvent.type(
      within(inline).getByLabelText(/^Nome da instituição/),
      "XP",
    );
    await userEvent.click(
      within(inline).getByRole("button", { name: "Criar instituição" }),
    );
    expect(
      await within(inline).findByText(
        "Já existe uma instituição com esse nome",
      ),
    ).toBeInTheDocument();
    await userEvent.click(
      within(inline).getByRole("button", { name: "Cancelar" }),
    );
    expect(
      within(modal).queryByRole("group", { name: "Nova instituição" }),
    ).toBeNull();
    expect(select).toHaveValue("");
    // Choosing an account after opening the form closes it too.
    await userEvent.selectOptions(select, "__new__");
    await userEvent.selectOptions(select, "acc_x");
    expect(
      within(modal).queryByRole("group", { name: "Nova instituição" }),
    ).toBeNull();
    expect(select).toHaveValue("acc_x");
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  apiError,
  CATALOG,
  mockApi,
  pickDate,
  pickMonth,
  renderPage,
} from "../../test/utils";
import { CatalogPage } from "./CatalogPage";
import { describeUncategorized } from "./SpendingTabs";

const open = (tab: string) =>
  renderPage(<CatalogPage />, `/cadastros?tab=${tab}`);
const dialog = () => screen.findByRole("dialog");
const save = (modal: HTMLElement) =>
  userEvent.click(within(modal).getByRole("button", { name: "Salvar" }));
const lastBody = (calls: { method: string; body: unknown }[], method: string) =>
  [...calls].reverse().find((c) => c.method === method)?.body;

const SUBSCRIPTION = {
  id: "sub_netflix",
  description: "Netflix",
  amount: "55.90",
  period: "monthly",
  month_of_year: null,
  payment_method: "credit",
  card_id: "card_x",
  account_id: null,
  start_month: "2026-01",
  end_month: null,
  category_id: "cat_lazer",
  allocations: { split_id: "split_casal" },
};

const RECURRING = {
  id: "rec_racao",
  description: "Ração dos gatos",
  match_description: "PETZ",
  estimated_amount: "250.00",
  every: { value: 45, unit: "days" },
  last_date: "2026-09-01",
  payment_method: "credit",
  card_id: "card_x",
  account_id: null,
  category_id: "cat_casa",
  allocations: null,
  active: true,
  skipped_dates: ["2026-07-15"],
  next_date: "2026-10-16",
};

const RULE = {
  id: "rule_uber",
  priority: 10,
  enabled: true,
  when: {
    description_regex: "UBER",
    card_id: "card_x",
    account_id: null,
    category_id: null,
    min_amount: "10.00",
    max_amount: null,
  },
  then: { category_id: "cat_lazer", allocations: { split_id: "split_casal" } },
};

describe("Categories tab", () => {
  it("r1_11 lists categories with budget", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/categories": [
        { id: "cat_casa", name: "Casa", color: "#4C6EF5", budget: "800.00" },
      ],
    });
    open("categorias");
    const row = (await screen.findByText("Casa")).closest("tr") as HTMLElement;
    expect(within(row).getByText(/800,00/)).toBeInTheDocument();
  });

  it("r1_11 creates a category with color and budget", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/categories": (body: unknown) => ({
        ...(body as object),
        id: "cat_new",
      }),
    });
    open("categorias");
    await screen.findByText("Casa");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "Pets");
    const color = within(modal).getByLabelText("Cor");
    await userEvent.clear(color);
    await userEvent.type(color, "azul");
    await save(modal);
    expect(
      await within(modal).findByText(/Cor: use o formato/),
    ).toBeInTheDocument();
    await userEvent.clear(color);
    await userEvent.type(color, "#AA22CC");
    await userEvent.type(
      within(modal).getByLabelText(/Orçamento mensal/),
      "300,5",
    );
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "POST")).toBeDefined());
    expect(lastBody(calls, "POST")).toEqual({
      name: "Pets",
      color: "#AA22CC",
      budget: "300.50",
      description: null,
    });
  });

  it("r14_24 a category explains what goes in it, in the list and in the picker", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/categories": [
        {
          id: "cat_casa",
          name: "Casa",
          color: "#2F9E44",
          budget: null,
          description: "Contas da casa: luz, água",
        },
      ],
    });
    open("categorias");
    expect(
      await screen.findByText("Contas da casa: luz, água"),
    ).toBeInTheDocument();
  });

  it("r1_12 deleting a category in use shows uncategorized count", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "DELETE /api/categories/cat_casa": {
        deleted: "cat_casa",
        uncategorized: { transactions: 3, subscriptions: 1, rules: 2 },
      },
    });
    open("categorias");
    await userEvent.click(
      await screen.findByRole("button", { name: "Excluir Casa" }),
    );
    const modal = await dialog();
    expect(within(modal).getByText(/ficam/)).toHaveTextContent("sem categoria");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Confirmar exclusão" }),
    );
    expect(
      await screen.findByText(
        /Ficaram sem categoria: 3 lançamentos, 1 assinaturas, 2 regras/,
      ),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.method === "DELETE")?.path).toBe(
      "/api/categories/cat_casa",
    );
  });

  it("r1_12 describes a delete that affected nothing", () => {
    expect(describeUncategorized({})).toMatch(/Nenhum item/);
    expect(describeUncategorized(undefined)).toMatch(/Nenhum item/);
    expect(describeUncategorized({ other: 1 })).toMatch(/1 other/);
  });
});

describe("Savings goals tab", () => {
  it("shows empty state, then creates a goal for a user", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/savings-goals": [],
      "POST /api/savings-goals": (body: unknown) => ({
        ...(body as object),
        id: "g1",
      }),
    });
    open("metas");
    expect(
      await screen.findByText("Nenhuma meta cadastrada."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "Reserva");
    await userEvent.type(within(modal).getByLabelText(/^Valor mensal/), "x");
    await save(modal);
    expect(
      await within(modal).findByText("Valor mensal: valor inválido"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText(/^Valor mensal/));
    await userEvent.type(within(modal).getByLabelText(/^Valor mensal/), "1000");
    await userEvent.selectOptions(
      within(modal).getByLabelText("Usuário"),
      "ana",
    );
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "POST")).toBeDefined());
    expect(lastBody(calls, "POST")).toEqual({
      name: "Reserva",
      monthly_amount: "1000.00",
      user_id: "ana",
    });
  });

  it("lists goals with user names", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/savings-goals": [
        { id: "g1", name: "Viagem", monthly_amount: "500.00", user_id: null },
        { id: "g2", name: "Carro", monthly_amount: "200.00", user_id: "ana" },
      ],
    });
    open("metas");
    expect(await screen.findByText("Viagem")).toBeInTheDocument();
    expect(screen.getByText("todos")).toBeInTheDocument();
    expect(screen.getByText("Ana")).toBeInTheDocument();
  });
});

describe("Subscriptions tab", () => {
  it("r14_16 'Padrão' says who the default split is (the card owners)", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/subscriptions": [{ ...SUBSCRIPTION, allocations: null }],
    });
    open("assinaturas");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Netflix" }),
    );
    const modal = await screen.findByRole("dialog");
    expect(
      await within(modal).findByTestId("default-split-hint"),
    ).toHaveTextContent("Padrão = donos do cartão Cartão X — Eu 100%");
  });

  it("r1_4 lists subscriptions", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/subscriptions": [
        SUBSCRIPTION,
        {
          ...SUBSCRIPTION,
          id: "sub_ipva",
          description: "Seguro",
          period: "annual",
          month_of_year: 3,
          payment_method: "pix",
          card_id: null,
          account_id: "acc_x",
          end_month: "2027-12",
          category_id: null,
          allocations: null,
        },
      ],
    });
    open("assinaturas");
    const row = (await screen.findByText("Netflix")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(row).getByText("Crédito · Cartão X")).toBeInTheDocument();
    expect(within(row).getByText("Casal")).toBeInTheDocument();
    expect(within(row).getByText("jan/2026 → sem fim")).toBeInTheDocument();
    const annual = screen.getByText("Seguro").closest("tr") as HTMLElement;
    expect(within(annual).getByText("Anual (março)")).toBeInTheDocument();
    expect(within(annual).getByText("PIX · Conta X")).toBeInTheDocument();
    expect(within(annual).getByText("sem categoria")).toBeInTheDocument();
  });

  it("r1_4 creates an annual subscription paid by account with a category", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/subscriptions": [],
      "POST /api/subscriptions": (body: unknown) => ({
        ...(body as object),
        id: "s1",
      }),
    });
    open("assinaturas");
    await screen.findByText("Nenhuma assinatura cadastrada.");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(
      within(modal).getByLabelText(/^Descrição/),
      "Anuidade",
    );
    await userEvent.type(within(modal).getByLabelText(/^Valor/), "480");
    await userEvent.click(within(modal).getByLabelText("Anual"));
    await userEvent.selectOptions(
      within(modal).getByLabelText("Mês da cobrança"),
      "5",
    );
    await pickMonth(
      userEvent,
      within(modal).getByLabelText(/^Início/),
      "2026-05",
    );
    await pickMonth(userEvent, within(modal).getByLabelText(/^Fim/), "2026-01");
    await userEvent.selectOptions(
      within(modal).getByLabelText("Meio de pagamento"),
      "debit",
    );
    await userEvent.selectOptions(
      within(modal).getByRole("combobox", { name: /^Conta/ }),
      "acc_x",
    );
    await save(modal);
    expect(
      await within(modal).findByText("Fim antes do início"),
    ).toBeInTheDocument();
    await userEvent.click(within(modal).getByLabelText("Limpar Fim"));
    await userEvent.click(
      within(modal).getByRole("textbox", { name: "Categoria" }),
    );
    await userEvent.click(await screen.findByRole("option", { name: "Lazer" }));
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "POST")).toBeDefined());
    expect(lastBody(calls, "POST")).toEqual({
      description: "Anuidade",
      amount: "480.00",
      period: "annual",
      month_of_year: 5,
      payment_method: "debit",
      card_id: null,
      account_id: "acc_x",
      start_month: "2026-05",
      end_month: null,
      category_id: "cat_lazer",
      allocations: null,
      price_history: [],
      pauses: [],
      allocation_history: [],
      group: "subscription",
      due_day: null,
    });
  });

  it("validates a monthly subscription and shows API validation errors", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/subscriptions": [SUBSCRIPTION],
      "PUT /api/subscriptions/sub_netflix": () =>
        apiError(422, "validation_error", "Dados inválidos"),
    });
    open("assinaturas");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Netflix" }),
    );
    const modal = await dialog();
    await pickMonth(
      userEvent,
      within(modal).getByLabelText(/^Início/),
      "2026-02",
    );
    await save(modal);
    expect(
      await within(modal).findByText("Dados inválidos"),
    ).toBeInTheDocument();
    expect(lastBody(calls, "PUT")).toMatchObject({
      id: "sub_netflix",
      amount: "55.90",
      start_month: "2026-02",
      allocations: { split_id: "split_casal" },
    });
  });
});

describe("Recurring purchases tab", () => {
  it("r12_1 lists recurring purchases with interval and next date", async () => {
    mockApi({ ...CATALOG, "GET /api/recurring-purchases": [RECURRING] });
    open("recorrentes");
    const row = (await screen.findByText("Ração dos gatos")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(row).getByText("a cada 45 dias")).toBeInTheDocument();
    expect(within(row).getByText("16/10/2026")).toBeInTheDocument();
    expect(within(row).getByText("ativa")).toBeInTheDocument();
  });

  it("r12_1 creates a recurring purchase", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/recurring-purchases": [],
      "POST /api/recurring-purchases": (body: unknown) => ({
        ...(body as object),
        id: "r1",
      }),
    });
    open("recorrentes");
    await screen.findByText("Nenhum gasto recorrente cadastrado.");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Descrição/), "Ração");
    await userEvent.type(
      within(modal).getByLabelText(/^Valor estimado/),
      "250",
    );
    const every = within(modal).getByLabelText("A cada");
    await userEvent.clear(every);
    await userEvent.type(every, "6");
    await userEvent.selectOptions(
      within(modal).getByLabelText("Unidade"),
      "weeks",
    );
    await userEvent.selectOptions(
      within(modal).getByLabelText(/^Cartão/),
      "card_x",
    );
    await save(modal);
    expect(
      await within(modal).findByText("Última compra: escolha a data"),
    ).toBeInTheDocument();
    await pickDate(
      userEvent,
      within(modal).getByLabelText(/^Data da última compra/),
      "2026-09-01",
    );
    await userEvent.click(
      within(modal).getByRole("switch", { name: /^Ativa/ }),
    );
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "POST")).toBeDefined());
    expect(lastBody(calls, "POST")).toEqual({
      description: "Ração",
      match_description: null,
      estimated_amount: "250.00",
      every: { value: 6, unit: "weeks" },
      last_date: "2026-09-01",
      payment_method: "credit",
      card_id: "card_x",
      account_id: null,
      category_id: null,
      allocations: null,
      active: false,
      price_history: [],
      pauses: [],
      allocation_history: [],
      group: "purchase",
    });
  });

  it("r12_1 editing keeps skipped dates the form does not manage", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/recurring-purchases": [RECURRING],
      "PUT /api/recurring-purchases/rec_racao": (body: unknown) => body,
    });
    open("recorrentes");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Ração dos gatos" }),
    );
    const modal = await dialog();
    expect(within(modal).getByLabelText(/^Valor estimado/)).toHaveValue(
      "250,00",
    );
    await userEvent.click(within(modal).getByLabelText("Personalizada"));
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "PUT")).toBeDefined());
    expect(lastBody(calls, "PUT")).toMatchObject({
      skipped_dates: ["2026-07-15"],
      match_description: "PETZ",
      allocations: [
        { user_id: "eu", pct: "50.00" },
        { user_id: "ana", pct: "50.00" },
      ],
    });
  });
});

describe("Rules tab", () => {
  it("lists rules with conditions and actions", async () => {
    mockApi({ ...CATALOG, "GET /api/rules": [RULE] });
    open("regras");
    expect(
      await screen.findByText(
        "descrição ~ /UBER/ e cartão Cartão X e ≥ R$ 10,00",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("categoria Lazer + divisão Casal"),
    ).toBeInTheDocument();
    expect(screen.getByText("habilitada")).toBeInTheDocument();
  });

  it("creates a rule requiring a category or split in 'then'", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/rules": [],
      "POST /api/rules": (body: unknown) => ({
        ...(body as object),
        id: "rule1",
      }),
    });
    open("regras");
    await screen.findByText("Nenhuma regra cadastrada.");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(
      within(modal).getByLabelText("Descrição (regex)"),
      "IFOOD",
    );
    await userEvent.type(within(modal).getByLabelText("Valor máximo"), "200");
    await save(modal);
    expect(await within(modal).findByText(/Então: defina/)).toBeInTheDocument();
    await userEvent.click(within(modal).getByLabelText("Padrão de divisão"));
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "POST")).toBeDefined());
    expect(lastBody(calls, "POST")).toEqual({
      priority: 100,
      enabled: true,
      when: {
        description_regex: "IFOOD",
        card_id: null,
        account_id: null,
        category_id: null,
        min_amount: null,
        max_amount: "200.00",
      },
      then: { category_id: null, allocations: { split_id: "split_casal" } },
    });
  });

  it("edits a rule and shows invalid_regex from the API", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/rules": [RULE],
      "PUT /api/rules/rule_uber": () =>
        apiError(422, "invalid_regex", "description_regex: unterminated"),
    });
    open("regras");
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Editar regra 10 (rule_uber)",
      }),
    );
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText("Valor mínimo"), "x");
    await save(modal);
    expect(
      await within(modal).findByText("Valor mínimo: valor inválido"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText("Valor mínimo"));
    await userEvent.click(within(modal).getByLabelText("Habilitada"));
    await save(modal);
    expect(
      await within(modal).findByText("description_regex: unterminated"),
    ).toBeInTheDocument();
    expect(lastBody(calls, "PUT")).toMatchObject({
      enabled: false,
      when: { min_amount: null, card_id: "card_x" },
    });
  });
});

describe("recurring purchase help (R14.14)", () => {
  it("r14_14 the last purchase date explains it is a purchase that already happened", async () => {
    mockApi({ ...CATALOG, "GET /api/recurring-purchases": [] });
    open("recorrentes");
    await userEvent.click(await screen.findByRole("button", { name: "Novo" }));
    const modal = await screen.findByRole("dialog");
    expect(
      within(modal).getByText(/A última vez que a compra aconteceu de verdade/),
    ).toBeInTheDocument();
  });
});

describe("gastos recorrentes: próxima data e todo dia X (R14.30)", () => {
  it("r14_30 'Próxima' shows the planned next date, not only a postponed one", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/recurring-purchases": [{ ...RECURRING, next_date: null }],
    });
    open("recorrentes");
    const row = (await screen.findByText("Ração dos gatos")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(row).getByText("16/10/2026")).toBeInTheDocument(); // 01/09 + 45 dias
  });

  it("r14_30 'Todo dia X do mês' saves monthly anchored on that day", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/recurring-purchases": [RECURRING],
      "PUT /api/recurring-purchases/rec_racao": (body: unknown) => body,
    });
    open("recorrentes");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Ração dos gatos" }),
    );
    const modal = await dialog();
    await userEvent.click(within(modal).getByLabelText("Todo dia X do mês"));
    const day = within(modal).getByLabelText(/^Dia do mês/);
    await userEvent.clear(day);
    await userEvent.type(day, "31");
    await save(modal);
    await waitFor(() => expect(lastBody(calls, "PUT")).toBeDefined());
    expect(lastBody(calls, "PUT")).toMatchObject({
      every: { value: 1, unit: "months" },
      last_date: "2026-08-31", // no 31/09: anchored on 31/08 so October is 31/10
    });
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { inUseText } from "../../components/QueryState";
import {
  apiError,
  CATALOG,
  mockApi,
  pickMonth,
  renderPage,
} from "../../test/utils";
import { CatalogPage } from "./CatalogPage";

const open = (tab: string) =>
  renderPage(<CatalogPage />, `/cadastros?tab=${tab}`);
const dialog = () => screen.findByRole("dialog");

describe("CatalogPage tabs", () => {
  it("defaults to users and switches tab via the tab list", async () => {
    mockApi({ ...CATALOG });
    renderPage(<CatalogPage />, "/cadastros?tab=bogus");
    expect(
      await screen.findByRole("heading", { name: "Usuários" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Categorias" }));
    expect(
      await screen.findByRole("heading", { name: "Categorias" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Casa")).toBeInTheDocument();
  });

  it("opens the tab given in the query string", async () => {
    mockApi({ ...CATALOG });
    open("cartoes");
    expect(
      await screen.findByRole("tab", { name: "Cartões", selected: true }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Cartão X")).toBeInTheDocument();
  });
});

describe("Users tab", () => {
  it("r14_4 several named incomes and a one-off income are saved and summarised", async () => {
    const two = {
      id: "eu",
      name: "Eu",
      aliases: [],
      income_history: [],
      benefit_income_history: [],
      collector_user_id: null,
      incomes: [
        {
          name: "Emprego A",
          history: [{ from_month: "2026-01", amount: "6000.00" }],
        },
        {
          name: "Freela",
          history: [{ from_month: "2026-02", amount: "1500.00" }],
        },
      ],
      one_off_incomes: [
        { month: "2026-12", amount: "2000.00", description: "Bônus" },
      ],
    };
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/users": [two],
      "PUT /api/users/eu": (body: unknown) => body,
    });
    open("usuarios");
    expect(
      await screen.findByText(/R\$\s?7\.500,00 \(2 rendas\)/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Editar Eu" }));
    const modal = await dialog();
    expect(within(modal).getByLabelText("Nome da renda 2")).toHaveValue(
      "Freela",
    );
    expect(within(modal).getByLabelText("Descrição (pontual 1)")).toHaveValue(
      "Bônus",
    );
    // a one-off income needs a positive value
    await userEvent.clear(within(modal).getByLabelText("Valor (pontual 1)"));
    await userEvent.type(
      within(modal).getByLabelText("Valor (pontual 1)"),
      "0",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Bônus: valor precisa ser maior que zero"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText("Valor (pontual 1)"));
    await userEvent.type(
      within(modal).getByLabelText("Valor (pontual 1)"),
      "2.500,00",
    );
    // drop the freelance income
    const removes = within(modal).getAllByRole("button", {
      name: "Remover renda",
    });
    await userEvent.click(removes[1]!);
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      income_history: [],
      incomes: [
        {
          name: "Emprego A",
          history: [{ from_month: "2026-01", amount: "6000.00" }],
        },
      ],
      one_off_incomes: [
        { month: "2026-12", amount: "2500.00", description: "Bônus" },
      ],
    });
  });

  it("r1_5 lists users with current income and empty income as dash", async () => {
    mockApi({ ...CATALOG });
    open("usuarios");
    const row = (await screen.findByText("Ana")).closest("tr") as HTMLElement;
    expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/R\$\s?9\.000,00 desde jan\/2026/),
    ).toBeInTheDocument();
  });

  it("shows empty state and API errors", async () => {
    mockApi({ ...CATALOG, "GET /api/users": [] });
    open("usuarios");
    expect(
      await screen.findByText("Nenhum usuário cadastrado."),
    ).toBeInTheDocument();
  });

  it("shows list errors", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/users": () => apiError(500, "boom", "Falhou geral"),
    });
    open("usuarios");
    expect(await screen.findByText("Falhou geral")).toBeInTheDocument();
  });

  it("r1_5 creates a user with optional income history and aliases", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/users": (body: unknown) => ({ ...(body as object), id: "u1" }),
    });
    open("usuarios");
    await screen.findByText("Ana");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "  ");
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Nome: obrigatório"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText(/^Nome/));
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "Mãe");
    await userEvent.type(
      within(modal).getByLabelText("Apelidos"),
      "MARIA{enter}",
    );
    // R14.4: incomes are named sources; a new one starts with one empty vigência.
    await userEvent.click(
      within(modal).getByRole("button", { name: "+ renda" }),
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText(/Renda 1: dê um nome/),
    ).toBeInTheDocument();
    await userEvent.type(
      within(modal).getByLabelText("Nome da renda 1"),
      "Salário",
    );
    await userEvent.type(
      within(modal).getByLabelText("Valor (Salário 1)"),
      "3.500,50",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Salário: escolha o mês"),
    ).toBeInTheDocument();
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (Salário 1)"),
      "2026-03",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    const post = calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/api/users");
    expect(post?.body).toEqual({
      name: "Mãe",
      aliases: ["MARIA"],
      collector_user_id: null,
      income_history: [],
      incomes: [
        {
          name: "Salário",
          history: [{ from_month: "2026-03", amount: "3500.50" }],
        },
      ],
      one_off_incomes: [],
      benefit_income_history: [],
    });
  });

  it("r1_5 edits a user keeping past income entries (PUT)", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "PUT /api/users/eu": (body: unknown) => body,
    });
    open("usuarios");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Eu" }),
    );
    const modal = await dialog();
    expect(within(modal).getByLabelText("Valor (Renda 1)")).toHaveValue(
      "9000,00",
    );
    const income = within(modal).getByRole("group", { name: "Renda" });
    await userEvent.click(
      within(income).getByRole("button", { name: "+ vigência" }),
    );
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (Renda 2)"),
      "2026-01",
    );
    await userEvent.type(
      within(modal).getByLabelText("Valor (Renda 2)"),
      "10000",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Renda: meses repetidos"),
    ).toBeInTheDocument();
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (Renda 2)"),
      "2026-09",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toMatchObject({
      id: "eu",
      // R14.4: the legacy single history is moved into a source named "Renda".
      income_history: [],
      incomes: [
        {
          name: "Renda",
          history: [
            { from_month: "2026-01", amount: "9000.00" },
            { from_month: "2026-09", amount: "10000.00" },
          ],
        },
      ],
    });
  });

  it("shows 409 in_use when deleting a referenced user", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "DELETE /api/users/eu": () =>
        apiError(409, "in_use", "Usuário em uso por cards/card_x"),
    });
    open("usuarios");
    await userEvent.click(
      await screen.findByRole("button", { name: "Excluir Eu" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", { name: "Confirmar exclusão" }),
    );
    expect(
      await within(modal).findByText("Usuário em uso por cards/card_x"),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.method === "DELETE")?.path).toBe(
      "/api/users/eu",
    );
  });

  it("r1_5 409 in_use lists what the user is linked to, by type", async () => {
    mockApi({
      ...CATALOG,
      "DELETE /api/users/eu": () =>
        new Response(
          JSON.stringify({
            error: {
              code: "in_use",
              message: "users/eu is referenced by cards/card_x",
              details: {
                referenced_by: [
                  "accounts/acc_x",
                  "cards/card_x",
                  "cards/card_y",
                  "transactions/tx_1",
                  "annotations/fp1",
                ],
              },
            },
          }),
          { status: 409 },
        ),
    });
    open("usuarios");
    await userEvent.click(
      await screen.findByRole("button", { name: "Excluir Eu" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", { name: "Confirmar exclusão" }),
    );
    expect(await within(modal).findByRole("alert")).toHaveTextContent(
      "Não é possível excluir: está vinculado a 5 itens (1 conta, 2 cartões, 1 lançamento, 1 anotação)",
    );
  });

  it("removes an income row and cancels the modal", async () => {
    mockApi({ ...CATALOG });
    open("usuarios");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Eu" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", { name: "Remover Renda 1" }),
    );
    expect(
      within(modal).queryByLabelText("Valor (Renda 1)"),
    ).not.toBeInTheDocument();
    await userEvent.click(
      within(modal).getByRole("button", { name: "Cancelar" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});

describe("Split profiles tab", () => {
  it("r6_10 lists split profiles with the current version", async () => {
    mockApi({ ...CATALOG });
    open("divisoes");
    expect(await screen.findByText("Casal")).toBeInTheDocument();
    expect(screen.getByText("jan/2026: Eu 60% · Ana 40%")).toBeInTheDocument();
    expect(screen.getByText("Percentual")).toBeInTheDocument();
  });

  it("r6_11 adds a new version from a month and validates the 100% sum", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "PUT /api/split-profiles/split_casal": (body: unknown) => body,
    });
    open("divisoes");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Casal" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", { name: "+ versão" }),
    );
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (versão 2)"),
      "2026-10",
    );
    await userEvent.type(within(modal).getByLabelText("Eu % (versão 2)"), "70");
    await userEvent.type(
      within(modal).getByLabelText("Ana % (versão 2)"),
      "20",
    );
    expect(
      within(modal).getByText(/soma: 90.00% \(precisa ser 100%\)/),
    ).toBeInTheDocument();
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText(/a soma precisa ser 100%/),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await userEvent.clear(within(modal).getByLabelText("Ana % (versão 2)"));
    await userEvent.type(
      within(modal).getByLabelText("Ana % (versão 2)"),
      "30",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      mode: "fixed",
      history: [
        {
          from_month: "2026-01",
          mode: "fixed",
          shares: [
            { user_id: "eu", pct: "60.00" },
            { user_id: "ana", pct: "40.00" },
          ],
        },
        {
          from_month: "2026-10",
          mode: "fixed",
          shares: [
            { user_id: "eu", pct: "70.00" },
            { user_id: "ana", pct: "30.00" },
          ],
        },
      ],
    });
  });

  it("r13_12 each version picks its mode: 70/30, proportional, then 50/50", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/split-profiles": (body: unknown) => ({
        ...(body as object),
        id: "s1",
      }),
    });
    open("divisoes");
    await screen.findByText("Casal");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "Família");
    // v1: 70/30 fixed
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (versão 1)"),
      "2026-01",
    );
    await userEvent.type(within(modal).getByLabelText("Eu % (versão 1)"), "70");
    await userEvent.type(
      within(modal).getByLabelText("Ana % (versão 1)"),
      "30",
    );
    // v2: proportional — percentages hidden, hint shown
    await userEvent.click(
      within(modal).getByRole("button", { name: "+ versão" }),
    );
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (versão 2)"),
      "2026-05",
    );
    const mode2 = within(modal).getByRole("radiogroup", {
      name: "Modo (versão 2)",
    });
    await userEvent.click(within(mode2).getByLabelText("Proporcional à renda"));
    expect(
      within(modal).queryByLabelText("Eu % (versão 2)"),
    ).not.toBeInTheDocument();
    expect(
      within(modal).getByText(/calculado pela renda de cada membro no mês/),
    ).toBeInTheDocument();
    // v3: back to fixed 50/50
    await userEvent.click(
      within(modal).getByRole("button", { name: "+ versão" }),
    );
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (versão 3)"),
      "2026-09",
    );
    await userEvent.type(within(modal).getByLabelText("Eu % (versão 3)"), "50");
    await userEvent.type(
      within(modal).getByLabelText("Ana % (versão 3)"),
      "50",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Família",
      members: ["eu", "ana"],
      mode: "fixed",
      history: [
        {
          from_month: "2026-01",
          mode: "fixed",
          shares: [
            { user_id: "eu", pct: "70.00" },
            { user_id: "ana", pct: "30.00" },
          ],
        },
        { from_month: "2026-05", mode: "income_proportional", shares: [] },
        {
          from_month: "2026-09",
          mode: "fixed",
          shares: [
            { user_id: "eu", pct: "50.00" },
            { user_id: "ana", pct: "50.00" },
          ],
        },
      ],
    });
  });

  it("r13_12 legacy proportional profiles load as proportional versions", async () => {
    const legacy = {
      id: "split_prop",
      name: "Pela renda",
      members: ["eu", "ana"],
      mode: "income_proportional",
      history: [
        {
          from_month: "2026-01",
          shares: [
            { user_id: "eu", pct: "50.00" },
            { user_id: "ana", pct: "50.00" },
          ],
        },
        {
          from_month: "2026-06",
          mode: "fixed",
          shares: [
            { user_id: "eu", pct: "80.00" },
            { user_id: "ana", pct: "20.00" },
          ],
        },
      ],
    };
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/split-profiles": [legacy],
      "PUT /api/split-profiles/split_prop": (body: unknown) => body,
    });
    open("divisoes");
    // Current version is the fixed one from jun/2026.
    expect(
      await screen.findByText("jun/2026: Eu 80% · Ana 20%"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Editar Pela renda" }),
    );
    const modal = await dialog();
    expect(
      within(modal).queryByLabelText("Eu % (versão 1)"),
    ).not.toBeInTheDocument();
    expect(within(modal).getByLabelText("Eu % (versão 2)")).toHaveValue(
      "80,00",
    );
    expect(
      within(modal).queryByText(/Nenhuma versão em percentual/),
    ).not.toBeInTheDocument();
    // Removing the only fixed version warns that there is no fallback.
    await userEvent.click(
      within(modal).getByRole("button", { name: "Remover Versões 2" }),
    );
    expect(
      within(modal).getByText(/Nenhuma versão em percentual/),
    ).toBeInTheDocument();
    await userEvent.click(
      within(modal).getByRole("button", { name: "+ versão" }),
    );
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (versão 2)"),
      "2026-06",
    );
    await userEvent.type(within(modal).getByLabelText("Eu % (versão 2)"), "80");
    await userEvent.type(
      within(modal).getByLabelText("Ana % (versão 2)"),
      "20",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      history: [
        { from_month: "2026-01", mode: "income_proportional", shares: [] },
        { from_month: "2026-06", mode: "fixed" },
      ],
    });
  });

  it("r13_12 lists a proportional current version without percentages", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/split-profiles": [
        {
          id: "p",
          name: "Renda",
          members: ["eu", "ana"],
          mode: "fixed",
          history: [
            { from_month: "2026-02", mode: "income_proportional", shares: [] },
          ],
        },
      ],
    });
    open("divisoes");
    expect(
      await screen.findByText("fev/2026: proporcional à renda"),
    ).toBeInTheDocument();
    expect(screen.getByText("Proporcional à renda")).toBeInTheDocument();
  });

  it("validates members, versions and duplicated months", async () => {
    mockApi({ ...CATALOG });
    open("divisoes");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Casal" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", { name: "+ versão" }),
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Versão: escolha o mês"),
    ).toBeInTheDocument();
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (versão 2)"),
      "2026-01",
    );
    await userEvent.type(
      within(modal).getByLabelText("Eu % (versão 2)"),
      "100",
    );
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Versões com o mesmo mês"),
    ).toBeInTheDocument();
    await userEvent.click(within(modal).getByRole("checkbox", { name: "Eu" }));
    await userEvent.click(within(modal).getByRole("checkbox", { name: "Ana" }));
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    expect(
      await within(modal).findByText("Escolha ao menos um membro"),
    ).toBeInTheDocument();
  });
});

describe("Users — collector (R13.11)", () => {
  it("r13_11 sets 'Repassar o que deve para' to another user and lists it", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "PUT /api/users/ana": (body: unknown) => body,
    });
    open("usuarios");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Ana" }),
    );
    const modal = await dialog();
    const select = within(modal).getByRole("textbox", {
      name: "Repassar o que deve para",
    });
    await userEvent.click(select);
    // The user being edited is not an option.
    expect(
      screen.queryByRole("option", { name: "Ana" }),
    ).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("option", { name: "Eu" }));
    await userEvent.click(
      within(modal).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      id: "ana",
      collector_user_id: "eu",
    });
  });

  it("r13_11 shows who each user passes debts to", async () => {
    const users = (CATALOG["GET /api/users"] as object[]).map((u, i) =>
      i === 1 ? { ...u, collector_user_id: "eu" } : u,
    );
    mockApi({ ...CATALOG, "GET /api/users": users });
    open("usuarios");
    const row = (await screen.findByText("Ana")).closest("tr");
    expect(row).not.toBeNull();
    await waitFor(() =>
      expect(within(row as HTMLElement).getByText("Eu")).toBeInTheDocument(),
    );
  });
});

describe("inUseText", () => {
  it("r1_5 uses singular labels, keeps unknown collections and ignores empty lists", () => {
    expect(inUseText(["benefits/b1"])).toBe(
      "Não é possível excluir: está vinculado a 1 item (1 benefício). Remova ou altere esses itens antes.",
    );
    expect(inUseText(["other/x", "other/y"])).toContain("2 itens (2 other)");
    expect(inUseText([])).toBeNull();
    expect(inUseText(undefined)).toBeNull();
  });

  it("r11_5 the user form no longer edits benefit income (moved to Benefícios)", async () => {
    mockApi({ ...CATALOG });
    open("usuarios");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Eu" }),
    );
    const modal = await dialog();
    expect(
      within(modal).queryByRole("group", { name: "Renda em benefício" }),
    ).not.toBeInTheDocument();
    expect(
      within(modal).getByText(/ficam na aba Benefícios/),
    ).toBeInTheDocument();
  });
});

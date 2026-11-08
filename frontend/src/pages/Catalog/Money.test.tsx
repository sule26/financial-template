import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  apiError,
  CATALOG,
  mockApi,
  pickMonth,
  renderPage,
} from "../../test/utils";
import { CatalogPage } from "./CatalogPage";
import { checkCard } from "./MoneyTabs";

const open = (tab: string) =>
  renderPage(<CatalogPage />, `/cadastros?tab=${tab}`);
const dialog = () => screen.findByRole("dialog");
const save = (modal: HTMLElement) =>
  userEvent.click(within(modal).getByRole("button", { name: "Salvar" }));

describe("Accounts tab", () => {
  it("r6_7 lists accounts with owners and responsible", async () => {
    mockApi({ ...CATALOG });
    open("contas");
    const row = (await screen.findByText("Conta X")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(row).getByText("Conta corrente")).toBeInTheDocument();
    expect(within(row).getByText("Eu 100%")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    mockApi({ ...CATALOG, "GET /api/accounts": [] });
    open("contas");
    expect(
      await screen.findByText("Nenhuma conta cadastrada."),
    ).toBeInTheDocument();
  });

  it("r6_8 creates a benefit account with owners, responsible and days", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/accounts": (body: unknown) => ({
        ...(body as object),
        id: "a1",
      }),
    });
    open("contas");
    await screen.findByText("Conta X");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "VR");
    await userEvent.selectOptions(
      within(modal).getByLabelText("Tipo"),
      "benefit",
    );
    await userEvent.type(
      within(modal).getByLabelText("Identificação no extrato"),
      "0001",
    );
    await userEvent.type(
      within(modal).getByLabelText("Confirmar lançamento manual após (dias)"),
      "7",
    );
    await save(modal);
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "VR",
      type: "benefit",
      owners: [{ user_id: "eu", pct: "100.00" }],
      responsible_user_id: "eu",
      responsibles: null,
      profile_id: null,
      account_hint: "0001",
      confirm_manual_after_days: 7,
      renewal_day: null,
    });
  });

  it("r6_7 rejects custom owners that do not sum 100 and shows 422 reference errors", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "PUT /api/accounts/acc_x": () =>
        apiError(
          422,
          "reference_not_found",
          "responsible_user_id: zé does not exist",
        ),
    });
    open("contas");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Conta X" }),
    );
    const modal = await dialog();
    await userEvent.click(within(modal).getByLabelText("Personalizada"));
    const pct = within(modal).getByLabelText("Percentual 1");
    await userEvent.clear(pct);
    await userEvent.type(pct, "30");
    await save(modal);
    expect(
      await within(modal).findByText(/Donos: escolha os donos/),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await userEvent.clear(pct);
    await userEvent.type(pct, "50");
    await save(modal);
    expect(
      await within(modal).findByText("responsible_user_id: zé does not exist"),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      owners: [
        { user_id: "eu", pct: "50.00" },
        { user_id: "ana", pct: "50.00" },
      ],
    });
  });

  it("deletes an account after confirmation", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "DELETE /api/accounts/acc_x": { deleted: "acc_x" },
    });
    open("contas");
    await userEvent.click(
      await screen.findByRole("button", { name: "Excluir Conta X" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", { name: "Confirmar exclusão" }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.method === "DELETE" && c.path === "/api/accounts/acc_x",
        ),
      ).toBe(true),
    );
  });
});

describe("Cards tab", () => {
  it("r1_1 lists cards with digits, billing and limit", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/cards": [
        ...CATALOG["GET /api/cards"],
        {
          id: "card_add",
          name: "Adicional Mãe",
          parent_card_id: "card_x",
          account_id: null,
          owners: null,
          responsible_user_id: null,
          last_digits: [],
          billing_history: [],
          limit: null,
          profile_id: null,
        },
      ],
    });
    open("cartoes");
    const row = (await screen.findByText("Cartão X")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(row).getByText("1234")).toBeInTheDocument();
    expect(
      within(row).getByText("dia 3 / dia 10 (desde jan/2026)"),
    ).toBeInTheDocument();
    expect(within(row).getByText(/5\.000,00/)).toBeInTheDocument();
    const add = screen.getByText("Adicional Mãe").closest("tr") as HTMLElement;
    expect(within(add).getByText("adicional de Cartão X")).toBeInTheDocument();
    expect(within(add).getByText("Eu 100%")).toBeInTheDocument();
    expect(
      within(add).getAllByText("(herdado do cartão Cartão X)"),
    ).toHaveLength(2);
    expect(within(add).getByText("da fatura principal")).toBeInTheDocument();
  });

  it("r1_1 creates a main card with billing history, digits and limit", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/cards": (body: unknown) => ({ ...(body as object), id: "c1" }),
    });
    open("cartoes");
    await screen.findByText("Cartão X");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(within(modal).getByLabelText(/^Nome/), "Nubank");
    await userEvent.type(
      within(modal).getByLabelText("Finais do cartão"),
      "12{enter}",
    );
    await save(modal);
    expect(
      await within(modal).findByText("Vigência: escolha o mês"),
    ).toBeInTheDocument();
    await pickMonth(
      userEvent,
      within(modal).getByLabelText("A partir de (vigência 1)"),
      "2026-01",
    );
    const closing = within(modal).getByLabelText("Fechamento (vigência 1)");
    await userEvent.clear(closing);
    await userEvent.type(closing, "5");
    await save(modal);
    expect(
      await within(modal).findByText(/deve ter exatamente 4 dígitos/),
    ).toBeInTheDocument();
    await userEvent.type(
      within(modal).getByLabelText("Finais do cartão"),
      "{backspace}9876{enter}",
    );
    await userEvent.type(within(modal).getByLabelText("Limite"), "abc");
    await save(modal);
    expect(
      await within(modal).findByText("Limite: valor inválido"),
    ).toBeInTheDocument();
    await userEvent.clear(within(modal).getByLabelText("Limite"));
    await userEvent.type(within(modal).getByLabelText("Limite"), "8.000,00");
    await userEvent.selectOptions(
      within(modal).getByLabelText("Conta vinculada"),
      "acc_x",
    );
    await save(modal);
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Nubank",
      parent_card_id: null,
      account_id: "acc_x",
      owners: null,
      responsible_user_id: null,
      responsibles: null,
      last_digits: ["9876"],
      billing_history: [{ from_month: "2026-01", closing_day: 5, due_day: 10 }],
      limit: "8000.00",
      profile_id: null,
    });
  });

  it("r1_10 creates an additional card with its own owners and no billing", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/cards": (body: unknown) => ({ ...(body as object), id: "c2" }),
    });
    open("cartoes");
    await screen.findByText("Cartão X");
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await userEvent.type(
      within(modal).getByLabelText(/^Nome/),
      "Adicional pais",
    );
    await userEvent.click(
      within(modal).getByLabelText("Adicional (fatura do principal)"),
    );
    // R14.5: choosing "Adicional" drops the billing section (it bills on the main card)
    expect(
      within(modal).queryByRole("group", { name: "Fatura" }),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(
      within(modal).getByLabelText(/^Cartão principal/),
      "card_x",
    );
    await userEvent.click(within(modal).getByLabelText("100% para…"));
    await userEvent.selectOptions(
      within(modal).getByLabelText("Responsável"),
      "ana",
    );
    await save(modal);
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      parent_card_id: "card_x",
      owners: [{ user_id: "eu", pct: "100.00" }],
      responsible_user_id: "ana",
      billing_history: [],
    });
  });

  it("r6_9 edits a card back to inherited owners (Padrão)", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "PUT /api/cards/card_x": (body: unknown) => body,
    });
    open("cartoes");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Cartão X" }),
    );
    const modal = await dialog();
    expect(within(modal).getByLabelText("Limite")).toHaveValue("5000,00");
    await userEvent.click(within(modal).getByLabelText("Padrão"));
    await userEvent.selectOptions(
      within(modal).getByLabelText("Responsável"),
      "",
    );
    await save(modal);
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      id: "card_x",
      owners: null,
      responsible_user_id: null,
      billing_history: [{ from_month: "2026-01", closing_day: 3, due_day: 10 }],
    });
  });

  it("validates main cards without billing", async () => {
    mockApi({ ...CATALOG });
    open("cartoes");
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar Cartão X" }),
    );
    const modal = await dialog();
    await userEvent.click(
      within(modal).getByRole("button", {
        name: "Remover Fechamento e vencimento 1",
      }),
    );
    await save(modal);
    expect(
      await within(modal).findByText(/precisa de ao menos uma vigência/),
    ).toBeInTheDocument();
  });

  it("checkCard covers parent, days and owners rules", () => {
    const base = {
      id: null,
      name: "C",
      additional: false,
      parent_card_id: null,
      account_id: null,
      owners: null,
      responsible_user_id: null,
      responsibles: null,
      last_digits: [],
      billing: [{ from_month: "2026-01", closing_day: 3, due_day: 10 }],
      limit: "",
      profile_id: "",
    };
    expect(checkCard(base)).toBeNull();
    expect(checkCard({ ...base, name: " " })).toBe("Nome: obrigatório");
    expect(checkCard({ ...base, additional: true })).toMatch(
      /Cartão principal/,
    );
    expect(
      checkCard({
        ...base,
        billing: [{ from_month: "2026-01", closing_day: 0, due_day: 10 }],
      }),
    ).toMatch(/entre 1 e 31/);
    expect(
      checkCard({ ...base, owners: [{ user_id: "eu", pct: "50.00" }] }),
    ).toMatch(/100%/);
  });
});

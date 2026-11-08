import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Account, Benefit } from "../../api/types";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { checkBenefit } from "./BenefitsTab";
import { CatalogPage } from "./CatalogPage";

const open = () => renderPage(<CatalogPage />, "/cadastros?tab=beneficios");
const dialog = () => screen.findByRole("dialog");

const VR_ACCOUNT: Account = {
  id: "acc_vr",
  name: "VR",
  type: "benefit",
  owners: [{ user_id: "eu", pct: "100.00" }],
  responsible_user_id: "eu",
  profile_id: null,
  account_hint: null,
  confirm_manual_after_days: null,
};
const ACCOUNTS = [...CATALOG["GET /api/accounts"], VR_ACCOUNT];

const BENEFIT: Benefit = {
  id: "ben_vr",
  name: "VR",
  user_id: "eu",
  destination: "card",
  account_id: "acc_vr",
  amount_history: [{ from_month: "2026-01", amount: "800.00" }],
  active: true,
};

describe("Benefits tab", () => {
  it("r11_5 lists benefits with destination, account and current amount", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/benefits": [
        BENEFIT,
        { ...BENEFIT, id: "b2", name: "VA", active: false },
      ],
    });
    open();
    expect(
      await screen.findByRole("tab", { name: "Benefícios", selected: true }),
    ).toBeInTheDocument();
    const row = (await screen.findByText("VA")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Cartão de benefício")).toBeInTheDocument();
    expect(
      within(row).getByText("R$ 800,00 desde jan/2026"),
    ).toBeInTheDocument();
    expect(within(row).getByText("Não")).toBeInTheDocument();
  });

  it("r11_5 creates VR on the benefit card with the right body", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/benefits": [],
      "POST /api/benefits": (body: unknown) => ({
        id: "ben_1",
        ...(body as object),
      }),
    });
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await user.type(within(modal).getByLabelText(/^Nome/), "VR");
    // Only benefit-type accounts are offered for the card destination.
    const select = within(modal).getByRole("combobox", {
      name: /^Cartão de benefício/,
    });
    const options = within(select)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["VR"]);
    await user.type(
      within(modal).getByLabelText("Valor mensal (vigência 1)"),
      "850,50",
    );
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "VR",
      user_id: "eu",
      destination: "card",
      account_id: "acc_vr",
      amount_history: [{ from_month: "2026-10", amount: "850.50" }],
      active: true,
    });
  });

  it("r11_5 creates home-office allowance in the checking account (filtered by type)", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/benefits": [],
      "POST /api/benefits": (body: unknown) => ({
        id: "ben_2",
        ...(body as object),
      }),
    });
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Novo" }));
    const modal = await dialog();
    await user.type(
      within(modal).getByLabelText(/^Nome/),
      "Auxílio home office",
    );
    await user.click(within(modal).getByText("Na conta"));
    const select = within(modal).getByRole("combobox", {
      name: /^Conta corrente/,
    });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Conta X"]);
    expect(within(modal).getByText(/soma na renda do mês/)).toBeInTheDocument();
    await user.click(within(modal).getByRole("switch", { name: "Ativo" }));
    await user.click(within(modal).getByRole("switch", { name: "Ativo" }));
    await user.type(
      within(modal).getByLabelText("Valor mensal (vigência 1)"),
      "150",
    );
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Auxílio home office",
      user_id: "eu",
      destination: "account",
      account_id: "acc_x",
      amount_history: [{ from_month: "2026-10", amount: "150.00" }],
      active: true,
    });
  });

  it("r11_5 hints to create the benefit card account and validates the form", async () => {
    const { calls } = mockApi({ ...CATALOG, "GET /api/benefits": [] });
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Novo" }));
    const modal = await dialog();
    expect(
      within(modal).getByText(/crie a conta do cartão de benefício em Contas/),
    ).toBeInTheDocument();
    await user.type(within(modal).getByLabelText(/^Nome/), "VR");
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    expect(
      await within(modal).findByText("Escolha o cartão de benefício"),
    ).toBeInTheDocument();
    await user.click(within(modal).getByText("Na conta"));
    await user.click(
      within(modal).getByRole("button", { name: "Remover Valor mensal 1" }),
    );
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    expect(
      await within(modal).findByText(/adicione ao menos uma vigência/),
    ).toBeInTheDocument();
    await user.click(within(modal).getByRole("button", { name: "+ vigência" }));
    await user.type(
      within(modal).getByLabelText("Valor mensal (vigência 1)"),
      "1",
    );
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    expect(await within(modal).findByText(/escolha o mês/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("r11_5 edits a benefit keeping its id (PUT) and asks for the person", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/accounts": ACCOUNTS,
      "GET /api/benefits": [BENEFIT],
      "PUT /api/benefits/ben_vr": (body: unknown) => body,
    });
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Editar VR" }));
    const modal = await dialog();
    expect(
      within(modal).getByLabelText("Valor mensal (vigência 1)"),
    ).toHaveValue("800,00");
    await user.click(within(modal).getByRole("switch", { name: "Ativo" }));
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      id: "ben_vr",
      active: false,
      account_id: "acc_vr",
    });
  });
});

describe("Accounts tab benefit hint", () => {
  it("r11_5 labels benefit accounts as benefit cards (VR/VA)", async () => {
    mockApi({ ...CATALOG, "GET /api/accounts": ACCOUNTS });
    const user = userEvent.setup();
    renderPage(<CatalogPage />, "/cadastros?tab=contas");
    const row = (await screen.findByText("VR")).closest("tr") as HTMLElement;
    expect(
      within(row).getByText("cartão de benefício (VR/VA)"),
    ).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Editar VR" }));
    const modal = await dialog();
    expect(
      within(modal).getByText(/cartão de benefício \(VR\/VA\): o valor mensal/),
    ).toBeInTheDocument();
  });
});

describe("checkBenefit", () => {
  it("r11_5 requires name, person and account", () => {
    const base = {
      name: "VR",
      user_id: "eu",
      destination: "account" as const,
      account_id: "acc_x",
      amounts: [{ from_month: "2026-10", amount: "10" }],
      active: true,
    };
    expect(checkBenefit({ ...base, name: " " })).toBe("Nome: obrigatório");
    expect(checkBenefit({ ...base, user_id: null })).toBe(
      "Pessoa: obrigatória",
    );
    expect(checkBenefit({ ...base, account_id: null })).toBe("Escolha a conta");
    expect(checkBenefit(base)).toBeNull();
  });
});

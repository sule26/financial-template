import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Account, Benefit, Card } from "../../api/types";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { CatalogPage } from "./CatalogPage";
import { describeInherited, resolveCardOwnership } from "./cardInheritance";

const open = (tab: string) =>
  renderPage(<CatalogPage />, `/cadastros?tab=${tab}`);

const JOAO = {
  id: "u1",
  name: "João Pedro",
  aliases: [],
  income_history: [],
  benefit_income_history: [],
};

const INTER_ACCOUNT: Account = {
  id: "acc_inter",
  name: "Inter",
  type: "checking",
  owners: [{ user_id: "u1", pct: "100.00" }],
  responsible_user_id: "u1",
  profile_id: null,
  account_hint: null,
  confirm_manual_after_days: null,
};

const card = (over: Partial<Card>): Card => ({
  id: "card_inter",
  name: "Inter",
  parent_card_id: null,
  account_id: "acc_inter",
  owners: null,
  responsible_user_id: null,
  last_digits: [],
  billing_history: [{ from_month: "2026-01", closing_day: 1, due_day: 8 }],
  limit: null,
  profile_id: null,
  ...over,
});

const rowOf = async (text: string) => {
  const hits = await screen.findAllByText(text);
  const row = hits.map((el) => el.closest("tbody tr")).find(Boolean);
  if (!row) throw new Error(`no table row with "${text}"`);
  return row as HTMLElement;
};

describe("Cards tab: inherited owners and responsible", () => {
  it("r1_10 shows the owners inherited from the linked account (operator case)", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/users": [JOAO],
      "GET /api/accounts": [INTER_ACCOUNT],
      "GET /api/cards": [card({})],
    });
    open("cartoes");
    const row = await rowOf("João Pedro 100%");
    const [, , owners, responsible] = within(row).getAllByRole("cell") as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ];
    expect(within(owners).getByText("João Pedro 100%")).toBeInTheDocument();
    expect(
      within(owners).getByText("(herdado da conta Inter)"),
    ).toBeInTheDocument();
    expect(within(row).queryByText("herda")).not.toBeInTheDocument();
    expect(within(responsible).getByText("João Pedro")).toBeInTheDocument();
    expect(
      within(responsible).getByText("(herdado da conta Inter)"),
    ).toBeInTheDocument();
  });

  it("r1_10 additional card inherits from the main card; split profile shows its name", async () => {
    const joint: Account = {
      ...INTER_ACCOUNT,
      id: "acc_joint",
      name: "Conjunta",
      owners: { split_id: "split_casal" },
    };
    mockApi({
      ...CATALOG,
      "GET /api/accounts": [joint],
      "GET /api/cards": [
        card({
          id: "card_main",
          name: "Nubank",
          account_id: null,
          owners: [{ user_id: "eu", pct: "100.00" }],
          responsible_user_id: "eu",
        }),
        card({
          id: "card_add",
          name: "Adicional Ana",
          parent_card_id: "card_main",
          account_id: null,
          billing_history: [],
        }),
        card({ id: "card_joint", name: "Itaú", account_id: "acc_joint" }),
        card({ id: "card_orphan", name: "Solto", account_id: null }),
      ],
    });
    open("cartoes");
    const add = await rowOf("Adicional Ana");
    expect(within(add).getByText("Eu 100%")).toBeInTheDocument();
    expect(within(add).getAllByText("(herdado do cartão Nubank)")).toHaveLength(
      2,
    );
    const joint_row = await rowOf("Itaú");
    expect(within(joint_row).getByText("Casal")).toBeInTheDocument();
    expect(
      within(joint_row).getAllByText("(herdado da conta Conjunta)"),
    ).toHaveLength(2);
    const orphan = await rowOf("Solto");
    expect(
      within(orphan).getByText("sem dono (configure)"),
    ).toBeInTheDocument();
    expect(
      within(orphan).getByText("sem responsável (configure)"),
    ).toBeInTheDocument();
    const main = await rowOf("Nubank");
    expect(within(main).queryByText(/herdado/)).not.toBeInTheDocument();
  });
});

describe("resolveCardOwnership", () => {
  it("r1_10 additional card without own account uses the main card's account", () => {
    const main = card({ id: "m", name: "Principal" });
    const add = card({
      id: "a",
      parent_card_id: "m",
      account_id: null,
      billing_history: [],
    });
    const r = resolveCardOwnership(add, [main, add], [INTER_ACCOUNT]);
    expect(r.owners.value).toEqual(INTER_ACCOUNT.owners);
    expect(r.owners.from).toEqual({ kind: "account", name: "Inter" });
    expect(r.responsible).toEqual({
      value: "u1",
      from: { kind: "account", name: "Inter" },
    });
  });

  it("r1_10 own values win and unknown links resolve to nothing", () => {
    const own = card({
      owners: [{ user_id: "eu", pct: "100.00" }],
      responsible_user_id: "eu",
    });
    expect(resolveCardOwnership(own, [], [])).toEqual({
      owners: { value: own.owners, from: null },
      responsible: { value: "eu", from: null },
      responsibles: null,
    });
    const lost = card({ parent_card_id: "nope", account_id: "nope" });
    expect(resolveCardOwnership(lost, [], [])).toEqual({
      owners: { value: null, from: null },
      responsible: { value: null, from: null },
      responsibles: null,
    });
    expect(describeInherited({ kind: "card", name: "X" })).toBe(
      "herdado do cartão X",
    );
  });
});

// ---------------------------------------------------------------- R13.17

const VR: Account = {
  ...INTER_ACCOUNT,
  id: "acc_vr",
  name: "VR",
  type: "benefit",
  owners: [{ user_id: "eu", pct: "100.00" }],
  responsible_user_id: "eu",
  renewal_day: 5,
};

describe("R13.17 benefit card renewal day", () => {
  it("r13_17 accounts table shows the renewal day of benefit accounts", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/accounts": [...CATALOG["GET /api/accounts"], VR],
    });
    open("contas");
    const row = await rowOf("VR");
    expect(within(row).getByText("renova dia 5")).toBeInTheDocument();
    const other = await rowOf("Conta X");
    expect(within(other).queryByText(/renova dia/)).not.toBeInTheDocument();
  });

  it("r13_17 account form asks the renewal day only for benefit and sends it", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "POST /api/accounts": (body: unknown) => ({
        id: "acc_new",
        ...(body as object),
      }),
    });
    const user = userEvent.setup();
    open("contas");
    await user.click(await screen.findByRole("button", { name: "Novo" }));
    const modal = await screen.findByRole("dialog");
    expect(
      within(modal).queryByLabelText(/Dia de renovação/),
    ).not.toBeInTheDocument();
    await user.type(within(modal).getByLabelText(/^Nome/), "VA");
    await user.selectOptions(
      within(modal).getByRole("combobox", { name: "Tipo" }),
      "benefit",
    );
    expect(
      within(modal).getByLabelText(/Responsável \(titular do benefício\)/),
    ).toBeInTheDocument();
    const day = within(modal).getByLabelText(/Dia de renovação/);
    await user.type(day, "7");
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST")).toBe(true),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      name: "VA",
      type: "benefit",
      renewal_day: 7,
    });
  });

  it("r13_17 switching a benefit account to checking drops the renewal day", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/accounts": [VR],
      "PUT /api/accounts/acc_vr": (body: unknown) => body,
    });
    const user = userEvent.setup();
    open("contas");
    await user.click(await screen.findByRole("button", { name: "Editar VR" }));
    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByLabelText(/Dia de renovação/)).toHaveValue("5");
    await user.selectOptions(
      within(modal).getByRole("combobox", { name: "Tipo" }),
      "checking",
    );
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PUT")).toBe(true),
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      type: "checking",
      renewal_day: null,
    });
  });

  it("r13_17 cards tab points benefit cards to Contas", async () => {
    mockApi(CATALOG);
    open("cartoes");
    const link = await screen.findByRole("link", { name: "Contas" });
    const note = link.closest('[role="alert"]') as HTMLElement;
    expect(note).toHaveTextContent(
      "Cartão de benefício (VR/VA)? Cadastre em Contas com tipo Benefício — ele não tem fechamento nem vencimento, só dia de renovação.",
    );
    expect(link).toHaveAttribute("href", "/cadastros?tab=contas");
  });

  it("r13_17 benefits tab shows the renewal day of the chosen benefit card", async () => {
    const benefit: Benefit = {
      id: "ben_vr",
      name: "Vale",
      user_id: "eu",
      destination: "card",
      account_id: "acc_vr",
      amount_history: [{ from_month: "2026-01", amount: "800.00" }],
      active: true,
    };
    const noDay: Account = {
      ...VR,
      id: "acc_va",
      name: "VA",
      renewal_day: null,
    };
    mockApi({
      ...CATALOG,
      "GET /api/accounts": [...CATALOG["GET /api/accounts"], VR, noDay],
      "GET /api/benefits": [benefit],
    });
    const user = userEvent.setup();
    open("beneficios");
    const row = await rowOf("Vale");
    expect(within(row).getByText("VR · renova dia 5")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Editar Vale" }));
    const modal = await screen.findByRole("dialog");
    expect(
      within(modal).getByText(/Renova dia 5: o crédito do benefício cai/),
    ).toBeInTheDocument();
    await user.selectOptions(
      within(modal).getByRole("combobox", { name: /^Cartão de benefício/ }),
      "acc_va",
    );
    expect(
      within(modal).getByText(/Dia de renovação não informado/),
    ).toBeInTheDocument();
  });
});

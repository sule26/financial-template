import type { Account, Card } from "../api/types";
import { labeled, ownerLabels } from "./ownerLabel";

const card = (over: Partial<Card>): Card => ({
  id: "card_x",
  name: "X",
  parent_card_id: null,
  account_id: null,
  owners: null,
  responsible_user_id: null,
  last_digits: [],
  billing_history: [],
  limit: null,
  profile_id: null,
  ...over,
});

const account = (over: Partial<Account>): Account => ({
  id: "acc_x",
  name: "X",
  type: "checking",
  owners: [{ user_id: "eu", pct: "100.00" }],
  responsible_user_id: "eu",
  profile_id: null,
  account_hint: null,
  confirm_manual_after_days: null,
  ...over,
});

describe("ownerLabels (R14.3)", () => {
  it("r14_3 keeps unique names as they are", () => {
    const labels = ownerLabels(
      [card({ id: "card_nu", name: "Nubank", last_digits: ["4321"] })],
      [account({ id: "acc_vr", name: "VR", type: "benefit" })],
    );
    expect(labels).toEqual({ card_nu: "Nubank", acc_vr: "VR" });
  });

  it("r14_3 tells apart card, additional and account with the same name", () => {
    const labels = ownerLabels(
      [
        card({ id: "card_inter", name: "Inter", last_digits: ["1234"] }),
        card({
          id: "card_add",
          name: "inter ", // same name ignoring case and spaces
          parent_card_id: "card_inter",
          last_digits: ["5678", "9999"],
        }),
      ],
      [account({ id: "acc_inter", name: "Inter" })],
    );
    expect(labels).toEqual({
      card_inter: "Inter (cartão ••1234)",
      card_add: "inter (adicional ••5678)",
      acc_inter: "Inter (conta)",
    });
  });

  it("r14_3 names the account kind and copes with cards without finals", () => {
    const labels = ownerLabels(
      [card({ id: "card_c", name: "Caixa" })],
      [
        account({ id: "acc_b", name: "Caixa", type: "benefit" }),
        account({ id: "acc_d", name: "Caixa", type: "cash" }),
      ],
    );
    expect(labels).toEqual({
      card_c: "Caixa (cartão)",
      acc_b: "Caixa (benefício)",
      acc_d: "Caixa (dinheiro)",
    });
  });

  it("r14_3 labeled() swaps names for select rows and keeps unknown ids", () => {
    const rows = [
      { id: "a", name: "A" },
      { id: "b", name: "B" },
    ];
    expect(labeled(rows, { a: "A (conta)" })).toEqual([
      { id: "a", name: "A (conta)" },
      { id: "b", name: "B" },
    ]);
  });
});

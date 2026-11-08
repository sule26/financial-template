/**
 * R14.3: unambiguous labels for cards and accounts.
 *
 * A name that is unique among all cards and accounts stays as is ("Nubank"). When two or more
 * share a name (the Inter card, its additional and the Inter account), each gets what tells it
 * apart: "Inter (cartão ••1234)", "Inter (adicional ••5678)", "Inter (conta)".
 */
import type { Account, AccountType, Card } from "../api/types";

const ACCOUNT_KIND: Record<AccountType, string> = {
  checking: "conta",
  benefit: "benefício",
  cash: "dinheiro",
};

const key = (name: string) => name.trim().toLocaleLowerCase("pt-BR");

function digits(card: Card): string {
  const first = card.last_digits[0];
  return first ? ` ••${first}` : "";
}

export function ownerLabels(
  cards: readonly Card[],
  accounts: readonly Account[],
): Record<string, string> {
  const count = new Map<string, number>();
  for (const row of [...cards, ...accounts])
    count.set(key(row.name), (count.get(key(row.name)) ?? 0) + 1);
  const repeated = (name: string) => (count.get(key(name)) ?? 0) > 1;
  const out: Record<string, string> = {};
  for (const c of cards) {
    out[c.id] = repeated(c.name)
      ? `${c.name.trim()} (${c.parent_card_id ? "adicional" : "cartão"}${digits(c)})`
      : c.name;
  }
  for (const a of accounts) {
    out[a.id] = repeated(a.name)
      ? `${a.name.trim()} (${ACCOUNT_KIND[a.type] ?? "conta"})`
      : a.name;
  }
  return out;
}

/** Rows for a select, with the unambiguous label as the name. */
export function labeled<T extends { id: string; name: string }>(
  rows: readonly T[],
  labels: Record<string, string>,
): T[] {
  return rows.map((r) => ({ ...r, name: labels[r.id] ?? r.name }));
}

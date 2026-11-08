/** Effective owners/responsible of a card, mirroring the backend resolve_card (docs/08):
 * additional card <- main card <- linked account (the card's own account, else the main's). */
import type { Account, Allocation, Card } from "../../api/types";

/** Where an inherited value comes from; null when the card sets it itself. */
export interface InheritedFrom {
  kind: "card" | "account";
  name: string;
}

export interface Resolved<T> {
  value: T | null;
  from: InheritedFrom | null;
}

export interface CardOwnership {
  owners: Resolved<Allocation>;
  responsible: Resolved<string>;
  /** R14.1: several payers, from the same level as `responsible` (null = only the responsible). */
  responsibles: Allocation | null;
}

type Link = { kind: "card"; item: Card } | { kind: "account"; item: Account };

function chainOf(card: Card, cards: Card[], accounts: Account[]): Link[] {
  const parent = card.parent_card_id
    ? cards.find((c) => c.id === card.parent_card_id)
    : undefined;
  const accountId = card.account_id ?? parent?.account_id ?? null;
  const account = accountId
    ? accounts.find((a) => a.id === accountId)
    : undefined;
  const chain: Link[] = [];
  if (parent) chain.push({ kind: "card", item: parent });
  if (account) chain.push({ kind: "account", item: account });
  return chain;
}

function pick<T>(
  own: T | null,
  chain: Link[],
  get: (link: Link) => T | null,
): Resolved<T> {
  if (own !== null) return { value: own, from: null };
  for (const link of chain) {
    const value = get(link);
    if (value !== null)
      return { value, from: { kind: link.kind, name: link.item.name } };
  }
  return { value: null, from: null };
}

export function resolveCardOwnership(
  card: Card,
  cards: Card[],
  accounts: Account[],
): CardOwnership {
  const chain = chainOf(card, cards, accounts);
  const responsible = pick(
    card.responsible_user_id,
    chain,
    (l) => l.item.responsible_user_id || null,
  );
  // R14.1: responsibles come with the responsible, never mixed across levels.
  const level: Card | Account | undefined =
    card.responsible_user_id !== null
      ? card
      : chain.find((l) => l.item.responsible_user_id)?.item;
  return {
    owners: pick(card.owners, chain, (l) => l.item.owners ?? null),
    responsible,
    responsibles:
      responsible.value === null ? null : (level?.responsibles ?? null),
  };
}

/** "herdado da conta Inter" / "herdado do cartão Nubank". */
export function describeInherited(from: InheritedFrom): string {
  return from.kind === "account"
    ? `herdado da conta ${from.name}`
    : `herdado do cartão ${from.name}`;
}

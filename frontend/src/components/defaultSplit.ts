/**
 * What "Padrão" means for a card/account (R14.16): the effective owners, so the operator sees
 * who the purchase will be split with instead of an opaque "Padrão" (docs/08 precedence:
 * a matching rule still wins over the owners).
 */
import { useList, useNames } from "../api/hooks";
import { resolveCardOwnership } from "../pages/Catalog/cardInheritance";
import { describeAllocation } from "../pages/Catalog/shared";

export function useDefaultSplit(
  cardId: string | null | undefined,
  accountId: string | null | undefined,
): string | null {
  const names = useNames();
  const cards = useList("cards").data ?? [];
  const accounts = useList("accounts").data ?? [];
  if (cardId) {
    const card = cards.find((c) => c.id === cardId);
    if (!card) return null;
    const owners = resolveCardOwnership(card, cards, accounts).owners.value;
    return owners
      ? `donos do cartão ${names.owner(cardId)} — ${describeAllocation(owners, names)}`
      : `o cartão ${names.owner(cardId)} não tem donos: configure em Cadastros → Cartões`;
  }
  if (accountId) {
    const account = accounts.find((a) => a.id === accountId);
    if (!account) return null;
    return `donos da conta ${names.owner(accountId)} — ${describeAllocation(account.owners, names)}`;
  }
  return null;
}

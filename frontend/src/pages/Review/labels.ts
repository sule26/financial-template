/** Human-readable labels for review suggestions, warnings and allocation origins (docs/09). */
import { isSplitRef, type Allocation } from "../../api/types";
import { formatMoney } from "../../lib/format";

export const SUGGESTION_LABELS: Record<string, string> = {
  link_plan: "parcela de plano",
  create_plan: "novo parcelamento",
  choose_plan: "escolher parcelamento",
  bank_anticipation: "antecipação feita pelo banco",
  link_anticipation: "parcelas antecipadas",
  link_anticipation_discount: "desconto da antecipação",
  refund_plan: "estorno de parcelamento",
  match_manual: "casa com lançamento manual",
  choose_manual: "escolher lançamento manual",
  link_recurring: "compra recorrente",
  link_subscription: "assinatura",
  invoice_payment: "pagamento de fatura",
  internal_transfer: "transferência entre contas",
  settlement: "acerto",
  link_investment: "investimento",
  choose_investment: "escolher investimento",
  apply_annotation: "edição anterior reaplicada",
};

export const suggestionLabel = (type: string) =>
  SUGGESTION_LABELS[type] ?? type;

export const isChoice = (type: string) => type.startsWith("choose_");

/** Warnings come as "code" or "code:arg[:arg]" (docs/09). */
export function warningText(
  warning: string,
  resolve: (kind: "plan" | "manual", id: string) => string = (_k, id) => id,
): string {
  const [code, ...args] = warning.split(":");
  switch (code) {
    case "sum_mismatch":
      return `A soma das linhas difere do total do PDF${args[0] ? ` em ${formatMoney(args[0])}` : ""}`;
    case "no_total":
      return "O PDF não tem total para conferir a soma";
    case "unknown_card_hint":
      return `Cartão final ${args[0] ?? "?"} não cadastrado`;
    case "expected_installment_missing":
      return `Parcela ${args[1] ?? "?"} de "${resolve("plan", args[0] ?? "")}" era esperada e não veio`;
    case "unmatched_manual":
      return `Lançamento manual "${resolve("manual", args[0] ?? "")}" não apareceu neste documento`;
    case "anticipation_not_happened":
      return `A antecipação de "${resolve("plan", args[0] ?? "")}" não aconteceu nesta fatura`;
    case "category_missing":
      return "Sem categoria";
    case "header_missing":
      return `Campo do cabeçalho não encontrado: ${args[0] ?? "?"}`;
    default:
      return warning;
  }
}

/** Allocation origin (docs/08 precedence) shown next to the split. */
export function originLabel(origin: string | null): string {
  if (!origin) return "—";
  // R14.6: never show the internal "<kind>:<detail>" code to the operator.
  const exact: Record<string, string> = {
    "owners:card": "donos do cartão",
    "owners:account": "donos da conta",
  };
  if (exact[origin]) return exact[origin];
  const [kind] = origin.split(":");
  const labels: Record<string, string> = {
    manual: "manual",
    rule: "regra",
    plan: "parcelamento",
    subscription: "assinatura",
    recurring: "recorrente",
    card: "cartão",
    account: "conta",
    owners: "donos",
    annotation: "edição anterior",
    default: "padrão",
  };
  return labels[kind ?? ""] ?? "automática";
}

export function allocationText(
  alloc: Allocation | null,
  users: Record<string, string>,
  splits: Record<string, string>,
): string {
  if (alloc === null) return "padrão";
  if (isSplitRef(alloc)) return splits[alloc.split_id] ?? alloc.split_id;
  if (alloc.length === 1)
    return `100% ${users[alloc[0]?.user_id ?? ""] ?? alloc[0]?.user_id ?? ""}`;
  return alloc
    .map((s) => `${users[s.user_id] ?? s.user_id} ${Number(s.pct)}%`)
    .join(" / ");
}

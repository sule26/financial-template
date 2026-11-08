import { Alert } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import { ContentSkeleton } from "./ui/ContentSkeleton";
import { EmptyState } from "./ui/EmptyState";

/** Standard loading (skeleton) / error / empty wrapper for queries. */
export function QueryState({
  isLoading,
  error,
  empty,
  emptyText = "Nada por aqui ainda.",
  emptyIcon,
  emptyAction,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  empty?: boolean;
  emptyText?: string;
  emptyIcon?: ReactNode;
  emptyAction?: ReactNode;
  children: ReactNode;
}) {
  if (isLoading) return <ContentSkeleton />;
  if (error) return <ErrorMessage error={error} />;
  if (empty)
    return (
      <EmptyState title={emptyText} icon={emptyIcon} action={emptyAction} />
    );
  return <>{children}</>;
}

/** Portuguese plural labels for the collections an in_use error may cite. */
const COLLECTION_LABELS: Record<string, [string, string]> = {
  accounts: ["conta", "contas"],
  cards: ["cartão", "cartões"],
  transactions: ["lançamento", "lançamentos"],
  staging: ["item em revisão", "itens em revisão"],
  subscriptions: ["assinatura", "assinaturas"],
  recurring_purchases: ["gasto recorrente", "gastos recorrentes"],
  installment_plans: ["parcelamento", "parcelamentos"],
  investments: ["investimento", "investimentos"],
  settlements: ["acerto", "acertos"],
  savings_goals: ["meta", "metas"],
  benefits: ["benefício", "benefícios"],
  rules: ["regra", "regras"],
  split_profiles: ["padrão de divisão", "padrões de divisão"],
  annotations: ["anotação", "anotações"],
};

/**
 * Readable text for a 409 in_use: "Não é possível excluir: está vinculado a 3 itens
 * (2 cartões, 1 conta)". ``refs`` are "collection/id" strings; null when there are none.
 */
export function inUseText(refs: unknown): string | null {
  if (!Array.isArray(refs) || refs.length === 0) return null;
  const counts = new Map<string, number>();
  for (const ref of refs) {
    const coll = String(ref).split("/")[0] ?? "";
    counts.set(coll, (counts.get(coll) ?? 0) + 1);
  }
  const parts = [...counts].map(([coll, n]) => {
    const [one, many] = COLLECTION_LABELS[coll] ?? [coll, coll];
    return `${n} ${n === 1 ? one : many}`;
  });
  const total = refs.length;
  return `Não é possível excluir: está vinculado a ${total} ${total === 1 ? "item" : "itens"} (${parts.join(", ")}). Remova ou altere esses itens antes.`;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const details = error.details as
      | {
          errors?: { loc: unknown[]; msg: string }[];
          referenced_by?: unknown;
        }
      | undefined;
    if (error.code === "in_use") {
      const text = inUseText(details?.referenced_by);
      if (text) return text;
    }
    const extra = details?.errors
      ?.map((e) => `${e.loc.slice(-1).join(".")}: ${e.msg}`)
      .join("; ");
    return extra ? `${error.message} (${extra})` : error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

export function ErrorMessage({ error }: { error: unknown }) {
  return (
    <Alert
      color="red"
      title="Erro"
      role="alert"
      radius="lg"
      icon={<IconAlertTriangle size={18} stroke={1.8} aria-hidden="true" />}
      className="et-notice"
      data-color="red"
    >
      {errorText(error)}
    </Alert>
  );
}

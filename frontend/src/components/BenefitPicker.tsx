/** R14.32: which benefit (VR, Home office…) of a benefit card pays an entry. */
import { Select, Text } from "@mantine/core";
import { useEffect } from "react";
import { useList } from "../api/hooks";
import type { Benefit } from "../api/types";

/** Benefits credited on the benefit card ``accountId``: the active ones, plus ``keep`` (the
 * one already chosen) even if it was switched off since. */
export function cardBenefits(
  benefits: Benefit[],
  accountId: string | null,
  keep?: string | null,
): Benefit[] {
  if (!accountId) return [];
  return benefits.filter(
    (b) =>
      b.destination === "card" &&
      b.account_id === accountId &&
      (b.active || b.id === keep),
  );
}

/** id -> name of every benefit, for the "Pagamento" columns ("Cartão de benefícios · VR"). */
export function useBenefitNames(): Record<string, string> {
  const benefits = useList("benefits").data ?? [];
  return Object.fromEntries(benefits.map((b) => [b.id, b.name]));
}

/**
 * Always shown for a benefit card: with one benefit and nothing chosen yet it comes chosen;
 * with none it says how to link one (Cadastros → Benefícios, "cai no cartão").
 */
export function BenefitPicker({
  accountId,
  value,
  onChange,
}: {
  accountId: string | null;
  value: string | null;
  onChange: (value: string | null) => void;
}) {
  const list = useList("benefits");
  const choices = cardBenefits(list.data ?? [], accountId, value);
  const only = choices.length === 1 ? choices[0]?.id : undefined;
  useEffect(() => {
    // only fills an empty choice: an existing one is never replaced
    if (only && value === null) onChange(only);
  }, [only, value, onChange]);
  if (!accountId || list.isLoading) return null;
  if (choices.length === 0)
    return (
      <Text size="xs" c="dimmed">
        Este cartão ainda não tem benefícios ligados. Em Cadastros → Benefícios,
        cadastre o VR, VA, Home office… com “cai no cartão” e este cartão para
        escolher qual foi usado.
      </Text>
    );
  return (
    <Select
      label="Qual benefício"
      description={
        choices.length > 1
          ? "Este cartão recebe mais de um benefício: diga qual foi usado"
          : undefined
      }
      placeholder="Não informado"
      clearable={choices.length > 1}
      data={choices.map((b) => ({
        value: b.id,
        label: b.active ? b.name : `${b.name} (desativado)`,
      }))}
      value={value}
      onChange={onChange}
    />
  );
}

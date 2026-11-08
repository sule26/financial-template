import { Group, Paper, Text } from "@mantine/core";

import {
  IconArrowDownRight,
  IconArrowUpRight,
  IconMinus,
} from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Guilloche } from "./Guilloche";
import { MoneyText, type MoneyTone } from "./MoneyText";

export interface StatDelta {
  /** Percent change vs the comparison period (e.g. 12.5 = +12,5%); null = no comparison. */
  pct: number | null;
  /** Text after the number, e.g. "vs set/2026". */
  label: string;
  /** For spending, going up is bad; for income/savings it is good. */
  goodWhen?: "up" | "down";
}

export interface StatCardProps {
  label: string;
  /** Money as a decimal string (count-up + tabular), or any node via ``display``. */
  value?: string | null;
  display?: ReactNode;
  tone?: MoneyTone;
  icon?: ReactNode;
  delta?: StatDelta;
  hint?: ReactNode;
  /** ``note`` = the month banknote (signature element); ``default`` = KPI tile. */
  variant?: "default" | "note";
  /** Serial line printed on the note, e.g. "OUT·2026". */
  serial?: string;
  valueTestId?: string;
  children?: ReactNode;
}

const pctFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

/** Direction text is part of the label, so the delta never relies on colour alone. */
export function deltaText(pct: number): string {
  if (pct === 0) return "estável";
  return `${pct > 0 ? "+" : "−"}${pctFormat.format(Math.abs(pct))}%`;
}

function Delta({ delta }: { delta: StatDelta }) {
  if (delta.pct === null || !Number.isFinite(delta.pct))
    return (
      <Text size="xs" className="et-stat__delta" data-trend="none">
        sem comparação {delta.label}
      </Text>
    );
  const up = delta.pct > 0;
  const flat = delta.pct === 0;
  const good = flat
    ? null
    : (delta.goodWhen ?? "down") === (up ? "up" : "down");
  const Icon = flat ? IconMinus : up ? IconArrowUpRight : IconArrowDownRight;
  return (
    <Group
      gap={4}
      wrap="nowrap"
      className="et-stat__delta"
      data-trend={flat ? "flat" : good ? "good" : "bad"}
    >
      <Icon size={14} stroke={2.2} aria-hidden="true" />
      <Text size="xs" fw={700} component="span" inherit>
        {deltaText(delta.pct)}
      </Text>
      <Text size="xs" component="span" inherit className="et-stat__delta-label">
        {delta.label}
      </Text>
    </Group>
  );
}

/** KPI tile with icon, counted-up value and variation; ``variant="note"`` is the month banknote. */
export function StatCard({
  label,
  value,
  display,
  tone = "auto",
  icon,
  delta,
  hint,
  variant = "default",
  serial,
  valueTestId,
  children,
}: StatCardProps) {
  const note = variant === "note";
  return (
    <Paper
      p={note ? "xl" : "lg"}
      component="section"
      aria-label={label}
      className={["et-stat", "et-lift", note ? "et-note" : ""]
        .filter(Boolean)
        .join(" ")}
      data-variant={variant}
    >
      {note && <Guilloche className="et-note__guilloche" />}
      <div className="et-stat__body">
        {icon && (
          <span
            className={`${note ? "et-note__icon" : "et-icon-chip"} et-stat__icon`}
            aria-hidden="true"
          >
            {icon}
          </span>
        )}
        {/* The value directly follows the label (siblings), so "label → value" reads in order. */}
        <Text className="et-stat__label" size="sm" fw={600}>
          {label}
        </Text>
        <div className={note ? "et-note__value" : "et-stat__value"}>
          {display ?? (
            <MoneyText
              value={value}
              tone={note ? "neutral" : tone}
              animate
              data-testid={valueTestId}
              className="et-display"
            />
          )}
        </div>
        {delta && <Delta delta={delta} />}
        {hint && (
          <Text size="xs" className="et-stat__hint" mt={4}>
            {hint}
          </Text>
        )}
        {note && serial && (
          <Text className="et-note__serial" size="xs" aria-hidden="true">
            {serial}
          </Text>
        )}
        {children}
      </div>
    </Paper>
  );
}

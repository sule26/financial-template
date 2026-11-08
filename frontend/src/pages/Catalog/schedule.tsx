/**
 * Price history (R14.9), paused periods (R14.11) and split history (R14.27) of subscriptions and recurring purchases:
 * drafts, validation, editors and the "now" helpers used by the lists.
 */
import { Stack, Text, TextInput } from "@mantine/core";
import type {
  Allocation,
  Money,
  MonthStr,
  RecurringPurchase,
} from "../../api/types";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { MonthField } from "../../components/ui/MonthField";
import { formatMonth } from "../../hooks/month";
import { formatMoney, parseMoneyInput } from "../../lib/format";
import { checkMoney, EntryList, moneyToInput, MONTH_RE } from "./shared";

export interface PriceEntry {
  from_month: MonthStr;
  amount: Money;
}
export interface Pause {
  from_month: MonthStr;
  until_month: MonthStr | null;
}
export interface PriceDraft {
  from_month: string;
  amount: string;
}
export interface PauseDraft {
  from_month: string;
  until_month: string;
}

export const toPriceDrafts = (rows: PriceEntry[] | undefined): PriceDraft[] =>
  (rows ?? []).map((r) => ({
    from_month: r.from_month,
    amount: moneyToInput(r.amount),
  }));
export const toPrices = (rows: PriceDraft[]): PriceEntry[] =>
  rows.map((r) => ({
    from_month: r.from_month.trim(),
    amount: parseMoneyInput(r.amount) ?? "",
  }));
export const toPauseDrafts = (rows: Pause[] | undefined): PauseDraft[] =>
  (rows ?? []).map((r) => ({
    from_month: r.from_month,
    until_month: r.until_month ?? "",
  }));
export const toPauses = (rows: PauseDraft[]): Pause[] =>
  rows.map((r) => ({
    from_month: r.from_month.trim(),
    until_month: r.until_month.trim() || null,
  }));

export function checkPrices(rows: PriceDraft[]): string | null {
  for (const r of rows) {
    if (!MONTH_RE.test(r.from_month.trim())) return "Reajuste: escolha o mês";
    const bad = checkMoney(r.amount, "Reajuste", true);
    if (bad) return bad;
    if (!(Number(parseMoneyInput(r.amount)) > 0))
      return "Reajuste: valor precisa ser maior que zero";
  }
  const months = rows.map((r) => r.from_month.trim());
  return new Set(months).size === months.length
    ? null
    : "Reajuste: meses repetidos";
}

export function checkPauses(rows: PauseDraft[]): string | null {
  for (const r of rows) {
    if (!MONTH_RE.test(r.from_month.trim()))
      return "Desativada: escolha o mês de início";
    const until = r.until_month.trim();
    if (until && until < r.from_month.trim())
      return "Desativada: o fim é antes do início";
  }
  return null;
}

/** Price in force in ``month``: latest reajuste with ``from_month <= month``, else the base. */
export function priceIn(
  base: Money,
  history: PriceEntry[] | undefined,
  month: MonthStr,
): Money {
  let chosen = base;
  for (const e of [...(history ?? [])].sort((a, b) =>
    a.from_month.localeCompare(b.from_month),
  ))
    if (e.from_month <= month) chosen = e.amount;
  return chosen;
}

export function pausedIn(
  pauses: Pause[] | undefined,
  month: MonthStr,
): boolean {
  return (pauses ?? []).some(
    (p) =>
      p.from_month <= month &&
      (p.until_month === null || month <= p.until_month),
  );
}

/**
 * R14.9/R14.28: the main price is the latest reajuste. In force: "R$ 44,90 (desde jun/2026)";
 * scheduled for later: "R$ 50,00 a partir de jan/2027 (hoje R$ 44,90)".
 */
export function describePrice(
  base: Money,
  history: PriceEntry[] | undefined,
  month: MonthStr,
): string {
  const now = priceIn(base, history, month);
  const sorted = [...(history ?? [])].sort((a, b) =>
    a.from_month.localeCompare(b.from_month),
  );
  const latest = sorted[sorted.length - 1];
  const upcoming = sorted.filter((e) => e.from_month > month);
  const next = upcoming[0];
  if (latest && next) {
    const then =
      upcoming.length > 1
        ? `; ${formatMoney(next.amount)} em ${formatMonth(next.from_month)}`
        : "";
    return `${formatMoney(latest.amount)} a partir de ${formatMonth(latest.from_month)} (hoje ${formatMoney(now)}${then})`;
  }
  return latest
    ? `${formatMoney(now)} (desde ${formatMonth(latest.from_month)})`
    : formatMoney(now);
}

// ---------------------------------------------------------------- split history (R14.27)

export interface AllocationEntry {
  from_month: MonthStr;
  allocations: Allocation | null;
}
export interface AllocationDraft {
  from_month: string;
  allocations: Allocation | null;
}

export const toAllocationDrafts = (
  rows: AllocationEntry[] | undefined,
): AllocationDraft[] => (rows ?? []).map((r) => ({ ...r }));
export const toAllocationHistory = (
  rows: AllocationDraft[],
): AllocationEntry[] =>
  rows.map((r) => ({
    from_month: r.from_month.trim(),
    allocations: r.allocations,
  }));

export function checkAllocationHistory(rows: AllocationDraft[]): string | null {
  for (const r of rows) {
    if (!MONTH_RE.test(r.from_month.trim()))
      return "Mudança de divisão: escolha o mês";
    if (!allocationValid(r.allocations))
      return "Mudança de divisão: a soma precisa ser 100%";
  }
  const months = rows.map((r) => r.from_month.trim());
  return new Set(months).size === months.length
    ? null
    : "Mudança de divisão: meses repetidos";
}

/** Split in force in ``month``: latest change with ``from_month <= month``, else the base. */
export function allocationIn(
  base: Allocation | null,
  history: AllocationEntry[] | undefined,
  month: MonthStr,
): Allocation | null {
  let chosen = base;
  for (const e of [...(history ?? [])].sort((a, b) =>
    a.from_month.localeCompare(b.from_month),
  ))
    if (e.from_month <= month) chosen = e.allocations;
  return chosen;
}

/** "Eu 100%" now, plus the next scheduled change: "Eu 100% → Casal a partir de jan/2027". */
export function describeSplit(
  base: Allocation | null,
  history: AllocationEntry[] | undefined,
  month: MonthStr,
  describe: (a: Allocation | null) => string,
): string {
  const now = describe(allocationIn(base, history, month));
  const next = [...(history ?? [])]
    .filter((e) => e.from_month > month)
    .sort((a, b) => a.from_month.localeCompare(b.from_month))[0];
  return next
    ? `${now} → ${describe(next.allocations)} a partir de ${formatMonth(next.from_month)}`
    : now;
}

export function AllocationHistoryEditor({
  rows,
  onChange,
}: {
  rows: AllocationDraft[];
  onChange: (rows: AllocationDraft[]) => void;
}) {
  return (
    <>
      <EntryList
        label="Mudanças de divisão"
        addLabel="+ mudança de divisão"
        emptyText="A divisão acima vale sempre."
        items={rows}
        onChange={onChange}
        make={() => ({ from_month: "", allocations: null })}
        row={(r, update, i) => (
          <Stack gap={4} style={{ flex: 1 }}>
            <MonthField
              label={`A partir de (mudança ${i + 1})`}
              clearable={false}
              value={r.from_month}
              onChange={(from_month) => update({ from_month })}
            />
            <AllocationPicker
              label={`Nova divisão (mudança ${i + 1})`}
              value={r.allocations}
              onChange={(allocations) => update({ allocations })}
            />
          </Stack>
        )}
      />
      <Text size="xs" c="dimmed">
        Ex.: começou a dividir as contas em janeiro. A divisão acima vale até a
        primeira mudança; cada mudança vale a partir do mês dela. Meses
        anteriores não mudam.
      </Text>
    </>
  );
}

export function PriceHistoryEditor({
  rows,
  onChange,
}: {
  rows: PriceDraft[];
  onChange: (rows: PriceDraft[]) => void;
}) {
  return (
    <>
      <EntryList
        label="Reajustes"
        addLabel="+ reajuste"
        emptyText="Nenhum reajuste."
        items={rows}
        onChange={onChange}
        make={() => ({ from_month: "", amount: "" })}
        row={(r, update, i) => (
          <>
            <MonthField
              label={`A partir de (reajuste ${i + 1})`}
              clearable={false}
              value={r.from_month}
              onChange={(from_month) => update({ from_month })}
            />
            <TextInput
              label={`Novo valor (reajuste ${i + 1})`}
              placeholder="0,00"
              inputMode="decimal"
              value={r.amount}
              onChange={(e) => update({ amount: e.currentTarget.value })}
            />
          </>
        )}
      />
      <Text size="xs" c="dimmed">
        O valor acima vale até o primeiro reajuste; cada reajuste vale a partir
        do mês dele. Meses anteriores não mudam.
      </Text>
    </>
  );
}

export function PausesEditor({
  rows,
  onChange,
}: {
  rows: PauseDraft[];
  onChange: (rows: PauseDraft[]) => void;
}) {
  return (
    <>
      <EntryList
        label="Períodos desativada"
        addLabel="+ período desativada"
        emptyText="Nunca ficou desativada."
        items={rows}
        onChange={onChange}
        make={() => ({ from_month: "", until_month: "" })}
        row={(r, update, i) => (
          <>
            <MonthField
              label={`Desativada de (período ${i + 1})`}
              clearable={false}
              value={r.from_month}
              onChange={(from_month) => update({ from_month })}
            />
            <MonthField
              label={`Até (período ${i + 1})`}
              description="Vazio = ainda desativada"
              value={r.until_month}
              onChange={(until_month) => update({ until_month })}
            />
          </>
        )}
      />
      <Text size="xs" c="dimmed">
        Nesses meses não há cobrança prevista nem aviso de “não ocorreu”.
      </Text>
    </>
  );
}

// ---------------------------------------------------------------- next date (R12, R14.26)

/** ``anchor + k × every`` (months clamp to the month's last day: 31/jan + 1 = 28/fev). */
export function step(
  anchor: string,
  k: number,
  every: RecurringPurchase["every"],
): string {
  const [y, m, d] = anchor.split("-").map(Number) as [number, number, number];
  const { value, unit } = every;
  const date =
    unit === "months"
      ? new Date(Date.UTC(y, m - 1 + k * value, 1))
      : new Date(
          Date.UTC(y, m - 1, d + k * value * (unit === "weeks" ? 7 : 1)),
        );
  if (unit === "months") {
    const last = new Date(
      Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0),
    ).getUTCDate();
    date.setUTCDate(Math.min(d, last));
  }
  return date.toISOString().slice(0, 10);
}

/**
 * Next expected date: explicit ``next_date`` (after postpone) or ``last_date + every``.
 * R14.26: a conta da casa never moves its anchor, so with ``month`` it is the first due date
 * from that month on (not skipped).
 */
export function nextDate(rec: RecurringPurchase, month?: string): string {
  if (rec.next_date) return rec.next_date;
  if (rec.group !== "household" || !month)
    return step(rec.last_date, 1, rec.every);
  for (let k = 1; k < 2000; k++) {
    const date = step(rec.last_date, k, rec.every);
    if (date.slice(0, 7) >= month && !rec.skipped_dates.includes(date))
      return date;
  }
  return step(rec.last_date, 1, rec.every);
}

/**
 * R14.30: anchor for "todo dia X": day X in the month of ``date``, or in the latest earlier month
 * that has day X (31 on 30/09 → 31/08), so later months keep day X (30/09, 31/10…).
 */
export function withDay(date: string, day: number): string {
  let [y, m] = date.split("-").map(Number) as [number, number];
  for (let i = 0; i < 12; i++) {
    if (new Date(Date.UTC(y, m, 0)).getUTCDate() >= day) break;
    m -= 1;
    if (m === 0) [y, m] = [y - 1, 12];
  }
  return `${y}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

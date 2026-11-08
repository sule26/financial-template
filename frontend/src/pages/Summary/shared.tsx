/**
 * Building blocks shared by the report pages (Summary, Projection, Receivables).
 *
 * Money stays a decimal string everywhere except when it is handed to Recharts, which can only plot
 * numbers; labels and tooltips are always rendered from the original string via formatMoney.
 */
import { Select, Switch } from "@mantine/core";
import { CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { useList } from "../../api/hooks";
import type { Commitment } from "../../api/types";
import { ChartTooltip } from "../../components/ui/ChartTooltip";
import { useChartTheme, type ChartTheme } from "../../components/ui/charts";
import { Panel as UiPanel } from "../../components/ui/Panel";
import { StatusBadge, type StatusTone } from "../../components/ui/StatusBadge";
import {
  formatMoney,
  formatPct,
  METHOD_LABELS,
  STATE_LABELS,
} from "../../lib/format";

/** Backend key for "no category" (domain/reports.py UNCATEGORIZED); the summary also sends it. */
export const UNCATEGORIZED_KEY = "__none__";
export const UNCATEGORIZED_LABEL = "Sem categoria";

/** Method groups used by the report filter (R11.4). */
export const METHOD_FILTER_OPTIONS = [
  "credit",
  "benefit",
  "account",
  "cash",
].map((value) => ({ value, label: METHOD_LABELS[value] ?? value }));

/** Build a query string, skipping empty values and ``false`` flags. */
export function buildQuery(
  params: Record<string, string | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (
      value === null ||
      value === undefined ||
      value === "" ||
      value === false
    )
      continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** Plot value only — never used for arithmetic shown to the user. */
export function plotValue(value: string | null | undefined): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** Theme-aware chart colours (R1.14) — the "Cédula" chart palette, see components/ui/charts.ts. */
export function useChartColors(): ChartTheme {
  return useChartTheme();
}

/** Category id -> { name, color } with the "Sem categoria" fallback. */
export function useCategoryInfo() {
  const categories = useList("categories");
  const colors = useChartColors();
  const byId = new Map((categories.data ?? []).map((c) => [c.id, c]));
  return (id: string, uncategorizedKey = UNCATEGORIZED_KEY) => {
    if (id === uncategorizedKey)
      return { name: UNCATEGORIZED_LABEL, color: colors.neutral };
    const cat = byId.get(id);
    return { name: cat?.name ?? id, color: cat?.color ?? colors.neutral };
  };
}

/** The shared titled surface; kept here as a re-export for the report pages. */
export const Panel = UiPanel;

const STATE_TONES: Record<string, StatusTone> = {
  real: "success",
  open: "info",
  projected: "neutral",
  missing: "danger",
};

/** Card/month state badge; "faltando" is filled red so it stands out (R8.9). */
export function StateBadge({ state }: { state: string | undefined }) {
  if (!state) return null;
  return (
    <StatusBadge
      tone={STATE_TONES[state] ?? "neutral"}
      strong={state === "missing"}
    >
      {STATE_LABELS[state] ?? state}
    </StatusBadge>
  );
}

const BAND_LABELS: Record<string, string> = {
  green: "confortável",
  yellow: "atenção",
  red: "alto",
};

const BAND_TONES: Record<string, StatusTone> = {
  green: "success",
  yellow: "warning",
  red: "danger",
};

/** Committed-income ratio with its band; the band also has a text label, not colour only. */
export function BandBadge({
  ratio,
  band,
}: {
  ratio: string | null;
  band: Commitment["band"];
}) {
  if (ratio === null) return <>—</>;
  return (
    <StatusBadge
      tone={band ? (BAND_TONES[band] ?? "neutral") : "neutral"}
      data-band={band ?? "none"}
    >
      {formatPct(ratio)}
      {band ? ` · ${BAND_LABELS[band]}` : ""}
    </StatusBadge>
  );
}

export function PersonSelect({
  value,
  onChange,
  label = "Pessoa",
  allowAll = true,
}: {
  value: string | null;
  onChange: (value: string | null) => void;
  label?: string;
  allowAll?: boolean;
}) {
  const users = useList("users");
  return (
    <Select
      label={label}
      placeholder={allowAll ? "Todos" : "Escolha"}
      data={(users.data ?? []).map((u) => ({ value: u.id, label: u.name }))}
      value={value}
      onChange={onChange}
      clearable={allowAll}
      allowDeselect={allowAll}
      w={200}
    />
  );
}

/** R5.5: unconfirmed (Review) items are hidden by default. */
export function PendingSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <Switch
      label="Incluir não confirmados"
      checked={checked}
      onChange={(e) => onChange(e.currentTarget.checked)}
      mt="lg"
    />
  );
}

export function moneyTooltip(value: unknown): string {
  return formatMoney(
    typeof value === "number" ? value.toFixed(2) : String(value),
  );
}

/** Grid + axes; a plain function (not a component) so Recharts sees the elements directly. */
export function chartAxes(colors: ChartTheme) {
  const tick = { fill: colors.text, fontSize: 12 };
  return (
    <>
      <CartesianGrid
        stroke={colors.grid}
        strokeDasharray="2 6"
        vertical={false}
      />
      <XAxis
        dataKey="label"
        tick={tick}
        tickLine={false}
        axisLine={{ stroke: colors.grid }}
      />
      <YAxis
        tick={tick}
        tickLine={false}
        axisLine={false}
        width={72}
        tickFormatter={compactMoney}
      />
    </>
  );
}

const compact = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Axis label: "R$ 1,2 mil" instead of "1200". */
export function compactMoney(value: number): string {
  return `R$ ${compact.format(value)}`;
}

/** Frosted tooltip + soft cursor, shared by every chart. A function so Recharts sees the element. */
export function chartTooltip(colors: ChartTheme, cursor = true) {
  return (
    <Tooltip
      content={<ChartTooltip />}
      cursor={cursor ? { fill: colors.cursor } : false}
      wrapperStyle={{ outline: "none" }}
    />
  );
}

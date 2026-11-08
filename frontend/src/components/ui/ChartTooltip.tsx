import type { ReactNode } from "react";
import { formatMoney } from "../../lib/format";

/** Subset of the props Recharts passes to a custom ``<Tooltip content>``. */
export interface ChartTooltipProps {
  active?: boolean;
  label?: ReactNode;
  payload?: readonly {
    name?: ReactNode;
    value?: unknown;
    color?: string;
    payload?: { fill?: string; color?: string };
    dataKey?: unknown;
  }[];
}

function money(value: unknown): string {
  return formatMoney(
    typeof value === "number" ? value.toFixed(2) : String(value ?? ""),
  );
}

/** Frosted tooltip shared by every chart: label, coloured dot per series, money in tabular figures. */
export function ChartTooltip({ active, label, payload }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const rows = payload.filter((p) => p.value !== undefined && p.value !== 0);
  if (rows.length === 0) return null;
  return (
    <div className="et-chart-tooltip" role="presentation">
      {label !== undefined && label !== "" && (
        <div className="et-chart-tooltip__label">{label}</div>
      )}
      {rows.map((p, i) => (
        <div
          className="et-chart-tooltip__row"
          key={`${String(p.dataKey ?? p.name)}-${i}`}
        >
          <span
            className="et-chart-tooltip__dot"
            style={{
              background: p.color ?? p.payload?.fill ?? p.payload?.color,
            }}
            aria-hidden="true"
          />
          <span className="et-chart-tooltip__name">{p.name}</span>
          <span className="et-chart-tooltip__value et-num">
            {money(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

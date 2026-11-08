import { Text, type TextProps } from "@mantine/core";
import { formatMoney } from "../../lib/format";
import { useCountUp } from "./motion";

export type MoneyTone = "auto" | "signed" | "neutral" | "positive" | "negative";

export interface MoneyTextProps extends Omit<TextProps, "c"> {
  /** Decimal string from the API (e.g. "1500.00"); null/undefined renders "—". */
  value: string | null | undefined;
  /**
   * ``auto``: only negatives are coloured (spending is positive and must not look "good");
   * ``signed``: negatives carmine, positives jade; ``neutral``: never coloured.
   */
  tone?: MoneyTone;
  /** Count up to the value once (skipped under reduced motion and in tests). */
  animate?: boolean;
  "data-testid"?: string;
}

function toneOf(
  value: number,
  tone: MoneyTone,
): "positive" | "negative" | "neutral" {
  if (tone === "positive" || tone === "negative" || tone === "neutral")
    return tone;
  if (value < 0) return "negative";
  if (tone === "signed" && value > 0) return "positive";
  return "neutral";
}

/** Money with tabular figures and a semantic colour; the final text is always ``formatMoney(value)``. */
export function MoneyText({
  value,
  tone = "auto",
  animate = false,
  className,
  ...rest
}: MoneyTextProps) {
  const n = Number(value);
  const numeric =
    value !== null && value !== undefined && value !== "" && Number.isFinite(n);
  const target = numeric ? n : 0;
  const shown = useCountUp(animate && numeric ? target : NaN);
  const settled = !animate || !numeric || shown === target;
  const text = settled ? formatMoney(value) : formatMoney(shown.toFixed(2));
  return (
    <Text
      component="span"
      inherit={rest.size === undefined && rest.fz === undefined}
      {...rest}
      className={["et-money", "et-num", className].filter(Boolean).join(" ")}
      data-tone={toneOf(target, tone)}
    >
      {text}
    </Text>
  );
}

import { Badge, type BadgeProps, type MantineColor } from "@mantine/core";
import type { ReactNode } from "react";

export type StatusTone =
  | "success"
  | "info"
  | "warning"
  | "danger"
  | "neutral"
  | "accent";

const TONE_COLORS: Record<StatusTone, MantineColor> = {
  success: "jade",
  info: "blue",
  warning: "yellow",
  danger: "red",
  neutral: "gray",
  accent: "brass",
};

/** Mantine colour names used by older call sites, mapped to a tone. */
const COLOR_TONES: Record<string, StatusTone> = {
  green: "success",
  teal: "success",
  jade: "success",
  blue: "info",
  cyan: "info",
  indigo: "info",
  yellow: "warning",
  orange: "warning",
  red: "danger",
  pink: "danger",
  gray: "neutral",
  dark: "neutral",
  brass: "accent",
  grape: "accent",
};

export function toneFromColor(color: string | undefined): StatusTone {
  return (color && COLOR_TONES[color]) || "neutral";
}

export interface StatusBadgeProps
  extends Omit<BadgeProps, "color" | "variant"> {
  tone?: StatusTone;
  /** ``strong`` = filled, for states that must stand out (e.g. "faltando"). */
  strong?: boolean;
  /** Show the leading status dot (default true). The text always carries the meaning. */
  dot?: boolean;
  /** Native tooltip with extra context. */
  title?: string;
  children: ReactNode;
  [dataAttr: `data-${string}`]: string | undefined;
}

/** One badge style for every status in the app: tinted pill, status dot, text label. */
export function StatusBadge({
  tone = "neutral",
  strong = false,
  dot = true,
  children,
  className,
  ...rest
}: StatusBadgeProps) {
  return (
    <Badge
      size="sm"
      radius="xl"
      {...rest}
      color={TONE_COLORS[tone]}
      variant={strong ? "filled" : "light"}
      className={["et-status", className].filter(Boolean).join(" ")}
      data-tone={tone}
      leftSection={
        dot ? <span className="et-status-dot" aria-hidden="true" /> : undefined
      }
      tt="none"
    >
      {children}
    </Badge>
  );
}

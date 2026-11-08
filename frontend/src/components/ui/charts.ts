import { useComputedColorScheme } from "@mantine/core";
import { usePrefersMotion } from "./motion";

/**
 * Chart palette of the "Cédula" system. Same ten hues in both themes: deep tones on light paper,
 * lifted tones on the dark ledger (each ≥3:1 against its surface, WCAG non-text contrast).
 */
export const CHART_PALETTE = {
  light: [
    "#0E6B55",
    "#A9822F",
    "#3C6E9E",
    "#A3485A",
    "#6A5BA8",
    "#4C8A3E",
    "#2C8C99",
    "#B5603A",
    "#7A7F3A",
    "#5B6770",
  ],
  dark: [
    "#4CC3A0",
    "#DDB463",
    "#7FA9D6",
    "#E08497",
    "#A99BE3",
    "#8CC57A",
    "#63C4CF",
    "#E3936D",
    "#C2C77A",
    "#9AA6AE",
  ],
} as const;

const BASE = {
  light: {
    text: "#5E6B66",
    grid: "#E1E7E4",
    spend: "#B4233F",
    income: "#0E6B55",
    neutral: "#87958F",
    cursor: "rgba(14, 107, 85, 0.07)",
  },
  dark: {
    text: "#93A39C",
    grid: "#24302B",
    spend: "#F08196",
    income: "#4CC3A0",
    neutral: "#6C7B75",
    cursor: "rgba(67, 181, 146, 0.08)",
  },
} as const;

export interface ChartTheme {
  text: string;
  grid: string;
  spend: string;
  income: string;
  neutral: string;
  cursor: string;
  series: (index: number) => string;
  /** Spread on every Recharts series: grows in once, never under reduced motion / tests. */
  animation: {
    isAnimationActive: boolean;
    animationDuration: number;
    animationEasing: "ease-out";
  };
}

/** Theme-aware chart colours (R1.14) plus the entrance animation switch. */
export function useChartTheme(): ChartTheme {
  const scheme = useComputedColorScheme("light");
  const animate = usePrefersMotion();
  const key = scheme === "dark" ? "dark" : "light";
  const palette = CHART_PALETTE[key];
  return {
    ...BASE[key],
    series: (index: number) => palette[index % palette.length] as string,
    animation: {
      isAnimationActive: animate,
      animationDuration: 700,
      animationEasing: "ease-out",
    },
  };
}

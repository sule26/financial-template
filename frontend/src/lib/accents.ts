/**
 * Accent colours for R13.10 (Configurações → Cor de destaque).
 *
 * Every palette follows the jade structure the redesign was tuned for: shade 7 is the filled
 * colour (white text) and the light-mode accent text, shade 4 is the dark-mode accent text, shade 2
 * is Mantine's "light" variant text in dark mode and shade 0 is the light-mode tint. The AA checks
 * for all of them live in accents.test.ts.
 */
import type { MantineColorsTuple } from "@mantine/core";

export type AccentId =
  | "jade"
  | "ocean"
  | "iris"
  | "amber"
  | "ruby"
  | "graphite";

export interface Accent {
  id: AccentId;
  /** Portuguese name shown in Configurações. */
  name: string;
  palette: MantineColorsTuple;
}

export const DEFAULT_ACCENT: AccentId = "jade";
export const ACCENT_STORAGE_KEY = "expense-tracker-accent";

export const ACCENTS: Accent[] = [
  {
    id: "jade",
    name: "Esmeralda",
    palette: [
      "#E8F6F1",
      "#CDEBDF",
      "#9FD8C3",
      "#6EC6A7",
      "#43B592",
      "#27A07E",
      "#168A6B",
      "#0E6B55",
      "#0A5544",
      "#063E32",
    ],
  },
  {
    id: "ocean",
    name: "Oceano",
    palette: [
      "#E8F2FB",
      "#CCE2F5",
      "#9DC8EE",
      "#6DADE6",
      "#5CA8EA",
      "#2D80CC",
      "#1C69AF",
      "#13528C",
      "#0E4170",
      "#092E50",
    ],
  },
  {
    id: "iris",
    name: "Violeta",
    palette: [
      "#F2EEFC",
      "#E1D8F8",
      "#C6B5F2",
      "#AC93EC",
      "#AD93F0",
      "#7F5BDB",
      "#6844C4",
      "#5434A3",
      "#422982",
      "#2F1D5E",
    ],
  },
  {
    id: "amber",
    name: "Âmbar",
    palette: [
      "#FDF6E4",
      "#FAEABF",
      "#F5D78E",
      "#F0C45E",
      "#EBB23C",
      "#D3961D",
      "#AD7712",
      "#835A0D",
      "#6A480A",
      "#4D3407",
    ],
  },
  {
    id: "ruby",
    name: "Rubi",
    palette: [
      "#FCEDF0",
      "#F8D5DC",
      "#F2AABA",
      "#EC8198",
      "#EF7F9C",
      "#D8456A",
      "#BF2F55",
      "#9C2142",
      "#7D1A35",
      "#5C1226",
    ],
  },
  {
    id: "graphite",
    name: "Grafite",
    palette: [
      "#F1F3F4",
      "#E1E5E7",
      "#C6CDD1",
      "#A9B3B9",
      "#97A2A9",
      "#77838B",
      "#5D6970",
      "#454F56",
      "#353D43",
      "#23292D",
    ],
  },
];

export const isAccentId = (value: unknown): value is AccentId =>
  ACCENTS.some((a) => a.id === value);

export const accentById = (id: AccentId): Accent =>
  (ACCENTS.find((a) => a.id === id) ?? ACCENTS[0]) as Accent;

/** "#RRGGBB" + alpha -> "rgba(r, g, b, a)". */
export function hexAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** CSS variables the redesign reads for the accent (src/styles/tokens.css), per colour scheme. */
export function accentVariables(accent: Accent): {
  light: Record<string, string>;
  dark: Record<string, string>;
} {
  const p = accent.palette;
  // R14.18: the Resumo banknote and the logo coin follow the accent too.
  const note = { "--et-note-from": p[8], "--et-note-to": p[9] };
  return {
    light: {
      "--et-jade": p[7],
      "--et-jade-tint": p[0],
      "--et-bg-glow-1": hexAlpha(p[7], 0.09),
      [`--mantine-color-${accent.id}-light-color`]: p[7],
      ...note,
    },
    dark: {
      "--et-jade": p[4],
      "--et-jade-tint": hexAlpha(p[4], 0.14),
      "--et-bg-glow-1": hexAlpha(p[4], 0.1),
      ...note,
    },
  };
}

const block = (selector: string, vars: Record<string, string>): string =>
  `${selector} {\n${Object.entries(vars)
    .map(([k, v]) => `  ${k}: ${v};`)
    .join("\n")}\n}`;

/**
 * Stylesheet with one rule per accent and scheme. Selectors carry ``data-accent`` on top of the
 * scheme attribute so they win over the defaults in tokens.css.
 */
export function accentStylesheet(): string {
  return ACCENTS.flatMap((a) => {
    const vars = accentVariables(a);
    const root = `:root[data-accent="${a.id}"]`;
    return [
      // Scheme-specific selectors only: a bare :root rule would leak light values into dark mode.
      block(`${root}[data-mantine-color-scheme="light"]`, vars.light),
      block(`${root}[data-mantine-color-scheme="dark"]`, vars.dark),
    ];
  }).join("\n");
}

/**
 * Visual system "Cédula" (see src/styles/design-tokens.json for the rationale and contrast checks).
 *
 * Jade is the primary, greys are tinted green so light and dark read as the same paper, and the dark
 * palette is a green-black scale (not an inverted light theme). CSS variables that Mantine does not
 * own (page background, brass accent, chart palette, motion) live in src/styles/tokens.css.
 */
import {
  Badge,
  Button,
  Card,
  createTheme,
  Modal,
  Paper,
  SegmentedControl,
  Skeleton,
  Table,
  TableScrollContainer,
  Tabs,
  type MantineColorsTuple,
} from "@mantine/core";

import { ACCENTS, DEFAULT_ACCENT, type AccentId } from "./lib/accents";

/** Accent palettes (R13.10): jade plus the alternatives chosen in Configurações. */
const accentColors = Object.fromEntries(
  ACCENTS.map((a) => [a.id, a.palette]),
) as Record<AccentId, MantineColorsTuple>;

/** Light neutrals: graphite with a green tint (gray[6] is the AA "dimmed" text). */
const gray: MantineColorsTuple = [
  "#F6F8F7",
  "#EEF2F0",
  "#E1E7E4",
  "#CDD6D2",
  "#ADB9B4",
  "#87958F",
  "#5E6B66",
  "#46524D",
  "#2D3733",
  "#15201C",
];

/** Dark surfaces: [0] text, [2] dimmed, [4] borders, [6] inputs, [7] surface, [9] page. */
const dark: MantineColorsTuple = [
  "#E4EBE8",
  "#C2CEC9",
  "#93A39C",
  "#6C7B75",
  "#3D4A45",
  "#2B3632",
  "#1E2925",
  "#131C19",
  "#0F1714",
  "#0B1210",
];

/** Carmine instead of Mantine's default red, so errors and negatives belong to the palette. */
const red: MantineColorsTuple = [
  "#FCEEF1",
  "#F8D9E0",
  "#F1B2C0",
  "#F08196",
  "#E5627B",
  "#D44461",
  "#C2304F",
  "#B4233F",
  "#8F1A31",
  "#6B1224",
];

const brass: MantineColorsTuple = [
  "#FBF5E6",
  "#F4E7C4",
  "#ECD59A",
  "#E3C27A",
  "#E0B864",
  "#C99D45",
  "#A9822F",
  "#8A6A22",
  "#6C521A",
  "#4E3B12",
];

export const theme = createTheme({
  primaryColor: DEFAULT_ACCENT,
  // Same filled shade in both schemes on purpose. Mantine's variant resolver picks the autoContrast
  // text colour from the *light* shade only, so a lighter dark shade (e.g. jade[4]) would get white
  // text at 2.5:1. Shade 7 keeps white text at >= 5:1 for jade, red, brass and gray in both themes;
  // the vivid jade[4] is still used for dark-mode text, outlines and accents via --et-jade.
  primaryShade: { light: 7, dark: 7 },
  colors: { ...accentColors, gray, dark, red, brass },
  black: "#15201C",
  white: "#FFFFFF",
  autoContrast: true,
  luminanceThreshold: 0.32,
  respectReducedMotion: true,
  fontFamily:
    "'Manrope Variable', system-ui, -apple-system, 'Segoe UI', sans-serif",
  fontFamilyMonospace: "ui-monospace, 'SFMono-Regular', Menlo, monospace",
  headings: {
    fontFamily:
      "'Bricolage Grotesque Variable', 'Manrope Variable', system-ui, sans-serif",
    fontWeight: "650",
    sizes: {
      h1: { fontSize: "2.25rem", lineHeight: "1.15" },
      h2: { fontSize: "1.75rem", lineHeight: "1.2" },
      h3: { fontSize: "1.25rem", lineHeight: "1.3" },
      h4: { fontSize: "1.0625rem", lineHeight: "1.35" },
    },
  },
  defaultRadius: "md",
  radius: {
    xs: "6px",
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "24px",
  },
  // Layered, green-tinted shadows: a tight contact shadow plus a soft ambient one.
  shadows: {
    xs: "0 1px 2px rgba(12, 34, 27, 0.06)",
    sm: "0 1px 2px rgba(12, 34, 27, 0.06), 0 2px 6px rgba(12, 34, 27, 0.05)",
    md: "0 1px 3px rgba(12, 34, 27, 0.07), 0 8px 20px -6px rgba(12, 34, 27, 0.12)",
    lg: "0 2px 4px rgba(12, 34, 27, 0.06), 0 18px 40px -12px rgba(12, 34, 27, 0.22)",
    xl: "0 4px 8px rgba(12, 34, 27, 0.08), 0 28px 60px -16px rgba(12, 34, 27, 0.30)",
  },
  cursorType: "pointer",
  focusRing: "auto",
  components: {
    Button: Button.extend({
      defaultProps: { radius: "md" },
      classNames: { root: "et-press" },
    }),
    Paper: Paper.extend({ defaultProps: { radius: "lg" } }),
    Card: Card.extend({ defaultProps: { radius: "lg" } }),
    Badge: Badge.extend({ defaultProps: { radius: "sm" } }),
    Modal: Modal.extend({
      defaultProps: {
        radius: "lg",
        overlayProps: { backgroundOpacity: 0.45, blur: 6 },
        transitionProps: { transition: "pop", duration: 180 },
      },
    }),
    SegmentedControl: SegmentedControl.extend({
      defaultProps: { radius: "xl" },
    }),
    Skeleton: Skeleton.extend({ defaultProps: { radius: "md" } }),
    Table: Table.extend({
      defaultProps: { verticalSpacing: "xs", highlightOnHover: true },
      classNames: { table: "et-table" },
    }),
    // R14.6: native scrollbar, visible whenever a wide table overflows (never silently cut).
    TableScrollContainer: TableScrollContainer.extend({
      defaultProps: { type: "native" },
    }),
    Tabs: Tabs.extend({ classNames: { root: "et-tabs" } }),
  },
});

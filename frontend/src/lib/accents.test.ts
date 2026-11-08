import { describe, expect, it } from "vitest";
import {
  ACCENTS,
  accentById,
  accentStylesheet,
  accentVariables,
  hexAlpha,
  isAccentId,
} from "./accents";

// WCAG 2.x relative luminance / contrast ratio.
type Rgb = [number, number, number];
function rgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function luminance([r, g, b]: Rgb): number {
  const [cr, cg, cb] = [r, g, b].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (cr ?? 0) + 0.7152 * (cg ?? 0) + 0.0722 * (cb ?? 0);
}
function blend(fg: string, alpha: number, bg: string): Rgb {
  const [f, b] = [rgb(fg), rgb(bg)];
  const mix = (i: 0 | 1 | 2) => Math.round(f[i] * alpha + b[i] * (1 - alpha));
  return [mix(0), mix(1), mix(2)];
}
function contrast(a: Rgb, b: Rgb): number {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// Surfaces of the "Cédula" tokens (tokens.css).
const LIGHT = ["#FFFFFF", "#F3F6F4", "#EEF2F0"];
const DARK = ["#131C19", "#0B1210", "#17221E"];
const AA = 4.5;

describe("accents", () => {
  it("r13_10 offers 6 to 8 named accents with Esmeralda first", () => {
    expect(ACCENTS.length).toBeGreaterThanOrEqual(6);
    expect(ACCENTS.length).toBeLessThanOrEqual(8);
    expect(ACCENTS[0]?.name).toBe("Esmeralda");
    expect(ACCENTS.map((a) => a.name)).toEqual(
      expect.arrayContaining(["Oceano", "Violeta", "Âmbar", "Rubi", "Grafite"]),
    );
    expect(isAccentId("ocean")).toBe(true);
    expect(isAccentId("pink")).toBe(false);
    expect(isAccentId(null)).toBe(false);
    expect(accentById("ruby").name).toBe("Rubi");
    expect(hexAlpha("#102030", 0.5)).toBe("rgba(16, 32, 48, 0.5)");
  });

  it.each(ACCENTS.map((a) => [a.name, a] as const))(
    "r13_10 %s keeps AA contrast in light and dark",
    (_name, accent) => {
      const p = accent.palette;
      // Filled buttons: white text on shade 7 (both schemes).
      expect(contrast(rgb("#FFFFFF"), rgb(p[7]))).toBeGreaterThanOrEqual(AA);
      // Light: accent text (shade 7) on surfaces, on its tint and on the light variant.
      for (const bg of LIGHT)
        expect(contrast(rgb(p[7]), rgb(bg))).toBeGreaterThanOrEqual(AA);
      expect(contrast(rgb(p[7]), rgb(p[0]))).toBeGreaterThanOrEqual(AA);
      expect(
        contrast(rgb(p[7]), blend(p[7], 0.1, "#FFFFFF")),
      ).toBeGreaterThanOrEqual(AA);
      // Dark: accent text (shade 4) and light-variant text (shade 2) on surfaces and tints.
      for (const bg of DARK) {
        expect(contrast(rgb(p[4]), rgb(bg))).toBeGreaterThanOrEqual(AA);
        expect(contrast(rgb(p[2]), rgb(bg))).toBeGreaterThanOrEqual(AA);
        expect(
          contrast(rgb(p[4]), blend(p[4], 0.14, bg)),
        ).toBeGreaterThanOrEqual(AA);
        expect(
          contrast(rgb(p[2]), blend(p[5], 0.15, bg)),
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );

  it("r13_10 builds per-scheme CSS variables for every accent", () => {
    const vars = accentVariables(accentById("ocean"));
    expect(vars.light["--et-jade"]).toBe(accentById("ocean").palette[7]);
    expect(vars.dark["--et-jade"]).toBe(accentById("ocean").palette[4]);
    const css = accentStylesheet();
    for (const a of ACCENTS) {
      expect(css).toContain(
        `:root[data-accent="${a.id}"][data-mantine-color-scheme="light"]`,
      );
      expect(css).toContain(
        `:root[data-accent="${a.id}"][data-mantine-color-scheme="dark"]`,
      );
      expect(css).not.toContain(`:root[data-accent="${a.id}"] {`);
      expect(css).not.toContain(`:root[data-accent="${a.id}"],`);
    }
  });
});

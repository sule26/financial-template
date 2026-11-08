import { afterEach, describe, expect, it } from "vitest";
import { formatMonth } from "../hooks/month";
import { formatDate, formatMoney } from "../lib/format";
import { EN } from "./en";
import { translate } from "./i18n";

describe("i18n (R14.13)", () => {
  afterEach(() => localStorage.clear());

  it("r14_13 translates known texts, keeps Portuguese for unknown ones, fills placeholders", () => {
    expect(translate("Resumo", "en")).toBe("Summary");
    expect(translate("Resumo", "pt-BR")).toBe("Resumo");
    expect(translate("Texto sem tradução", "en")).toBe("Texto sem tradução");
    expect(
      translate("Para onde foi o dinheiro em {month}.", "en", {
        month: "Oct 2026",
      }),
    ).toBe("Where the money went in Oct 2026.");
  });

  it("r14_13 every English entry is a non-empty text", () => {
    for (const [pt, en] of Object.entries(EN)) {
      expect(pt.length).toBeGreaterThan(0);
      expect(en.trim().length).toBeGreaterThan(0);
    }
  });

  it("r14_13 formats default to Brazilian Portuguese", () => {
    expect(formatMoney("1234.5")).toMatch(/R\$\s?1\.234,50/);
    expect(formatDate("2026-10-09")).toBe("09/10/2026");
    expect(formatMonth("2026-10")).toBe("out/2026");
  });
});

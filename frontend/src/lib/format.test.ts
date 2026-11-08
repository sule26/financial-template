import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatMoney,
  formatPct,
  parseMoneyInput,
  sumMoney,
} from "./format";

describe("format helpers", () => {
  it("parses user-typed amounts into canonical decimal strings", () => {
    expect(parseMoneyInput("1.234,56")).toBe("1234.56");
    expect(parseMoneyInput("12,5")).toBe("12.50");
    expect(parseMoneyInput("1234.56")).toBe("1234.56");
    expect(parseMoneyInput("8.000")).toBe("8000.00");
    expect(parseMoneyInput("R$ 10")).toBe("10.00");
    expect(parseMoneyInput("-3,63")).toBe("-3.63");
    expect(parseMoneyInput("")).toBeNull();
    expect(parseMoneyInput("abc")).toBeNull();
    expect(parseMoneyInput("1,234")).toBeNull();
  });

  it("formats money, percentages and dates", () => {
    expect(formatMoney("1234.5")).toContain("1.234,50");
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney("x")).toBe("x");
    expect(formatPct("54.55")).toBe("54,55%");
    expect(formatPct(null)).toBe("—");
    expect(formatDate("2026-10-12")).toBe("12/10/2026");
    expect(formatDate(null)).toBe("—");
  });

  it("sums decimal strings without float drift", () => {
    expect(sumMoney(["0.10", "0.20", null, "-0.05"])).toBe("0.25");
    expect(sumMoney(["-1.00", "0.50"])).toBe("-0.50");
  });
});

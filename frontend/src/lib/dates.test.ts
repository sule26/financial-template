import { describe, expect, it } from "vitest";
import {
  dateToIso,
  dateToMonth,
  isoToDate,
  monthToDate,
  todayIso,
} from "./dates";

describe("dates", () => {
  it("r13_13 converts months both ways using local parts", () => {
    const d = monthToDate("2026-03");
    expect(d?.getFullYear()).toBe(2026);
    expect(d?.getMonth()).toBe(2);
    expect(d?.getDate()).toBe(1);
    expect(dateToMonth(new Date(2026, 11, 31, 23, 59))).toBe("2026-12");
    expect(dateToMonth(null)).toBe("");
    expect(monthToDate("")).toBeNull();
    expect(monthToDate("2026-13")).toBeNull();
    expect(monthToDate(undefined)).toBeNull();
  });

  it("r13_13 converts dates both ways without a timezone shift", () => {
    // 23:30 local would become the next day through toISOString in UTC-3.
    expect(dateToIso(new Date(2026, 9, 31, 23, 30))).toBe("2026-10-31");
    expect(dateToIso(new Date(2026, 0, 5, 0, 0))).toBe("2026-01-05");
    expect(dateToIso(null)).toBe("");
    const d = isoToDate("2026-10-05");
    expect([d?.getFullYear(), d?.getMonth(), d?.getDate()]).toEqual([
      2026, 9, 5,
    ]);
    expect(isoToDate("2026-02-30")).toBeNull();
    expect(isoToDate("05/10/2026")).toBeNull();
    expect(isoToDate(null)).toBeNull();
    expect(todayIso(new Date(2026, 9, 12, 23, 50))).toBe("2026-10-12");
  });
});

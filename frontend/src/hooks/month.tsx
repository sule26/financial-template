import { currentLang } from "../i18n/i18n";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/** Month as "YYYY-MM". */
export type Month = string;

export function monthOf(date: Date): Month {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export function addMonths(month: Month, delta: number): Month {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const idx = y * 12 + (m - 1) + delta;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

export const MONTH_NAMES = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

const MONTH_NAMES_EN = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function formatMonth(month: Month): string {
  const [y, m] = month.split("-").map(Number) as [number, number];
  // R14.13: "out/2026" in Portuguese, "Oct 2026" in English
  return currentLang() === "en"
    ? `${MONTH_NAMES_EN[m - 1]} ${y}`
    : `${MONTH_NAMES[m - 1]}/${y}`;
}

interface MonthContextValue {
  current: Month;
  selected: Month;
  setSelected: (m: Month) => void;
  shift: (delta: number) => void;
  reset: () => void;
  isCurrent: boolean;
}

const MonthContext = createContext<MonthContextValue | null>(null);

/**
 * Month in focus (docs/07 "Mês em foco"). Always starts at the real current month; it is never
 * persisted, so every reload opens on the current month (R1.13).
 */
export function MonthProvider({
  children,
  today,
}: {
  children: ReactNode;
  today?: Date;
}) {
  const current = monthOf(today ?? new Date());
  const [selected, setSelected] = useState<Month>(current);
  const shift = useCallback(
    (delta: number) => setSelected((m) => addMonths(m, delta)),
    [],
  );
  const reset = useCallback(() => setSelected(current), [current]);
  const value = useMemo(
    () => ({
      current,
      selected,
      setSelected,
      shift,
      reset,
      isCurrent: selected === current,
    }),
    [current, selected, shift, reset],
  );
  return (
    <MonthContext.Provider value={value}>{children}</MonthContext.Provider>
  );
}

export function useMonth(): MonthContextValue {
  const ctx = useContext(MonthContext);
  if (!ctx) throw new Error("useMonth must be used inside MonthProvider");
  return ctx;
}

/**
 * Conversions between the API's plain strings ("YYYY-MM", "YYYY-MM-DD") and the local-time Date
 * objects used by @mantine/dates pickers (R13.13).
 *
 * Everything uses local date parts on purpose: ``toISOString`` converts to UTC and shifts the day
 * near midnight in negative offsets such as America/Sao_Paulo.
 */

export const MONTH_STR_RE = /^(\d{4})-(0[1-9]|1[0-2])$/;
export const DATE_STR_RE = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

const pad = (n: number): string => String(n).padStart(2, "0");

/** "2026-03" -> local Date for the 1st of that month; invalid or empty -> null. */
export function monthToDate(month: string | null | undefined): Date | null {
  const m = MONTH_STR_RE.exec((month ?? "").trim());
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, 1) : null;
}

/** Local Date -> "YYYY-MM"; null -> "". */
export function dateToMonth(date: Date | null | undefined): string {
  return date ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}` : "";
}

/** "2026-03-05" -> local Date; invalid (incl. 2026-02-30) or empty -> null. */
export function isoToDate(iso: string | null | undefined): Date | null {
  const m = DATE_STR_RE.exec((iso ?? "").trim());
  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]) - 1, Number(m[3])];
  const date = new Date(y, mo, d);
  // Reject overflow such as Feb 30 -> Mar 2.
  return date.getMonth() === mo && date.getDate() === d ? date : null;
}

/** Local Date -> "YYYY-MM-DD"; null -> "". */
export function dateToIso(date: Date | null | undefined): string {
  return date
    ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    : "";
}

/** Today's local date as "YYYY-MM-DD". */
export function todayIso(now: Date = new Date()): string {
  return dateToIso(now);
}

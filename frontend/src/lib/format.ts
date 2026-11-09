/** Formatting helpers. Money comes from the API as decimal strings; the backend computes. */

import { currentLang } from "../i18n/i18n";

// R14.13: amounts are always in reais; only the number format follows the language.
const BRL = {
  "pt-BR": new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }),
  en: new Intl.NumberFormat("en-US", { style: "currency", currency: "BRL" }),
};

export function formatMoney(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? BRL[currentLang()].format(n) : value;
}

/** Parse a user-typed amount ("1.234,56", "1234.56", "12,5") into a canonical "1234.56". */
export function parseMoneyInput(text: string): string | null {
  const raw = text.trim().replace(/\s|R\$/g, "");
  if (!raw) return null;
  let normalized = raw;
  if (raw.includes(",")) normalized = raw.replace(/\./g, "").replace(",", ".");
  else if (/^-?\d{1,3}(\.\d{3})+$/.test(raw))
    normalized = raw.replace(/\./g, ""); // "8.000"
  if (!/^-?\d+(\.\d{1,2})?$/.test(normalized)) return null;
  const [whole, cents = ""] = normalized.split(".");
  return `${whole}.${cents.padEnd(2, "0")}`;
}

export function formatPct(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toLocaleString(currentLang() === "en" ? "en-US" : "pt-BR", { maximumFractionDigits: 2 })}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return currentLang() === "en" ? `${m}/${d}/${y}` : `${d}/${m}/${y}`;
}

export const METHOD_LABELS: Record<string, string> = {
  credit: "Crédito",
  benefit: "Cartão de benefícios",
  debit: "Débito",
  pix: "PIX",
  transfer: "Transferência",
  boleto: "Boleto",
  cash: "Dinheiro",
  account: "Débito/PIX/conta",
};

export const KIND_LABELS: Record<string, string> = {
  expense: "Gasto",
  refund: "Estorno",
  fee: "Tarifa/juros",
  income: "Receita",
  transfer: "Transferência",
  settlement: "Acerto",
  investment: "Investimento",
};

export const STATE_LABELS: Record<string, string> = {
  real: "real",
  open: "fatura aberta",
  projected: "projetado",
  missing: "faltando",
};

/** Sum of decimal strings, in cents, to avoid float drift in the UI. */
export function sumMoney(values: (string | null | undefined)[]): string {
  let cents = 0;
  for (const v of values) if (v) cents += Math.round(Number(v) * 100);
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

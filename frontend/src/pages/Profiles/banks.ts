/** Pure helpers behind the simple mode of Perfis de banco (R13.9). */
import { sumMoney } from "../../lib/format";
import type { ExampleInfo, ProfilesList, ProfileTestResult } from "./types";

export interface Bank {
  id: string;
  name: string;
  /** "fatura" | "extrato" | null when unknown (older backends list examples by id only). */
  kind: string | null;
  format: string | null;
  files: number;
  errors: number;
  /** Example shipped with the app (embutido), not a file in profiles/. */
  builtin: boolean;
  /** Where its YAML is read from: profiles/ or the built-in examples. */
  source: "profile" | "example";
}

export const exampleId = (e: ExampleInfo): string =>
  typeof e === "string" ? e : e.id;

const kindFromId = (id: string): string | null =>
  id.includes("extrato") ? "extrato" : id.includes("fatura") ? "fatura" : null;

/** Profiles plus built-in examples, one entry per id, sorted by name. */
export function supportedBanks(list: ProfilesList): Bank[] {
  const exampleIds = new Set(list.examples.map(exampleId));
  const banks = new Map<string, Bank>();
  for (const p of list.profiles)
    banks.set(p.id, {
      id: p.id,
      name: p.name,
      kind: p.kind,
      format: p.format,
      files: p.files,
      errors: p.errors,
      builtin: exampleIds.has(p.id) || (p.file ?? "").startsWith("examples/"),
      source: "profile",
    });
  for (const e of list.examples) {
    const id = exampleId(e);
    if (banks.has(id)) continue;
    const info = typeof e === "string" ? { id } : e;
    banks.set(id, {
      id,
      name: info.name ?? id,
      kind: info.kind ?? kindFromId(id),
      format: info.format ?? null,
      files: info.files ?? 0,
      errors: info.errors ?? 0,
      builtin: true,
      source: "example",
    });
  }
  return [...banks.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export const KIND_TEXT: Record<string, string> = {
  fatura: "Fatura de cartão",
  extrato: "Extrato de conta",
};

export interface TestSummary {
  count: number;
  sum: string;
  /** Bank total from the document; null when the document has none. */
  total: string | null;
  /** total - sum; "0.00" when it matches. */
  difference: string | null;
  matches: boolean | null;
}

/** Reads a /api/profiles/test result as numbers a person can check. */
export function summarize(result: ProfileTestResult): TestSummary {
  const lines = result.lines ?? [];
  const sum = sumMoney(lines.map((l) => l.amount));
  const raw = result.header?.total;
  const total =
    typeof raw === "string" || typeof raw === "number" ? String(raw) : null;
  if (total === null)
    return { count: lines.length, sum, total, difference: null, matches: null };
  const difference = sumMoney([total, String(-Number(sum))]);
  return {
    count: lines.length,
    sum,
    total,
    difference,
    matches: difference === "0.00",
  };
}

/**
 * R14.25: who the screens show by default (Resumo, Projeção, A receber), chosen in
 * Configurações and remembered in this browser. Empty = everybody (the household).
 */
export const DEFAULT_PEOPLE_KEY = "expense-tracker-default-people";

export function readDefaultPeople(): string[] {
  try {
    const raw = window.localStorage.getItem(DEFAULT_PEOPLE_KEY);
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value)
      ? value.filter((v): v is string => typeof v === "string")
      : [];
  } catch {
    return [];
  }
}

export function saveDefaultPeople(ids: string[]): void {
  try {
    window.localStorage.setItem(DEFAULT_PEOPLE_KEY, JSON.stringify(ids));
  } catch {
    // Private mode / quota: the choice still applies for this session.
  }
}

/** Only ids that still exist (a removed person never sticks as default). */
export function knownPeople(
  ids: string[],
  users: { id: string }[] | undefined,
): string[] {
  if (!users) return ids;
  const known = new Set(users.map((u) => u.id));
  return ids.filter((id) => known.has(id));
}

/**
 * Interface language (R14.13): pt-BR (default) or en, chosen in Configurações and remembered in
 * this browser. Texts are written in Portuguese in the code; ``t()`` looks the Portuguese text
 * up in the English dictionary and returns it unchanged when there is no translation (so a
 * missing entry shows Portuguese, never a broken key). Money stays in R$ in both languages.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { EN } from "./en";

export type Lang = "pt-BR" | "en";
export const LANG_STORAGE_KEY = "expense-tracker-language";
export const LANGS: { id: Lang; name: string }[] = [
  { id: "pt-BR", name: "Português (Brasil)" },
  { id: "en", name: "English" },
];

let current: Lang = "pt-BR";

/** Language in use right now (also read by the formatting helpers). */
export function currentLang(): Lang {
  return current;
}

export function readStoredLang(): Lang {
  try {
    const value = window.localStorage.getItem(LANG_STORAGE_KEY);
    return value === "en" ? "en" : "pt-BR";
  } catch {
    return "pt-BR";
  }
}

/** Translate a Portuguese UI text; ``{name}`` placeholders are filled from ``vars``. */
export function translate(
  text: string,
  lang: Lang = current,
  vars?: Record<string, string | number>,
): string {
  const base = lang === "en" ? (EN[text] ?? text) : text;
  if (!vars) return base;
  return base.replace(/\{(\w+)\}/g, (m, k: string) =>
    k in vars ? String(vars[k]) : m,
  );
}

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (text: string, vars?: Record<string, string | number>) => string;
}

const LangContext = createContext<LangContextValue>({
  lang: "pt-BR",
  setLang: () => {},
  t: (text, vars) => translate(text, "pt-BR", vars),
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    current = readStoredLang();
    return current;
  });
  useEffect(() => {
    current = lang;
    document.documentElement.setAttribute("lang", lang);
  }, [lang]);
  const setLang = useCallback((next: Lang) => {
    current = next;
    setLangState(next);
    try {
      window.localStorage.setItem(LANG_STORAGE_KEY, next);
    } catch {
      // Private mode / quota: the choice still applies for this session.
    }
  }, []);
  const value = useMemo<LangContextValue>(
    () => ({
      lang,
      setLang,
      t: (text, vars) => translate(text, lang, vars),
    }),
    [lang, setLang],
  );
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  return useContext(LangContext);
}

/** Shortcut for components that only need ``t``. */
export function useT(): LangContextValue["t"] {
  return useContext(LangContext).t;
}

/** Inline translation of a Portuguese text node: ``<T>Resumo</T>``. */
export function T({ children }: { children: string }) {
  const t = useT();
  return <>{t(children)}</>;
}

/** Translates plain strings, leaves rich nodes untouched. */
export function TNode({ children }: { children: ReactNode }) {
  const t = useT();
  return <>{typeof children === "string" ? t(children) : children}</>;
}

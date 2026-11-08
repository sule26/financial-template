/** Accent colour chosen in Configurações (R13.10), remembered in this browser. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  ACCENT_STORAGE_KEY,
  accentStylesheet,
  DEFAULT_ACCENT,
  isAccentId,
  type AccentId,
} from "../lib/accents";

const STYLE_ID = "et-accent-vars";

/** Stored accent, falling back to the default when absent, invalid or storage is unavailable. */
export function readStoredAccent(): AccentId {
  try {
    const value = window.localStorage.getItem(ACCENT_STORAGE_KEY);
    return isAccentId(value) ? value : DEFAULT_ACCENT;
  } catch {
    return DEFAULT_ACCENT;
  }
}

/** Puts the accent stylesheet in <head> (once) and marks <html> with the chosen accent. */
export function applyAccent(accent: AccentId): void {
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = accentStylesheet();
    document.head.appendChild(style);
  }
  document.documentElement.setAttribute("data-accent", accent);
}

interface AccentContextValue {
  accent: AccentId;
  setAccent: (accent: AccentId) => void;
}

const AccentContext = createContext<AccentContextValue>({
  accent: DEFAULT_ACCENT,
  setAccent: () => {},
});

/**
 * Holds the accent and renders ``children`` with it, so the Mantine theme can use it as
 * ``primaryColor``. Changing it applies immediately (no reload).
 */
export function AccentProvider({
  children,
}: {
  children: (accent: AccentId) => ReactNode;
}) {
  const [accent, setState] = useState<AccentId>(readStoredAccent);

  useEffect(() => applyAccent(accent), [accent]);

  const setAccent = useCallback((next: AccentId) => {
    setState(next);
    try {
      window.localStorage.setItem(ACCENT_STORAGE_KEY, next);
    } catch {
      // Private mode / quota: the choice still applies for this session.
    }
  }, []);

  const value = useMemo(() => ({ accent, setAccent }), [accent, setAccent]);
  return (
    <AccentContext.Provider value={value}>
      {children(accent)}
    </AccentContext.Provider>
  );
}

export function useAccent(): AccentContextValue {
  return useContext(AccentContext);
}

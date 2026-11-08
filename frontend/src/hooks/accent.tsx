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
  ACCENTS,
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

/** R14.18: favicon in the accent colour (same coin as the logo). */
export function faviconSvg(coin: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
    `<circle cx="16" cy="16" r="15.5" fill="${coin}"/>` +
    `<circle cx="16" cy="16" r="12.5" fill="none" stroke="#E3C27A" stroke-width="1.2"/>` +
    `<circle cx="16" cy="16" r="6" fill="none" stroke="#E3C27A" stroke-width="1.2"/>` +
    `<circle cx="16" cy="16" r="2" fill="#E3C27A"/></svg>`
  );
}

function applyFavicon(accent: AccentId): void {
  const coin = ACCENTS.find((a) => a.id === accent)?.palette[8];
  if (!coin) return;
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  link.type = "image/svg+xml";
  link.href = `data:image/svg+xml,${encodeURIComponent(faviconSvg(coin))}`;
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
  applyFavicon(accent);
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

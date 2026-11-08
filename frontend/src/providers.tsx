import { Fragment } from "react";
import { LanguageProvider, useLang } from "./i18n/i18n";
import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "dayjs/locale/pt-br";
import { useMemo, type ReactNode } from "react";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { AccentProvider } from "./hooks/accent";
import { MonthProvider } from "./hooks/month";
import type { AccentId } from "./lib/accents";
import { theme } from "./theme";

// R1.14: light / dark / system, remembered in this browser
const colorSchemeManager = localStorageColorSchemeManager({
  key: "expense-tracker-color-scheme",
});

// R13.13: every month/date picker speaks Portuguese and starts the week on Sunday.
const DATES_SETTINGS = { locale: "pt-br", firstDayOfWeek: 0 as const };

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, staleTime: 5_000 },
    },
  });
}

interface ProvidersProps {
  children: ReactNode;
  client?: QueryClient;
  initialPath?: string;
  today?: Date;
}

/** Mantine theme with the accent chosen in Configurações as primary colour (R13.10). */
function ThemedMantine({
  accent,
  children,
}: {
  accent: AccentId;
  children: ReactNode;
}) {
  const themed = useMemo(() => ({ ...theme, primaryColor: accent }), [accent]);
  return (
    <MantineProvider
      theme={themed}
      defaultColorScheme="auto"
      colorSchemeManager={colorSchemeManager}
    >
      {children}
    </MantineProvider>
  );
}

/** All app-level providers. Tests pass ``initialPath`` (memory router) and a fixed ``today``. */
export function Providers({
  children,
  client,
  initialPath,
  today,
}: ProvidersProps) {
  const qc = client ?? makeQueryClient();
  const Router = initialPath === undefined ? BrowserRouter : MemoryRouter;
  const future = { v7_startTransition: true, v7_relativeSplatPath: true };
  const routerProps =
    initialPath === undefined
      ? { future }
      : { future, initialEntries: [initialPath] };
  return (
    <LanguageProvider>
      <LangKeyed>
        <AccentProvider>
          {(accent) => (
            <ThemedMantine accent={accent}>
              <DatesProvider settings={DATES_SETTINGS}>
                <Notifications position="top-right" />
                <QueryClientProvider client={qc}>
                  <MonthProvider today={today}>
                    <Router {...routerProps}>{children}</Router>
                  </MonthProvider>
                </QueryClientProvider>
              </DatesProvider>
            </ThemedMantine>
          )}
        </AccentProvider>
      </LangKeyed>
    </LanguageProvider>
  );
}

/** R14.13: changing the language re-renders the whole tree (formatters read it at render). */
function LangKeyed({ children }: { children: ReactNode }) {
  const { lang } = useLang();
  return <Fragment key={lang}>{children}</Fragment>;
}

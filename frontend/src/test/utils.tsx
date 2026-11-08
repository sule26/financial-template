import {
  render,
  screen,
  waitFor,
  within,
  type RenderResult,
} from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";
import { PICKER_ARIA_LABELS } from "../components/ui/pickerLabels";
import { makeQueryClient, Providers } from "../providers";

type Handler = (body: unknown, url: URL) => unknown;
export interface Routes {
  [key: string]: Handler | unknown; // "GET /api/users" -> value or handler
}

/** Stub fetch with a route table. Unmatched routes return 404. Calls are recorded. */
export function mockApi(routes: Routes) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path: url.pathname + url.search, body });
    const key = `${method} ${url.pathname}`;
    const handler =
      key in routes
        ? routes[key]
        : routes[`${method} ${url.pathname}${url.search}`];
    if (handler === undefined) {
      return new Response(
        JSON.stringify({
          error: { code: "not_found", message: `no mock ${key}` },
        }),
        {
          status: 404,
        },
      );
    }
    try {
      const value =
        typeof handler === "function"
          ? (handler as Handler)(body, url)
          : handler;
      if (value instanceof Response) return value;
      return new Response(value === undefined ? null : JSON.stringify(value), {
        status: value === undefined ? 204 : 200,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ error: { code: "test_error", message: String(err) } }),
        {
          status: 422,
        },
      );
    }
  });
  vi.stubGlobal("fetch", fn);
  return { calls, fn };
}

export function apiError(status: number, code: string, message: string) {
  return new Response(
    JSON.stringify({ error: { code, message, details: {} } }),
    { status },
  );
}

export function renderPage(
  ui: ReactElement,
  path = "/",
  today = new Date(2026, 9, 12),
): RenderResult {
  return render(
    <Providers client={makeQueryClient()} initialPath={path} today={today}>
      {ui}
    </Providers>,
  );
}

/** Minimal catalog used by most page tests. */
export const CATALOG = {
  "GET /api/users": [
    {
      id: "eu",
      name: "Eu",
      aliases: [],
      income_history: [{ from_month: "2026-01", amount: "9000.00" }],
      benefit_income_history: [],
    },
    {
      id: "ana",
      name: "Ana",
      aliases: [],
      income_history: [],
      benefit_income_history: [],
    },
  ],
  "GET /api/cards": [
    {
      id: "card_x",
      name: "Cartão X",
      parent_card_id: null,
      account_id: null,
      owners: [{ user_id: "eu", pct: "100.00" }],
      responsible_user_id: "eu",
      last_digits: ["1234"],
      billing_history: [{ from_month: "2026-01", closing_day: 3, due_day: 10 }],
      limit: "5000.00",
      profile_id: null,
    },
  ],
  "GET /api/accounts": [
    {
      id: "acc_x",
      name: "Conta X",
      type: "checking",
      owners: [{ user_id: "eu", pct: "100.00" }],
      responsible_user_id: "eu",
      profile_id: null,
      account_hint: null,
      confirm_manual_after_days: null,
    },
  ],
  "GET /api/categories": [
    { id: "cat_casa", name: "Casa", color: "#4C6EF5", budget: null },
    { id: "cat_lazer", name: "Lazer", color: "#40C057", budget: null },
  ],
  "GET /api/split-profiles": [
    {
      id: "split_casal",
      name: "Casal",
      members: ["eu", "ana"],
      mode: "fixed",
      history: [
        {
          from_month: "2026-01",
          shares: [
            { user_id: "eu", pct: "60.00" },
            { user_id: "ana", pct: "40.00" },
          ],
        },
      ],
    },
  ],
  "GET /api/alerts": [],
};

// ---------------------------------------------------------------- pickers (R13.13)

type User = { click: (el: Element) => Promise<void> };

const MONTHS_SHORT = [
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
const MONTHS_LONG = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

async function openDropdown(user: User, field: HTMLElement, level: string) {
  await user.click(field);
  const controls = await screen.findAllByLabelText(level);
  const control = controls[controls.length - 1];
  if (!control) throw new Error("picker level control not found");
  const dropdown = control.closest<HTMLElement>(".mantine-Popover-dropdown");
  if (!dropdown) throw new Error("picker dropdown not found");
  return { control, dropdown };
}

/** Waits for the picker to close, so the next one opened is not confused with it. */
async function closed(dropdown: HTMLElement) {
  await waitFor(() => {
    if (dropdown.isConnected) throw new Error("picker still open");
  });
}

/** In the decade level, page until ``year`` is visible and click it. */
async function chooseYear(user: User, dropdown: HTMLElement, year: number) {
  for (let i = 0; i < 20; i++) {
    const button = within(dropdown).queryByRole("button", {
      name: String(year),
    });
    if (button) {
      await user.click(button);
      return;
    }
    const shown = within(dropdown)
      .getAllByRole("button")
      .map((b) => Number(b.textContent))
      .filter((n) => n > 1000);
    const label =
      year < Math.min(...shown)
        ? PICKER_ARIA_LABELS.previousDecade
        : PICKER_ARIA_LABELS.nextDecade;
    await user.click(within(dropdown).getByLabelText(label));
  }
  throw new Error(`year ${year} not reachable`);
}

/** Chooses "YYYY-MM" in a MonthField (MonthPickerInput). */
export async function pickMonth(user: User, field: HTMLElement, month: string) {
  const [y = 0, m = 1] = month.split("-").map(Number);
  const { control, dropdown } = await openDropdown(
    user,
    field,
    PICKER_ARIA_LABELS.yearLevelControl,
  );
  await user.click(control);
  await chooseYear(user, dropdown, y);
  await user.click(
    within(dropdown).getByRole("button", { name: MONTHS_SHORT[m - 1] ?? "" }),
  );
  await closed(dropdown);
}

/** Chooses "YYYY-MM-DD" in a DateField (DatePickerInput). */
export async function pickDate(user: User, field: HTMLElement, iso: string) {
  const [y = 0, m = 1, d = 1] = iso.split("-").map(Number);
  const { control, dropdown } = await openDropdown(
    user,
    field,
    PICKER_ARIA_LABELS.monthLevelControl,
  );
  await user.click(control);
  await user.click(
    within(dropdown).getByLabelText(PICKER_ARIA_LABELS.yearLevelControl),
  );
  await chooseYear(user, dropdown, y);
  await user.click(
    within(dropdown).getByRole("button", { name: MONTHS_SHORT[m - 1] ?? "" }),
  );
  await user.click(
    within(dropdown).getByLabelText(`${d} ${MONTHS_LONG[m - 1] ?? ""} ${y}`),
  );
  await closed(dropdown);
}

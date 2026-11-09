/**
 * Visual tour (docs/11 "Tour visual"): seed a synthetic household through the API, then visit
 * every screen and catalog tab in light and dark mode, saving a full-page screenshot of each and
 * failing on any console error, page error or failed API call. Screenshots go to SHOTS_DIR, which
 * scripts/ui-tour.sh points outside the repository. No personal data: everything is made up here.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { copyFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const INBOX = process.env.INBOX_DIR ?? "/inbox";
const FIXTURES = process.env.FIXTURES_DIR ?? "/fixtures";
const SHOTS = process.env.SHOTS_DIR ?? "/shots";

function month(offset: number): string {
  const d = new Date();
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + offset, 1));
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`;
}

function day(offsetDays: number): string {
  const d = new Date(Date.now() + offsetDays * 86_400_000);
  return d.toISOString().slice(0, 10);
}

async function seed(api: APIRequestContext) {
  const post = async (path: string, data: unknown) => {
    const res = await api.post(path, { data });
    expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
    return (await res.json()) as { id: string };
  };
  const cats = (await (await api.get("/api/categories")).json()) as { id: string; name: string }[];
  const cat = (name: string) => cats.find((c) => c.name === name)!.id;

  await post("/api/users", {
    id: "eu",
    name: "Eu",
    incomes: [
      {
        name: "Emprego",
        history: [{ from_month: month(-12), amount: "8000.00" }],
      },
      {
        name: "Freela",
        history: [{ from_month: month(-3), amount: "1500.00" }],
      },
    ],
    one_off_incomes: [
      { month: month(1), amount: "2500.00", description: "Bônus" },
    ],
  });
  await post("/api/users", {
    id: "ana",
    name: "Ana",
    income_history: [{ from_month: month(-12), amount: "6000.00" }],
  });
  await post("/api/users", { id: "pais", name: "Pais" });
  await post("/api/split-profiles", {
    id: "split_casal",
    name: "Casal",
    members: ["eu", "ana"],
    history: [
      {
        from_month: month(-12),
        mode: "fixed",
        shares: [
          { user_id: "eu", pct: "60.00" },
          { user_id: "ana", pct: "40.00" },
        ],
      },
    ],
  });
  await post("/api/accounts", {
    id: "acc_inter",
    name: "Inter",
    type: "checking",
    owners: { split_id: "split_casal" },
    responsible_user_id: "eu",
    // R14.1: Eu and Ana pay the Inter bill 60/40
    responsibles: [
      { user_id: "eu", pct: "60.00" },
      { user_id: "ana", pct: "40.00" },
    ],
  });
  await post("/api/accounts", {
    id: "acc_vr",
    name: "VR",
    type: "benefit",
    owners: [{ user_id: "eu", pct: "100.00" }],
    responsible_user_id: "eu",
    renewal_day: 5,
  });
  await post("/api/cards", {
    id: "card_inter",
    name: "Inter",
    account_id: "acc_inter",
    last_digits: ["1234"],
    billing_history: [{ from_month: month(-12), closing_day: 8, due_day: 15 }],
    limit: "12000.00",
    profile_id: "inter-fatura",
  });
  await post("/api/cards", {
    id: "card_inter_pais",
    name: "Inter",
    parent_card_id: "card_inter",
    owners: [{ user_id: "pais", pct: "100.00" }],
    last_digits: ["5678"],
  });
  await post("/api/cards", {
    id: "card_nubank",
    name: "Nubank",
    owners: [{ user_id: "eu", pct: "100.00" }],
    responsible_user_id: "eu",
    last_digits: ["4321"],
    billing_history: [{ from_month: month(-12), closing_day: 1, due_day: 8 }],
    limit: "5000.00",
  });
  await post("/api/benefits", {
    id: "ben_vr",
    name: "VR",
    user_id: "eu",
    destination: "card",
    account_id: "acc_vr",
    amount_history: [{ from_month: month(-12), amount: "900.00" }],
  });
  // R14.32: one benefit card with two benefits
  await post("/api/benefits", {
    id: "ben_ho",
    name: "Home office",
    user_id: "eu",
    destination: "card",
    account_id: "acc_vr",
    amount_history: [{ from_month: month(-12), amount: "150.00" }],
  });
  await post("/api/subscriptions", {
    id: "sub_stream",
    description: "STREAMING",
    amount: "55.90",
    start_month: month(-6),
    card_id: "card_nubank",
    category_id: cat("Entretenimento"),
    allocations: { split_id: "split_casal" },
    price_history: [{ from_month: month(-2), amount: "59.90" }],
    pauses: [{ from_month: month(-4), until_month: month(-4) }],
  });
  // R14.26: contas da casa are gastos recorrentes (occurrence = due date), one paid this month.
  // R14.27: from next month LUZ is split with the partner.
  for (const [id, description, amount, dueDay] of [
    ["rec_luz", "LUZ", "180.00", "10"],
    ["rec_agua", "AGUA", "90.00", "25"],
    ["rec_aluguel", "ALUGUEL", "2500.00", "05"],
  ] as const) {
    await post("/api/recurring-purchases", {
      id,
      description,
      estimated_amount: amount,
      every: { value: 1, unit: "months" },
      last_date: `${month(-1)}-${dueDay}`,
      payment_method: "boleto",
      account_id: "acc_inter",
      category_id: cat(id === "rec_aluguel" ? "Aluguel" : "Casa"),
      allocations: [{ user_id: "eu", pct: "100.00" }],
      allocation_history:
        id === "rec_luz"
          ? [{ from_month: month(1), allocations: { split_id: "split_casal" } }]
          : [],
      group: "household",
    });
  }
  await post("/api/transactions", {
    purchase_date: day(-2),
    amount: "2500.00",
    description: "ALUGUEL",
    category_id: cat("Aluguel"),
    payment_method: "boleto",
    account_id: "acc_inter",
    recurring_purchase_id: "rec_aluguel",
    recurring_month: month(0),
  });
  await post("/api/installment-plans", {
    id: "plan_geladeira",
    card_id: "card_inter",
    description: "GELADEIRA",
    total_installments: 10,
    first_invoice_month: month(-2),
    total_amount: "4000.00",
    category_id: cat("Casa"),
  });
  await post("/api/installment-plans", {
    id: "plan_celular",
    card_id: "card_nubank",
    description: "CELULAR",
    total_installments: 6,
    first_invoice_month: month(-1),
    total_amount: "1800.00",
    category_id: cat("Compras"),
  });
  // R7: the rest of CELULAR (from installment 3) all lands on next month's invoice.
  await post("/api/installment-plans/plan_celular/anticipate", {
    from_n: 3,
    target_month: month(1),
  });
  await post("/api/recurring-purchases", {
    id: "rec_feira",
    description: "FEIRA",
    estimated_amount: "120.00",
    every: { value: 7, unit: "days" },
    last_date: day(-3),
    card_id: "card_nubank",
    category_id: cat("Alimentação"),
    allocations: { split_id: "split_casal" },
  });
  await post("/api/savings-goals", {
    id: "goal_reserva",
    name: "Reserva",
    monthly_amount: "500.00",
    user_id: "eu",
  });
  await post("/api/rules", {
    id: "rule_mercado",
    priority: 100,
    when: { description_regex: "MERCADO" },
    then: { category_id: cat("Alimentação"), allocations: { split_id: "split_casal" } },
  });
  await post("/api/transactions", {
    purchase_date: day(-2),
    amount: "64.50",
    description: "FARMACIA",
    category_id: cat("Saúde"),
    payment_method: "pix",
    account_id: "acc_inter",
  });
  await post("/api/transactions", {
    purchase_date: day(-1),
    amount: "38.00",
    description: "PADARIA",
    category_id: cat("Alimentação"),
    payment_method: "benefit",
    account_id: "acc_vr",
    benefit_id: "ben_vr",
  });
  await post("/api/transactions", {
    purchase_date: day(-1),
    amount: "300.00",
    description: "PRESENTE PAIS",
    category_id: cat("Presente"),
    payment_method: "credit",
    card_id: "card_inter_pais",
  });
  await post("/api/settlements", {
    id: "set_ana",
    from_user_id: "ana",
    to_user_id: "eu",
    amount: "150.00",
    date: day(-1),
    month: month(0),
  });
  await post("/api/investments", {
    id: "inv_reserva",
    name: "Reserva CDB",
    institution_id: "acc_inter",
    type: "emergency_reserve",
    owners: { split_id: "split_casal" },
    goal_id: "goal_reserva",
    snapshots: [{ date: day(-30), balance: "20000.00" }],
  });
}

const PAGES: [string, string][] = [
  ["/", "resumo"],
  ["/projecao", "projecao"],
  ["/lancamentos", "lancamentos"],
  ["/contas-da-casa", "contas-da-casa"],
  ["/revisao", "revisao"],
  ["/a-receber", "a-receber"],
  ["/investimentos", "investimentos"],
  ["/perfis", "perfis"],
  ["/status", "status"],
  ["/configuracoes", "configuracoes"],
  ["/ajuda", "ajuda"],
];

const TABS = [
  "usuarios",
  "divisoes",
  "contas",
  "cartoes",
  "beneficios",
  "instituicoes",
  "categorias",
  "metas",
  "assinaturas",
  "recorrentes",
  "regras",
];

/** Collect problems the operator would hit; the tour fails if any shows up. */
function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500)
      problems.push(`api ${r.status()}: ${r.url()}`);
  });
  return problems;
}

async function shot(page: Page, name: string) {
  // Let queries settle and entrance animations finish before the picture.
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true });
}

async function setScheme(page: Page, scheme: "light" | "dark") {
  await page.evaluate((s) => {
    localStorage.setItem("expense-tracker-color-scheme", s);
  }, scheme);
}

test("r14_7 visual tour of every screen", async ({ page, request }) => {
  mkdirSync(SHOTS, { recursive: true });
  await seed(request);
  mkdirSync(join(INBOX, "faturas", "inter"), { recursive: true });
  copyFileSync(join(FIXTURES, "inter.pdf"), join(INBOX, "faturas", "inter", "fatura.pdf"));

  const problems = watch(page);
  await page.goto("/status");
  await page.getByRole("button", { name: "Varrer agora" }).click();
  await expect(page.getByText("faturas/inter/fatura.pdf")).toBeVisible();

  for (const scheme of ["light", "dark"] as const) {
    await page.goto("/");
    await setScheme(page, scheme);
    for (const [path, name] of PAGES) {
      await page.goto(path);
      await shot(page, `${scheme}-${name}`);
    }
    for (const tab of TABS) {
      await page.goto(`/cadastros?tab=${tab}`);
      await shot(page, `${scheme}-cadastros-${tab}`);
    }
  }

  // R14.18: another accent recolours the logo coin and the month banknote.
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("expense-tracker-accent", "ruby"));
  await page.goto("/");
  await shot(page, "light-resumo-ruby");
  await page.evaluate(() => localStorage.removeItem("expense-tracker-accent"));

  // Detail views the operator opens most.
  await page.goto("/");
  await setScheme(page, "light");
  await page.goto("/projecao");
  await page.getByRole("button", { name: /^Ver itens de/ }).first().click();
  await shot(page, "light-projecao-itens");
  await page.goto("/cadastros?tab=cartoes");
  await page.getByRole("button", { name: "Novo" }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(SHOTS, "light-cartao-novo.png") });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Editar Nubank" }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(SHOTS, "light-cartao-editar.png") });
  await page.keyboard.press("Escape");
  await page.goto("/cadastros?tab=usuarios");
  await page.getByRole("button", { name: "Editar Eu" }).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(SHOTS, "light-usuario-editar.png"), fullPage: true });
  await page.keyboard.press("Escape");

  // Installments: the plans tab (with the anticipated CELULAR) and the anticipate dialog.
  await page.goto("/lancamentos");
  await page.getByRole("tab", { name: /Parcelamentos/ }).click();
  await shot(page, "light-lancamentos-parcelamentos");
  const antecipar = page.getByRole("button", { name: /Antecipar/ }).first();
  if (await antecipar.isVisible()) {
    await antecipar.click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(SHOTS, "light-antecipar.png") });
    await page.keyboard.press("Escape");
  }

  // R14.6 responsiveness: tablet and small laptop widths; actions must stay reachable.
  for (const [w, h] of [
    [1024, 768],
    [768, 1024],
  ] as const) {
    await page.setViewportSize({ width: w, height: h });
    for (const [path, name] of [
      ["/revisao", "revisao"],
      ["/cadastros?tab=cartoes", "cadastros-cartoes"],
      ["/", "resumo"],
      ["/lancamentos", "lancamentos"],
      ["/projecao", "projecao"],
    ] as const) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(500);
      await page.screenshot({
        path: join(SHOTS, `w${w}-${name}.png`),
        fullPage: true,
      });
    }
  }

  expect(problems, problems.join("\n")).toEqual([]);
});

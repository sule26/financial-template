/**
 * End-to-end (docs/11 "e2e"): drop a synthetic invoice in the inbox → Status → Review → edit the
 * split → confirm → Summary shows the value → remove the file → it disappears → put it back →
 * the edited split comes back. Runs against the production image (scripts/e2e.sh).
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { copyFileSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const INBOX = process.env.INBOX_DIR ?? "/inbox";
const FIXTURES = process.env.FIXTURES_DIR ?? "/fixtures";
const TARGET = join(INBOX, "faturas", "inter", "fatura.pdf");

async function seed(api: APIRequestContext) {
  const post = async (path: string, data: unknown) => {
    const res = await api.post(path, { data });
    expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  };
  await post("/api/users", { id: "eu", name: "Eu" });
  await post("/api/users", { id: "ana", name: "Ana" });
  // default categories (R13.7) already exist on a fresh app: Casa, Saúde…
  const cats = (await (await api.get("/api/categories")).json()) as { id: string; name: string }[];
  expect(cats.map((c) => c.name)).toContain("Casa");
  const casa = cats.find((c) => c.name === "Casa")!.id;
  await post("/api/rules", {
    id: "rule_casa",
    priority: 100,
    when: { description_regex: "MERCADO|FARMACIA" },
    then: { category_id: casa },
  });
  await post("/api/cards", {
    id: "card_inter",
    name: "Inter",
    owners: [{ user_id: "eu", pct: "100" }],
    responsible_user_id: "eu",
    last_digits: ["1234"],
    billing_history: [{ from_month: "2020-01", closing_day: 8, due_day: 15 }],
    profile_id: "inter-fatura",
  });
}

async function scan(page: Page) {
  await page.goto("/status");
  await page.getByRole("button", { name: "Varrer agora" }).click();
}

test("inbox → review → confirm → summary → remove → restore edits", async ({ page, request }) => {
  await seed(request);

  // 1. drop the invoice and scan
  mkdirSync(join(INBOX, "faturas", "inter"), { recursive: true });
  copyFileSync(join(FIXTURES, "inter.pdf"), TARGET);
  await scan(page);
  await expect(page.getByText("faturas/inter/fatura.pdf")).toBeVisible();
  await expect(page.getByText("pendente revisão").first()).toBeVisible();

  // 2. review: the rule suggested "Casa"; give MERCADO a 50/50 split with Ana and confirm the file
  await page.getByRole("link", { name: "Revisão" }).click();
  await expect(page.getByText("MERCADO BOM")).toBeVisible();
  const mercado = page.getByRole("row").filter({ hasText: "MERCADO BOM" });
  await mercado.getByRole("button", { name: /^Divisão de MERCADO BOM/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Personalizada").click();
  await dialog.getByRole("button", { name: "Aplicar" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: /confirmar arquivo/i }).click();
  await expect(page.getByText("MERCADO BOM")).toHaveCount(0);

  // 3. summary of the current month shows the confirmed total
  await page.getByRole("link", { name: "Resumo" }).click();
  await expect(page.getByText("R$ 280,00").first()).toBeVisible();

  // 4. remove the file: data disappears
  rmSync(TARGET);
  await scan(page);
  await expect(page.getByText("faturas/inter/fatura.pdf")).toHaveCount(0);
  await page.getByRole("link", { name: "Resumo" }).click();
  await expect(page.getByText("R$ 280,00")).toHaveCount(0);

  // 5. put it back: it returns to review with my split restored (annotation by fingerprint)
  copyFileSync(join(FIXTURES, "inter.pdf"), TARGET);
  await scan(page);
  type Staged = { lines: { description: string; allocation_origin: string; allocations: unknown }[] }[];
  await expect
    .poll(async () => {
      const files = (await (await request.get("/api/review")).json()) as Staged;
      const line = files.flatMap((f) => f.lines).find((l) => l.description === "MERCADO BOM");
      return line ? { origin: line.allocation_origin, allocations: line.allocations } : null;
    })
    .toEqual({
      origin: "manual",
      allocations: [
        { user_id: "eu", pct: "50.00" },
        { user_id: "ana", pct: "50.00" },
      ],
    });

  // 6. dark mode toggle persists
  await page.getByText("Escuro", { exact: true }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", "dark");
});

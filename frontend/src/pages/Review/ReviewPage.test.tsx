import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ManifestEntry, ReviewFile, Transaction } from "../../api/types";
import { CATALOG, apiError, mockApi, renderPage } from "../../test/utils";
import { allocationText, originLabel, warningText } from "./labels";
import { ReviewPage } from "./ReviewPage";

// Generous async timeouts: the full suite runs many jsdom files in parallel.
configure({ asyncUtilTimeout: 10000 });
vi.setConfig({ testTimeout: 20000 });

function line(over: Partial<Transaction>): Transaction {
  return {
    id: "st1",
    fingerprint: "fp1",
    kind: "expense",
    source: { type: "import", sha256: "sha_b", path: "faturas/b.pdf", line: 1 },
    provisional: false,
    payment_method: "credit",
    card_id: "card_x",
    account_id: null,
    purchase_date: "2026-09-20",
    invoice_month: "2026-10",
    description: "Mercado",
    amount: "100.00",
    category_id: "cat_casa",
    installment: null,
    links: {},
    allocations: { split_id: "split_casal" },
    allocation_origin: "rule:r1",
    note: null,
    tag: null,
    review: { status: "pending", suggestions: [], warnings: [] },
    ...over,
  };
}

function file(over: Partial<ManifestEntry>): ManifestEntry {
  return {
    path: "faturas/b.pdf",
    sha256: "sha_b",
    kind: "fatura",
    format: "pdf",
    profile_id: "inter",
    card_id: "card_x",
    account_id: null,
    invoice_month: "2026-10",
    total: "150.00",
    amount_due: "150.00",
    open_invoice: false,
    status: "pending_review",
    error: null,
    warnings: [],
    supersedes_candidate: null,
    superseded_by: null,
    duplicate_of: null,
    paid_by_fingerprints: [],
    ...over,
  };
}

const LINES = [
  line({}),
  line({
    id: "st2",
    description: "Loja TV",
    amount: "50.00",
    category_id: null,
    installment: { plan_id: null, n: 2, of: 10 },
    review: {
      status: "needs_choice",
      warnings: ["category_missing"],
      suggestions: [
        {
          type: "choose_plan",
          target_id: null,
          score: null,
          data: {},
          candidates: ["plan1", "plan2"],
          rejected: false,
        },
        {
          type: "match_manual",
          target_id: "tx9",
          score: "0.9",
          data: {},
          candidates: [],
          rejected: true,
        },
      ],
    },
  }),
  line({
    id: "st3",
    description: "Antiga",
    review: {
      status: "overlap",
      suggestions: [
        {
          type: "invoice_payment",
          target_id: null,
          score: null,
          data: {},
          candidates: [],
          rejected: false,
        },
      ],
      warnings: [],
    },
  }),
];

const REVIEW: ReviewFile[] = [
  {
    file: file({
      warnings: ["sum_mismatch:-10.00", "unknown_card_hint:9999"],
      supersedes_candidate: "faturas/a.pdf",
    }),
    label: "pendente revisão",
    count: 3,
    lines: LINES,
  },
];

const PLANS = [
  { id: "plan1", description: "TV Sala" },
  { id: "plan2", description: "TV Quarto" },
];

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...CATALOG,
    "GET /api/review": REVIEW,
    "GET /api/installment-plans": PLANS,
    "GET /api/investments": [],
    "GET /api/transactions": [],
    "PATCH /api/review/lines/st1": {
      transaction: LINES[0],
      rule_suggestion: null,
    },
    "PATCH /api/review/lines/st2": {
      transaction: LINES[1],
      rule_suggestion: null,
    },
    "POST /api/review/confirm": { confirmed: 2 },
    "POST /api/sync/supersede/approve": { id: "j1", status: "done" },
    "POST /api/sync/supersede/reject": { id: "j2", status: "done" },
    ...extra,
  };
}

const patches = (calls: { method: string; path: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "PATCH");

describe("ReviewPage", () => {
  it("renders file header, warnings and highlighted lines", async () => {
    mockApi(routes());
    renderPage(<ReviewPage />, "/revisao");
    expect(await screen.findByText("faturas/b.pdf")).toBeInTheDocument();
    expect(
      await screen.findByText(/Fatura · Cartão X · out\/2026/),
    ).toBeInTheDocument();
    // sum excludes the overlapped line: 100 + 50
    expect(screen.getAllByText("R$ 150,00").length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText(
        /A soma das linhas difere do total do PDF em -R\$\s10,00/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Cartão final 9999 não cadastrado"),
    ).toBeInTheDocument();
    expect(screen.getByText("precisa escolher")).toBeInTheDocument();
    expect(screen.getByText("Sem categoria")).toBeInTheDocument();
    expect(screen.getByText("pagamento de fatura")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Divisão de Mercado: Casal" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("origem: regra").length).toBeGreaterThan(0);
  });

  it("shows empty and error states", async () => {
    mockApi({ ...routes(), "GET /api/review": [] });
    renderPage(<ReviewPage />, "/revisao");
    expect(await screen.findByText("Nada para revisar.")).toBeInTheDocument();
  });

  it("shows the load error", async () => {
    mockApi({
      ...routes(),
      "GET /api/review": () => apiError(500, "x", "quebrou"),
    });
    renderPage(<ReviewPage />, "/revisao");
    expect(await screen.findByRole("alert")).toHaveTextContent("quebrou");
  });

  it("overlap lines are not selectable nor confirmable", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    const box = await screen.findByRole("checkbox", {
      name: "Selecionar Antiga",
    });
    expect(box).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Confirmar Antiga" }),
    ).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: "Selecionar todas de faturas/b.pdf",
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "Confirmar selecionadas (2)" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/review/confirm")?.body).toEqual(
        {
          ids: ["st1", "st2"],
        },
      ),
    );
  });

  it("r5 accepts, rejects and chooses suggestions", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    await user.click(
      await screen.findByRole("button", {
        name: "Aceitar casa com lançamento manual em Loja TV",
      }),
    );
    await waitFor(() =>
      expect(patches(calls)[0]).toMatchObject({
        path: "/api/review/lines/st2",
        body: { accept: "match_manual" },
      }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "Rejeitar escolher parcelamento em Loja TV",
      }),
    );
    await waitFor(() =>
      expect(patches(calls)[1]?.body).toEqual({ reject: "choose_plan" }),
    );
    await user.click(
      screen.getByRole("textbox", {
        name: "escolher parcelamento para Loja TV",
      }),
    );
    await user.click(await screen.findByRole("option", { name: "TV Quarto" }));
    await waitFor(() =>
      expect(patches(calls)[2]?.body).toEqual({
        choose: { type: "choose_plan", target_id: "plan2" },
      }),
    );
  });

  it("r14_8 a card invoice line only offers spending kinds (and investment)", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    await user.click(
      await screen.findByRole("textbox", { name: "Tipo de Mercado" }),
    );
    const offered = (await screen.findAllByRole("option")).map(
      (o) => o.textContent,
    );
    expect(offered).toEqual([
      "Gasto",
      "Estorno",
      "Tarifa/juros",
      "Investimento",
    ]);
  });

  it("edits category, kind, note and split inline", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    await user.click(
      await screen.findByRole("textbox", { name: "Categoria de Loja TV" }),
    );
    await user.click(await screen.findByRole("option", { name: "Lazer" }));
    await waitFor(() =>
      expect(patches(calls)[0]?.body).toEqual({ category_id: "cat_lazer" }),
    );
    await user.click(screen.getByRole("textbox", { name: "Tipo de Mercado" }));
    await user.click(await screen.findByRole("option", { name: "Estorno" }));
    await waitFor(() =>
      expect(patches(calls)[1]?.body).toEqual({ kind: "refund" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Nota de Mercado" }),
      "feira",
    );
    await user.tab();
    await waitFor(() =>
      expect(patches(calls)[2]?.body).toEqual({ note: "feira" }),
    );

    await user.click(
      screen.getByRole("button", { name: "Divisão de Mercado: Casal" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Divisão — Mercado",
    });
    await user.click(within(dialog).getByRole("radio", { name: "100% para…" }));
    await user.click(within(dialog).getByRole("button", { name: "Aplicar" }));
    await waitFor(() =>
      expect(patches(calls)[3]?.body).toEqual({
        allocations: [{ user_id: "eu", pct: "100.00" }],
      }),
    );
  });

  it("r5_4 offers to create a rule when the API suggests one", async () => {
    const suggestion = {
      description_regex: "MERCADO",
      priority: 20,
      category_id: "cat_lazer",
      allocations: null,
    };
    const { calls } = mockApi(
      routes({
        "PATCH /api/review/lines/st2": {
          transaction: LINES[1],
          rule_suggestion: suggestion,
        },
        "POST /api/rules": { id: "rule1" },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    await user.click(
      await screen.findByRole("textbox", { name: "Categoria de Loja TV" }),
    );
    await user.click(await screen.findByRole("option", { name: "Lazer" }));
    await user.click(
      await screen.findByRole("button", { name: "Criar regra" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/rules")?.body).toEqual({
        priority: 20,
        enabled: true,
        when: { description_regex: "MERCADO" },
        then: { category_id: "cat_lazer", allocations: null },
      }),
    );
    expect(await screen.findByText("Regra criada.")).toBeVisible();
  });

  it("confirms one line or the whole file and shows cannot_confirm", async () => {
    let n = 0;
    const { calls } = mockApi(
      routes({
        "POST /api/review/confirm": () =>
          n++ === 0
            ? { confirmed: 1 }
            : apiError(422, "cannot_confirm", "st2: needs_choice"),
      }),
    );
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    await user.click(
      await screen.findByRole("button", { name: "Confirmar Mercado" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/api/review/confirm")?.body).toEqual(
        {
          ids: ["st1"],
        },
      ),
    );
    expect(await screen.findByText("1 linha(s) confirmada(s).")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Confirmar arquivo" }));
    expect(
      await screen.findByText("Não dá para confirmar: st2: needs_choice"),
    ).toBeInTheDocument();
    expect(
      calls.filter((c) => c.path === "/api/review/confirm")[1]?.body,
    ).toEqual({ path: "faturas/b.pdf" });
  });

  it("r3_11 approves or rejects a superseding invoice", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ReviewPage />, "/revisao");
    expect(
      await screen.findByText("Substituir a fatura faturas/a.pdf por esta?"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Aprovar substituição" }),
    );
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/sync/supersede/approve")?.body,
      ).toEqual({ path: "faturas/b.pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Recusar" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/sync/supersede/reject")?.body,
      ).toEqual({ path: "faturas/b.pdf" }),
    );
  });
});

describe("review labels", () => {
  it("translates warnings and origins", () => {
    const resolve = (_k: string, id: string) => `<${id}>`;
    expect(warningText("no_total")).toMatch(/não tem total/);
    expect(warningText("expected_installment_missing:p1:3", resolve)).toBe(
      'Parcela 3 de "<p1>" era esperada e não veio',
    );
    expect(warningText("unmatched_manual:tx1", resolve)).toMatch(/<tx1>/);
    expect(warningText("anticipation_not_happened:p1", resolve)).toMatch(
      /<p1>/,
    );
    expect(warningText("header_missing:total")).toMatch(/total/);
    expect(warningText("weird")).toBe("weird");
    expect(originLabel(null)).toBe("—");
    expect(originLabel("plan:p1")).toBe("parcelamento");
    // R14.6: an unknown code is never shown raw to the operator.
    expect(originLabel("xyz")).toBe("automática");
  });

  it("r14_6 origin of the owners is in plain language", () => {
    expect(originLabel("owners:account")).toBe("donos da conta");
    expect(originLabel("owners:card")).toBe("donos do cartão");
    expect(originLabel("owners:other")).toBe("donos");
  });

  it("keeps the remaining label checks", () => {
    expect(allocationText(null, {}, {})).toBe("padrão");
    expect(
      allocationText(
        [
          { user_id: "eu", pct: "60.00" },
          { user_id: "ana", pct: "40.00" },
        ],
        { eu: "Eu", ana: "Ana" },
        {},
      ),
    ).toBe("Eu 60% / Ana 40%");
  });
});

import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CATALOG, apiError, mockApi, renderPage } from "../../test/utils";
import { ProfilesPage, type ProfilesList } from "./ProfilesPage";

// Generous async timeouts: the full suite runs many jsdom files in parallel.
configure({ asyncUtilTimeout: 10000 });
vi.setConfig({ testTimeout: 20000 });

const LIST: ProfilesList = {
  profiles: [
    {
      id: "inter-fatura",
      name: "Inter fatura",
      kind: "fatura",
      format: "pdf",
      file: "inter-fatura.yaml",
      files: 3,
      errors: 1,
    },
  ],
  plugins: [{ id: "custom", kind: "extrato", file: "plugins/custom.py" }],
  errors: { "quebrado.yaml": "detect: field required" },
  examples: ["nubank-fatura"],
};

const YAML = "id: inter-fatura\nkind: fatura\n";

const TEST_RESULT = {
  valid: true,
  status: "ok",
  error: null,
  detected: true,
  header: {
    kind: "fatura",
    profile_id: "inter-fatura",
    total: "150.00",
    due_date: "2026-10-10",
    open_invoice: false,
    card_hint: null,
    warnings: [],
  },
  lines: [
    {
      index: 0,
      date: "2026-09-20",
      description: "MERCADO",
      amount: "100.00",
      installment_n: null,
      installment_of: null,
      card_hint: "1234",
      kind: null,
    },
    {
      index: 1,
      date: "2026-09-21",
      description: "LOJA TV",
      amount: "40.00",
      installment_n: 2,
      installment_of: 10,
      card_hint: null,
      kind: null,
    },
  ],
  ignored: ["Total da fatura 150,00"],
  unrecognized: ["21/09 LINHA ESTRANHA 10,00"],
};

const routes = (extra: Record<string, unknown> = {}) => ({
  ...CATALOG,
  "GET /api/profiles": LIST,
  "GET /api/profiles/inter-fatura": { id: "inter-fatura", yaml: YAML },
  "GET /api/sync/status": {
    files: [{ path: "faturas/a.pdf" }],
    last_scan: null,
    last_report: null,
    jobs: [],
  },
  "POST /api/profiles/validate": { valid: false, error: "detect missing" },
  "POST /api/profiles/test": TEST_RESULT,
  "POST /api/profiles/raw-text": { pages: ["PAGINA UM", "PAGINA DOIS"] },
  "PUT /api/profiles/inter-fatura": { saved: "inter-fatura", job: null },
  ...extra,
});

async function editInter(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    await screen.findByRole("button", { name: "Editar perfil inter-fatura" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "YAML do perfil" })).toHaveValue(
      YAML,
    ),
  );
}

async function chooseFile(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    screen.getByRole("textbox", { name: "Arquivo da pasta de entrada" }),
  );
  await user.click(
    await screen.findByRole("option", { name: "faturas/a.pdf" }),
  );
}

async function openAdvanced(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    await screen.findByRole("button", { name: "Modo avançado" }),
  );
}

describe("ProfilesPage — simple mode (R13.9)", () => {
  it("r13_9 shows supported banks as cards, with built-in examples", async () => {
    mockApi(routes());
    renderPage(<ProfilesPage />, "/perfis");
    const inter = await screen.findByRole("article", { name: "Inter fatura" });
    expect(inter).toHaveTextContent("Fatura de cartão · PDF");
    expect(inter).toHaveTextContent("3 arquivos lidos");
    expect(inter).toHaveTextContent("1 com erro");
    expect(within(inter).queryByText("embutido")).toBeNull();
    const nubank = screen.getByRole("article", { name: "nubank-fatura" });
    expect(within(nubank).getByText("embutido")).toBeInTheDocument();
    expect(nubank).toHaveTextContent("0 arquivos lidos");
    expect(screen.getByText("quebrado.yaml")).toBeInTheDocument();
    // The steps for a missing bank are always visible.
    expect(
      screen.getByRole("region", { name: "Meu banco não está na lista" }),
    ).toHaveTextContent("Modo avançado");
  });

  it("r13_9 tests a file with the detected profile and explains a match", async () => {
    const { calls } = mockApi(
      routes({
        "GET /api/sync/status": {
          files: [{ path: "faturas/a.pdf", profile_id: "inter-fatura" }],
          last_scan: null,
          last_report: null,
          jobs: [],
        },
        "POST /api/profiles/test": {
          ...TEST_RESULT,
          header: { ...TEST_RESULT.header, total: "140.00" },
          unrecognized: [],
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await user.click(
      await screen.findByRole("textbox", { name: "Arquivo para testar" }),
    );
    await user.click(
      await screen.findByRole("option", { name: "faturas/a.pdf" }),
    );
    expect(
      await screen.findByText("Perfil reconhecido: Inter fatura."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Testar arquivo" }));
    const result = await screen.findByText(/Lemos 2 lançamentos/);
    expect(result).toHaveTextContent(
      "Lemos 2 lançamentos, soma R$ 140,00, total do banco R$ 140,00 — bate ✓",
    );
    expect(
      screen.getByText("Todas as linhas com valor foram entendidas."),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/profiles/test")?.body).toEqual({
      yaml: YAML,
      path: "faturas/a.pdf",
    });
  });

  it("r13_9 explains a mismatch and lists lines it did not understand", async () => {
    mockApi(
      routes({
        "GET /api/sync/status": {
          files: [{ path: "faturas/a.pdf", profile_id: "inter-fatura" }],
          last_scan: null,
          last_report: null,
          jobs: [],
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await user.click(
      await screen.findByRole("textbox", { name: "Arquivo para testar" }),
    );
    await user.click(
      await screen.findByRole("option", { name: "faturas/a.pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Testar arquivo" }));
    expect(await screen.findByText(/Lemos 2 lançamentos/)).toHaveTextContent(
      "soma R$ 140,00, total do banco R$ 150,00 — não bate: diferença R$ 10,00",
    );
    expect(
      screen.getByText("Linhas que não entendemos (1)"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("21/09 LINHA ESTRANHA 10,00").length).toBe(1);
  });

  it("r13_9 falls back to the built-in example and handles no detection, no total and errors", async () => {
    const { calls } = mockApi(
      routes({
        "GET /api/sync/status": {
          files: [{ path: "faturas/b.pdf", profile_id: null }],
          last_scan: null,
          last_report: null,
          jobs: [],
        },
        "GET /api/profiles/examples/nubank-fatura": {
          id: "nubank-fatura",
          yaml: "id: nubank-fatura\n",
        },
        "POST /api/profiles/test": {
          valid: true,
          status: "ok",
          error: "aviso do leitor",
          header: null,
          lines: [],
          unrecognized: [],
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await user.click(
      await screen.findByRole("textbox", { name: "Arquivo para testar" }),
    );
    await user.click(
      await screen.findByRole("option", { name: "faturas/b.pdf" }),
    );
    expect(
      await screen.findByText(/Nenhum perfil reconheceu este arquivo/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Testar arquivo" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("textbox", { name: "Perfil" }));
    await user.click(
      await screen.findByRole("option", { name: "nubank-fatura" }),
    );
    await user.click(screen.getByRole("button", { name: "Testar arquivo" }));
    expect(await screen.findByText(/Lemos 0 lançamentos/)).toHaveTextContent(
      "o documento não informa o total para conferir",
    );
    expect(screen.getByText("aviso do leitor")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/profiles/test")?.body).toEqual({
      yaml: "id: nubank-fatura\n",
      path: "faturas/b.pdf",
    });
  });

  it("r13_9 tries the other source when the profile YAML is not found, and shows errors", async () => {
    mockApi(
      routes({
        "GET /api/profiles": {
          ...LIST,
          // A newer backend lists built-in examples among the profiles.
          profiles: [
            ...LIST.profiles,
            {
              id: "nubank-fatura",
              name: "Nubank",
              kind: "fatura",
              format: "pdf",
              file: "examples/nubank-fatura.yaml",
              files: 1,
              errors: 0,
            },
          ],
          examples: [{ id: "nubank-fatura", name: "Nubank" }],
        },
        "GET /api/sync/status": {
          files: [{ path: "faturas/n.pdf", profile_id: "nubank-fatura" }],
          last_scan: null,
          last_report: null,
          jobs: [],
        },
        "GET /api/profiles/examples/nubank-fatura": {
          id: "nubank-fatura",
          yaml: "id: nubank-fatura\n",
        },
        "POST /api/profiles/test": { valid: false, error: "bad yaml" },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    const card = await screen.findByRole("article", { name: "Nubank" });
    expect(within(card).getByText("embutido")).toBeInTheDocument();
    expect(card).toHaveTextContent("1 arquivo lido");
    await user.click(
      screen.getByRole("textbox", { name: "Arquivo para testar" }),
    );
    await user.click(
      await screen.findByRole("option", { name: "faturas/n.pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Testar arquivo" }));
    expect(await screen.findByText("O perfil tem um erro")).toBeInTheDocument();
    expect(screen.getByText("bad yaml")).toBeInTheDocument();
  });

  it("r13_9 shows a load failure of the profile YAML", async () => {
    mockApi(
      routes({
        "GET /api/profiles/inter-fatura": () =>
          apiError(500, "x", "disco cheio"),
        "GET /api/sync/status": {
          files: [{ path: "faturas/a.pdf", profile_id: "inter-fatura" }],
          last_scan: null,
          last_report: null,
          jobs: [],
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await user.click(
      await screen.findByRole("textbox", { name: "Arquivo para testar" }),
    );
    await user.click(
      await screen.findByRole("option", { name: "faturas/a.pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Testar arquivo" }));
    expect(await screen.findByText("disco cheio")).toBeInTheDocument();
  });
});

describe("ProfilesPage — advanced mode", () => {
  it("lists profiles, plugins and examples", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    expect(
      await screen.findByRole("cell", { name: /Inter fatura/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/custom \(extrato\)/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Usar exemplo nubank-fatura" }),
    ).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    mockApi(
      routes({
        "GET /api/profiles": {
          profiles: [],
          plugins: [],
          errors: {},
          examples: [],
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    expect(
      await screen.findByText("Nenhum banco configurado ainda."),
    ).toBeInTheDocument();
    await openAdvanced(user);
    expect(
      await screen.findByText(/Nenhum perfil em profiles/),
    ).toBeInTheDocument();
  });

  it("shows the load error", async () => {
    mockApi(
      routes({ "GET /api/profiles": () => apiError(500, "x", "sem perfis") }),
    );
    renderPage(<ProfilesPage />, "/perfis");
    expect(await screen.findByRole("alert")).toHaveTextContent("sem perfis");
  });

  it("loads, validates and saves a profile", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    await editInter(user);
    expect(screen.getByRole("textbox", { name: /ID do perfil/ })).toHaveValue(
      "inter-fatura",
    );
    await user.click(screen.getByRole("button", { name: "Validar" }));
    expect(
      await screen.findByText("YAML inválido: detect missing"),
    ).toBeVisible();
    expect(
      calls.find((c) => c.path === "/api/profiles/validate")?.body,
    ).toEqual({
      yaml: YAML,
    });
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(
        calls.find(
          (c) => c.method === "PUT" && c.path === "/api/profiles/inter-fatura",
        )?.body,
      ).toEqual({ yaml: YAML }),
    );
    expect(await screen.findByText(/Perfil inter-fatura salvo/)).toBeVisible();
  });

  it("r4_3 tests the profile and highlights unrecognized lines", async () => {
    const { calls } = mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    await editInter(user);
    await chooseFile(user);
    await user.click(screen.getByRole("button", { name: "Testar" }));
    expect(
      await screen.findByText("Linhas NÃO reconhecidas (1)"),
    ).toBeInTheDocument();
    expect(screen.getByText("21/09 LINHA ESTRANHA 10,00")).toBeInTheDocument();
    expect(screen.getByText("Linhas reconhecidas (2)")).toBeInTheDocument();
    expect(screen.getByText("MERCADO")).toBeInTheDocument();
    expect(screen.getByText("2/10")).toBeInTheDocument();
    expect(screen.getByText("Total da fatura 150,00")).toBeInTheDocument();
    expect(screen.getByText("não confere")).toBeInTheDocument();
    expect(screen.getByText("10/10/2026")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/profiles/test")?.body).toEqual({
      yaml: YAML,
      path: "faturas/a.pdf",
    });
  });

  it("shows the raw text and invalid test results", async () => {
    const { calls } = mockApi(
      routes({
        "POST /api/profiles/test": { valid: false, error: "bad yaml" },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    await user.click(
      await screen.findByRole("button", { name: "Novo perfil" }),
    );
    await chooseFile(user);
    await user.click(screen.getByRole("button", { name: "Ver texto bruto" }));
    expect(await screen.findByText("PAGINA DOIS")).toBeInTheDocument();
    expect(
      calls.find((c) => c.path === "/api/profiles/raw-text")?.body,
    ).toEqual({
      path: "faturas/a.pdf",
    });
    await user.click(screen.getByRole("button", { name: "Testar" }));
    expect(await screen.findByText("YAML inválido: bad yaml")).toBeVisible();
  });

  it("r4_3 loads an example profile into the editor", async () => {
    const { calls } = mockApi(
      routes({
        "GET /api/profiles/examples/nubank-fatura": {
          id: "nubank-fatura",
          yaml: "id: nubank-fatura\n",
        },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    await user.click(
      await screen.findByRole("button", { name: "Usar exemplo nubank-fatura" }),
    );
    await waitFor(() =>
      expect(
        calls.some((c) => c.path === "/api/profiles/examples/nubank-fatura"),
      ).toBe(true),
    );
  });

  it("explains when an example cannot be loaded", async () => {
    mockApi(routes());
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    await user.click(
      await screen.findByRole("button", { name: "Usar exemplo nubank-fatura" }),
    );
    expect(
      await screen.findByText(/Não foi possível carregar o exemplo/),
    ).toBeInTheDocument();
  });

  it("shows a valid validation result", async () => {
    mockApi(
      routes({
        "POST /api/profiles/validate": { valid: true, id: "meu-banco-fatura" },
      }),
    );
    const user = userEvent.setup();
    renderPage(<ProfilesPage />, "/perfis");
    await openAdvanced(user);
    await user.click(
      await screen.findByRole("button", { name: "Novo perfil" }),
    );
    await user.click(screen.getByRole("button", { name: "Validar" }));
    expect(
      await screen.findByText("YAML válido (id meu-banco-fatura)."),
    ).toBeVisible();
  });
});

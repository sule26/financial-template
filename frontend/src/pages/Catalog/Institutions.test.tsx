import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Institution } from "../../api/types";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { CatalogPage } from "./CatalogPage";
import { checkInstitution, INSTITUTION_TYPE_LABELS } from "./InstitutionsTab";

const open = () => renderPage(<CatalogPage />, "/cadastros?tab=instituicoes");

const XP: Institution = { id: "ins_xp", name: "XP", type: "broker" };

describe("Institutions tab", () => {
  it("r13_15 lists institutions with the Portuguese type label", async () => {
    mockApi({
      ...CATALOG,
      "GET /api/institutions": [
        XP,
        { id: "ins_prev", name: "Brasilprev", type: "pension" },
      ],
    });
    open();
    expect(
      await screen.findByRole("tab", { name: "Instituições", selected: true }),
    ).toBeInTheDocument();
    const row = (await screen.findByText("Brasilprev")).closest(
      "tr",
    ) as HTMLElement;
    expect(within(row).getByText("Previdência")).toBeInTheDocument();
    expect(
      within(screen.getByText("XP").closest("tr") as HTMLElement).getByText(
        "Corretora",
      ),
    ).toBeInTheDocument();
  });

  it("r13_15 creates an institution with a trimmed name", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/institutions": [],
      "POST /api/institutions": (body: unknown) => ({
        ...(body as object),
        id: "ins_new",
      }),
    });
    open();
    expect(
      await screen.findByText("Nenhuma instituição cadastrada."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Novo/ }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/^Nome/), "  Binance ");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Tipo"),
      "exchange",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        name: "Binance",
        type: "exchange",
      }),
    );
  });

  it("r13_15 edits an institution and shows a readable 409 when deleting one in use", async () => {
    const { calls } = mockApi({
      ...CATALOG,
      "GET /api/institutions": [XP],
      "PUT /api/institutions/ins_xp": (body: unknown) => body,
      "DELETE /api/institutions/ins_xp": () =>
        new Response(
          JSON.stringify({
            error: {
              code: "in_use",
              message: "Instituição em uso",
              details: {
                referenced_by: ["investments/inv_a", "investments/inv_b"],
              },
            },
          }),
          { status: 409 },
        ),
    });
    open();
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar XP" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Tipo")).toHaveValue("broker");
    await userEvent.selectOptions(
      within(dialog).getByLabelText("Tipo"),
      "other",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Salvar" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
        name: "XP",
        type: "other",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole("button", { name: "Excluir XP" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Confirmar exclusão" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não é possível excluir: está vinculado a 2 itens (2 investimentos)",
    );
  });

  it("r13_15 type labels and validation", () => {
    expect(Object.values(INSTITUTION_TYPE_LABELS)).toEqual([
      "Corretora",
      "Exchange",
      "Previdência",
      "Banco",
      "Outra",
    ]);
    expect(checkInstitution({ name: " ", type: "bank" })).toBe(
      "Nome: obrigatório",
    );
    expect(checkInstitution({ name: "Inter", type: "bank" })).toBeNull();
  });
});

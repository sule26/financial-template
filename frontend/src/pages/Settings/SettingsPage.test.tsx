import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../../App";
import { CATALOG, mockApi, renderPage } from "../../test/utils";
import { SettingsPage } from "./SettingsPage";

describe("SettingsPage", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-accent");
  });

  it("r13_10 changes the accent without reloading and remembers it", async () => {
    mockApi({});
    const user = userEvent.setup();
    renderPage(<SettingsPage />);
    await waitFor(() =>
      expect(document.documentElement).toHaveAttribute("data-accent", "jade"),
    );
    expect(screen.getByRole("radio", { name: /Esmeralda/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: /Oceano/ }));
    await waitFor(() =>
      expect(document.documentElement).toHaveAttribute("data-accent", "ocean"),
    );
    expect(localStorage.getItem("expense-tracker-accent")).toBe("ocean");
    expect(screen.getByRole("radio", { name: /Oceano/ })).toBeChecked();
    expect(document.getElementById("et-accent-vars")?.textContent).toContain(
      'data-accent="ocean"',
    );
    // The theme toggle lives here too.
    await user.click(screen.getByText("Escuro"));
    await waitFor(() =>
      expect(document.documentElement).toHaveAttribute(
        "data-mantine-color-scheme",
        "dark",
      ),
    );
  });

  it("r13_10 starts with the stored accent and ignores invalid values", async () => {
    mockApi({});
    localStorage.setItem("expense-tracker-accent", "ruby");
    const { unmount } = renderPage(<SettingsPage />);
    expect(screen.getByRole("radio", { name: /Rubi/ })).toBeChecked();
    await waitFor(() =>
      expect(document.documentElement).toHaveAttribute("data-accent", "ruby"),
    );
    unmount();
    localStorage.setItem("expense-tracker-accent", "neon");
    renderPage(<SettingsPage />);
    expect(screen.getByRole("radio", { name: /Esmeralda/ })).toBeChecked();
  });

  it("r13_10 is reachable from the menu at /configuracoes", async () => {
    mockApi({ ...CATALOG });
    renderPage(<App />, "/configuracoes");
    expect(
      await screen.findByRole("heading", { name: "Configurações" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /Configurações/ }).length,
    ).toBeGreaterThan(0);
  });
});

describe("Pessoa padrão (R14.25)", () => {
  beforeEach(() => localStorage.clear());

  it("r14_25 the default people chosen here are remembered", async () => {
    mockApi({ ...CATALOG });
    const user = userEvent.setup();
    renderPage(<SettingsPage />);
    await user.click(
      await screen.findByRole("textbox", { name: "Mostrar por padrão" }),
    );
    await user.click(await screen.findByRole("option", { name: "Eu" }));
    await user.click(await screen.findByRole("option", { name: "Ana" }));
    await waitFor(() =>
      expect(
        JSON.parse(
          localStorage.getItem("expense-tracker-default-people") ?? "[]",
        ),
      ).toEqual(["eu", "ana"]),
    );
  });

  it("r14_25 Resumo opens with the default people (their parts summed)", async () => {
    localStorage.setItem(
      "expense-tracker-default-people",
      JSON.stringify(["eu", "ana"]),
    );
    const { calls } = mockApi({ ...CATALOG });
    renderPage(<App />, "/");
    await waitFor(() =>
      expect(calls.map((c) => c.path)).toContain(
        "/api/reports/summary?month=2026-10&user_id=eu%2Cana",
      ),
    );
  });
});

describe("Idioma (R14.13)", () => {
  beforeEach(() => localStorage.clear());

  it("r14_13 switching to English translates the shell and formats, and is remembered", async () => {
    mockApi({ ...CATALOG });
    const user = userEvent.setup();
    renderPage(<App />, "/configuracoes");
    await user.click(await screen.findByRole("radio", { name: "English" }));
    expect(
      await screen.findByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Summary").length).toBeGreaterThan(0);
    expect(localStorage.getItem("expense-tracker-language")).toBe("en");
    expect(document.documentElement).toHaveAttribute("lang", "en");
    await user.click(
      await screen.findByRole("radio", { name: "Português (Brasil)" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Configurações" }),
    ).toBeInTheDocument();
  });
});

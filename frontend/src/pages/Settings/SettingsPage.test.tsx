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

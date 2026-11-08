import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { Providers } from "../providers";
import { isActive, NAV_ITEMS } from "./Layout";

function renderApp(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("[]")),
  );
  return render(
    <Providers initialPath={path} today={new Date(2026, 9, 12)}>
      <App />
    </Providers>,
  );
}

describe("Layout", () => {
  it("isActive matches the root exactly and sections by prefix", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/ajuda")).toBe(false);
    expect(isActive("/lancamentos", "/lancamentos")).toBe(true);
    expect(NAV_ITEMS.map((i) => i.label)).toContain("Perfis de banco");
  });

  it("marks the current page in the grouped sidebar", () => {
    renderApp("/ajuda");
    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    const current = within(nav).getByRole("link", { name: "Ajuda" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(
      within(nav).getByRole("link", { name: "Resumo" }),
    ).not.toHaveAttribute("aria-current");
    expect(within(nav).getByText("Configuração")).toBeInTheDocument();
    expect(nav.querySelector(".et-nav__marker")).not.toBeNull();
  });

  it("opens the mobile drawer with the navigation and the theme toggle, and closes on navigate", async () => {
    const user = userEvent.setup();
    renderApp("/ajuda");
    await user.click(screen.getByRole("button", { name: "Menu" }));
    const drawer = await screen.findByRole("navigation", {
      name: "Navegação (menu)",
    });
    expect(
      within(drawer).getByRole("link", { name: "Status" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Escuro").length).toBeGreaterThan(1);
    await user.click(within(drawer).getByRole("link", { name: "Status" }));
    expect(
      await screen.findByRole("heading", { level: 2, name: "Status" }),
    ).toBeInTheDocument();
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeToggle } from "../components/ThemeToggle";
import { mockApi, renderPage } from "./utils";

describe("theme", () => {
  it("r1_14 switches between light, dark and system and remembers the choice", async () => {
    mockApi({});
    localStorage.clear();
    const user = userEvent.setup();
    renderPage(<ThemeToggle />);
    await user.click(screen.getByText("Escuro"));
    await waitFor(() =>
      expect(document.documentElement).toHaveAttribute(
        "data-mantine-color-scheme",
        "dark",
      ),
    );
    expect(localStorage.getItem("expense-tracker-color-scheme")).toBe("dark");
    await user.click(screen.getByText("Claro"));
    await waitFor(() =>
      expect(document.documentElement).toHaveAttribute(
        "data-mantine-color-scheme",
        "light",
      ),
    );
    await user.click(screen.getByText("Sistema"));
    expect(localStorage.getItem("expense-tracker-color-scheme")).toBe("auto");
  });
});

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderPage } from "../../test/utils";
import { HelpPage } from "./HelpPage";

describe("HelpPage", () => {
  it("r1_8 shows 'Como usar' and 'Como modificar' sections", async () => {
    renderPage(<HelpPage />, "/ajuda");
    expect(
      screen.getByRole("heading", { name: "Como usar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Como modificar" }),
    ).toBeInTheDocument();
    const bank = screen.getByRole("button", {
      name: "Como adicionar um banco",
    });
    expect(bank).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(bank);
    expect(bank).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/secrets\/pdf-passwords.yaml/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Comandos \(Taskfile/ }),
    );
    expect(screen.getByText("task --list")).toBeInTheDocument();
  });
});

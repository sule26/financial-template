import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { addMonths, formatMonth, monthOf } from "../hooks/month";
import { Providers } from "../providers";

describe("month helpers", () => {
  it("monthOf / addMonths / formatMonth", () => {
    expect(monthOf(new Date(2026, 9, 12))).toBe("2026-10");
    expect(addMonths("2026-10", 3)).toBe("2027-01");
    expect(addMonths("2026-01", -1)).toBe("2025-12");
    expect(formatMonth("2026-10")).toBe("out/2026");
  });
});

describe("app shell", () => {
  it("r1_13 opens on the current month and allows navigating to past months", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("[]")),
    );
    render(
      <Providers initialPath="/ajuda" today={new Date(2026, 9, 12)}>
        <App />
      </Providers>,
    );
    expect(screen.getByTestId("selected-month")).toHaveTextContent("out/2026");
    expect(screen.queryByText("voltar ao mês atual")).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Mês anterior"));
    expect(screen.getByTestId("selected-month")).toHaveTextContent("set/2026");
    await userEvent.click(screen.getByText("voltar ao mês atual"));
    expect(screen.getByTestId("selected-month")).toHaveTextContent("out/2026");
    await userEvent.click(screen.getByLabelText("Próximo mês"));
    expect(screen.getByTestId("selected-month")).toHaveTextContent("nov/2026");
  });

  it("renders navigation", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("[]")),
    );
    render(
      <Providers initialPath="/nada">
        <App />
      </Providers>,
    );
    expect(screen.getByRole("link", { name: "Revisão" })).toBeInTheDocument();
    expect(screen.getByText("Página não encontrada")).toBeInTheDocument();
  });
});

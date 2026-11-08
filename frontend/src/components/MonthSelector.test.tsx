import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderPage } from "../test/utils";
import { MonthSelector } from "./MonthSelector";

const month = () => screen.getByTestId("selected-month");
const openPicker = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole("button", { name: /^Escolher mês/ }));
  return screen.findByRole("dialog", { name: /^Escolher mês/ });
};

describe("MonthSelector", () => {
  it("r1_13 picks a month of another year from the grid and returns to the current one", async () => {
    const user = userEvent.setup();
    renderPage(<MonthSelector />);
    expect(month()).toHaveTextContent("out/2026");

    const picker = await openPicker(user);
    expect(within(picker).getByTestId("picker-year")).toHaveTextContent("2026");
    const current = within(picker).getByRole("button", {
      name: "outubro de 2026",
    });
    expect(current).toHaveAttribute("aria-current", "date");
    expect(current).toHaveAttribute("aria-pressed", "true");

    await user.click(
      within(picker).getByRole("button", { name: "Ano anterior" }),
    );
    await user.click(
      within(picker).getByRole("button", { name: "Ano anterior" }),
    );
    expect(within(picker).getByTestId("picker-year")).toHaveTextContent("2024");
    expect(
      within(picker).getByRole("group", { name: "Meses de 2024" }),
    ).toBeInTheDocument();
    await user.click(
      within(picker).getByRole("button", { name: "março de 2024" }),
    );
    expect(month()).toHaveTextContent("mar/2024");
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: /^Escolher mês/ }),
      ).not.toBeInTheDocument(),
    );

    // Reopening starts on the selected year, with that month pressed.
    const again = await openPicker(user);
    expect(within(again).getByTestId("picker-year")).toHaveTextContent("2024");
    expect(
      within(again).getByRole("button", { name: "março de 2024" }),
    ).toHaveAttribute("aria-pressed", "true");
    await user.click(
      within(again).getByRole("button", { name: "Próximo ano" }),
    );
    expect(within(again).getByTestId("picker-year")).toHaveTextContent("2025");
    await user.click(
      within(again).getByRole("button", { name: "ir para out/2026" }),
    );
    expect(month()).toHaveTextContent("out/2026");

    await user.click(screen.getByLabelText("Próximo mês"));
    expect(month()).toHaveTextContent("nov/2026");
    await user.click(screen.getByText("voltar ao mês atual"));
    expect(month()).toHaveTextContent("out/2026");
    expect(screen.queryByText("voltar ao mês atual")).not.toBeInTheDocument();
  });

  it("r13_8 keyboard: arrows change the month and Home returns to the current one", async () => {
    const user = userEvent.setup();
    renderPage(<MonthSelector />);
    screen.getByLabelText("Mês anterior").focus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(month()).toHaveTextContent("ago/2026");
    await user.keyboard("{ArrowRight}");
    expect(month()).toHaveTextContent("set/2026");
    await user.keyboard("{Home}");
    expect(month()).toHaveTextContent("out/2026");
    // Other keys are ignored.
    await user.keyboard("a");
    expect(month()).toHaveTextContent("out/2026");
  });

  it("r1_13 arrow keys inside the open grid do not move the selected month", async () => {
    const user = userEvent.setup();
    renderPage(<MonthSelector />);
    const picker = await openPicker(user);
    within(picker).getByRole("button", { name: "janeiro de 2026" }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(month()).toHaveTextContent("out/2026");
  });
});

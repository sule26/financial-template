import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { mockApi, pickDate, pickMonth, renderPage } from "../../test/utils";
import { DateField } from "./DateField";
import { MonthField } from "./MonthField";

function MonthHarness({
  initial,
  onValue,
  required,
}: {
  initial: string;
  onValue: (v: string) => void;
  required?: boolean;
}) {
  const [v, setV] = useState(initial);
  return (
    <MonthField
      label="Mês alvo"
      required={required}
      value={v}
      onChange={(next) => {
        setV(next);
        onValue(next);
      }}
    />
  );
}

function DateHarness({
  initial,
  onValue,
}: {
  initial: string;
  onValue: (v: string) => void;
}) {
  const [v, setV] = useState(initial);
  return (
    <DateField
      label="Data"
      value={v}
      onChange={(next) => {
        setV(next);
        onValue(next);
      }}
    />
  );
}

describe("MonthField / DateField", () => {
  it("r13_13 month picker shows MMM/YYYY and emits YYYY-MM", async () => {
    mockApi({});
    const onValue = vi.fn();
    const user = userEvent.setup();
    renderPage(<MonthHarness initial="2026-01" onValue={onValue} />);
    const field = screen.getByLabelText("Mês alvo");
    expect(field).toHaveTextContent("jan/2026");
    await pickMonth(user, field, "2024-11");
    expect(onValue).toHaveBeenLastCalledWith("2024-11");
    expect(screen.getByLabelText("Mês alvo")).toHaveTextContent("nov/2024");
    // Optional: a clear button empties the value.
    await user.click(screen.getByLabelText("Limpar Mês alvo"));
    expect(onValue).toHaveBeenLastCalledWith("");
  });

  it("r13_13 required month picker has no clear button", async () => {
    mockApi({});
    renderPage(<MonthHarness initial="2026-01" onValue={vi.fn()} required />);
    expect(screen.queryByLabelText("Limpar Mês alvo")).not.toBeInTheDocument();
  });

  it("r13_13 date picker shows DD/MM/YYYY and emits YYYY-MM-DD", async () => {
    mockApi({});
    const onValue = vi.fn();
    const user = userEvent.setup();
    renderPage(<DateHarness initial="" onValue={onValue} />);
    const field = screen.getByLabelText("Data");
    await pickDate(user, field, "2031-02-28");
    expect(onValue).toHaveBeenLastCalledWith("2031-02-28");
    expect(screen.getByLabelText("Data")).toHaveTextContent("28/02/2031");
  });
});

import { MantineProvider } from "@mantine/core";
import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { mockApi, renderPage } from "../../test/utils";
import { theme } from "../../theme";
import { ChartTooltip } from "./ChartTooltip";
import { CHART_PALETTE, useChartTheme } from "./charts";
import { ContentSkeleton } from "./ContentSkeleton";
import { EmptyState } from "./EmptyState";
import { BrandMark, Guilloche, rosettePath, wavePath } from "./Guilloche";
import { MoneyText } from "./MoneyText";
import { prefersMotion, useCountUp, usePrefersMotion } from "./motion";
import { PageHeader } from "./PageHeader";
import { Panel } from "./Panel";
import { deltaText, StatCard } from "./StatCard";
import { StatusBadge, toneFromColor } from "./StatusBadge";

const originalMatchMedia = window.matchMedia;

/** Pretend the OS says "motion is fine" and drive requestAnimationFrame by hand. */
function allowMotion() {
  const listeners: (() => void)[] = [];
  window.matchMedia = ((query: string) => ({
    matches: query.includes("no-preference"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: (_: string, cb: () => void) => listeners.push(cb),
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  let now = 0;
  const frames: FrameRequestCallback[] = [];
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    frames.push(cb);
    return frames.length;
  });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
  return {
    listeners,
    /** Advance the clock and run the queued frames. */
    step(ms: number) {
      now += ms;
      const queued = frames.splice(0);
      act(() => queued.forEach((f) => f(now)));
    },
  };
}

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe("motion", () => {
  it("r13_1 motion is off in jsdom (matchMedia never matches no-preference)", () => {
    expect(prefersMotion()).toBe(false);
    const { result } = renderHook(() => usePrefersMotion());
    expect(result.current).toBe(false);
  });

  it("is off when matchMedia is missing or throws", () => {
    // @ts-expect-error simulate an old browser
    window.matchMedia = undefined;
    expect(prefersMotion()).toBe(false);
    window.matchMedia = (() => {
      throw new Error("boom");
    }) as unknown as typeof window.matchMedia;
    expect(prefersMotion()).toBe(false);
  });

  it("is on when the OS has no preference", () => {
    allowMotion();
    expect(prefersMotion()).toBe(true);
  });

  it("follows OS changes", () => {
    const motion = allowMotion();
    const { result } = renderHook(() => usePrefersMotion());
    expect(result.current).toBe(true);
    window.matchMedia = originalMatchMedia; // now "reduce" (stub: nothing matches)
    act(() => motion.listeners.forEach((cb) => cb()));
    expect(result.current).toBe(false);
  });

  it("useCountUp returns the target immediately under reduced motion", () => {
    const { result, rerender } = renderHook(({ v }) => useCountUp(v), {
      initialProps: { v: 1500 },
    });
    expect(result.current).toBe(1500);
    rerender({ v: 42 });
    expect(result.current).toBe(42);
  });

  it("useCountUp animates from 0 to the target when motion is allowed", () => {
    const motion = allowMotion();
    const { result, rerender } = renderHook(({ v }) => useCountUp(v, 100), {
      initialProps: { v: 1000 },
    });
    expect(result.current).toBe(0);
    motion.step(50);
    expect(result.current).toBeGreaterThan(0);
    expect(result.current).toBeLessThan(1000);
    motion.step(60);
    expect(result.current).toBe(1000);
    // a new target continues from the current value
    rerender({ v: 2000 });
    motion.step(200);
    expect(result.current).toBe(2000);
  });
});

describe("MoneyText", () => {
  it("formats with tabular figures and colours only negatives by default", () => {
    render(
      <>
        <MoneyText value="1500.00" data-testid="pos" />
        <MoneyText value="-20.50" data-testid="neg" />
        <MoneyText value={null} data-testid="none" />
      </>,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("pos")).toHaveTextContent("R$ 1.500,00");
    expect(screen.getByTestId("pos")).toHaveAttribute("data-tone", "neutral");
    expect(screen.getByTestId("pos")).toHaveClass("et-num");
    expect(screen.getByTestId("neg")).toHaveAttribute("data-tone", "negative");
    expect(screen.getByTestId("none")).toHaveTextContent("—");
  });

  it("signed/positive/negative tones", () => {
    render(
      <>
        <MoneyText value="10.00" tone="signed" data-testid="a" />
        <MoneyText value="10.00" tone="negative" data-testid="b" />
        <MoneyText value="-10.00" tone="neutral" data-testid="c" />
      </>,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("a")).toHaveAttribute("data-tone", "positive");
    expect(screen.getByTestId("b")).toHaveAttribute("data-tone", "negative");
    expect(screen.getByTestId("c")).toHaveAttribute("data-tone", "neutral");
  });

  it("animate shows the final value at once under reduced motion", () => {
    render(<MoneyText value="280.00" animate data-testid="m" />, {
      wrapper: Wrapper,
    });
    expect(screen.getByTestId("m")).toHaveTextContent("R$ 280,00");
  });

  it("animate counts up and lands exactly on the formatted value", () => {
    const motion = allowMotion();
    render(<MoneyText value="280.00" animate data-testid="m" />, {
      wrapper: Wrapper,
    });
    expect(screen.getByTestId("m")).toHaveTextContent("R$ 0,00");
    motion.step(800);
    expect(screen.getByTestId("m")).toHaveTextContent("R$ 280,00");
  });
});

describe("StatCard", () => {
  it("renders label, value right after the label, icon and a bad (up) delta for spending", () => {
    render(
      <StatCard
        label="Total do mês"
        value="1500.00"
        valueTestId="v"
        icon={<span>i</span>}
        delta={{ pct: 12.5, label: "vs set/2026" }}
        hint="out/2026"
      />,
      { wrapper: Wrapper },
    );
    const section = screen.getByRole("region", { name: "Total do mês" });
    expect(section).toBeInTheDocument();
    expect(screen.getByTestId("v")).toHaveTextContent("R$ 1.500,00");
    expect(screen.getByText("Total do mês").nextSibling).toHaveTextContent(
      "R$ 1.500,00",
    );
    expect(screen.getByText("+12,5%").closest("[data-trend]")).toHaveAttribute(
      "data-trend",
      "bad",
    );
    expect(screen.getByText("vs set/2026")).toBeInTheDocument();
    expect(screen.getByText("out/2026")).toBeInTheDocument();
  });

  it("note variant prints the serial and the guilloché; good/flat/none deltas", () => {
    const { rerender } = render(
      <StatCard
        variant="note"
        label="Total"
        value="10.00"
        serial="OUT · 2026"
        delta={{ pct: -5, label: "vs set" }}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByRole("region", { name: "Total" })).toHaveAttribute(
      "data-variant",
      "note",
    );
    expect(screen.getByText("OUT · 2026")).toBeInTheDocument();
    expect(screen.getByText("−5%").closest("[data-trend]")).toHaveAttribute(
      "data-trend",
      "good",
    );
    expect(document.querySelector(".et-note__guilloche")).not.toBeNull();

    rerender(
      <StatCard
        label="Renda"
        value="1.00"
        delta={{ pct: 3, label: "x", goodWhen: "up" }}
      />,
    );
    expect(screen.getByText("+3%").closest("[data-trend]")).toHaveAttribute(
      "data-trend",
      "good",
    );
    rerender(
      <StatCard label="Renda" value="1.00" delta={{ pct: 0, label: "x" }} />,
    );
    expect(screen.getByText("estável").closest("[data-trend]")).toHaveAttribute(
      "data-trend",
      "flat",
    );
    rerender(
      <StatCard
        label="Renda"
        display={<b>custom</b>}
        delta={{ pct: null, label: "ontem" }}
      />,
    );
    expect(screen.getByText("custom")).toBeInTheDocument();
    expect(screen.getByText("sem comparação ontem")).toBeInTheDocument();
  });

  it("deltaText", () => {
    expect(deltaText(0)).toBe("estável");
    expect(deltaText(1.234)).toBe("+1,2%");
    expect(deltaText(-40)).toBe("−40%");
  });
});

describe("PageHeader / Panel / EmptyState", () => {
  it("PageHeader renders the page h2, eyebrow, subtitle, actions and filters", async () => {
    const onClick = vi.fn();
    render(
      <PageHeader
        title="Resumo"
        eyebrow="Visão geral"
        subtitle="Para onde foi o dinheiro."
        icon={<span>i</span>}
        actions={<button onClick={onClick}>Agir</button>}
      >
        <label>
          Filtro <input />
        </label>
      </PageHeader>,
      { wrapper: Wrapper },
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "Resumo" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Visão geral")).toBeInTheDocument();
    expect(screen.getByText("Para onde foi o dinheiro.")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtro")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Agir" }));
    expect(onClick).toHaveBeenCalled();
  });

  it("PageHeader without optional parts", () => {
    render(<PageHeader title="Só título" />, { wrapper: Wrapper });
    expect(
      screen.getByRole("heading", { name: "Só título" }),
    ).toBeInTheDocument();
  });

  it("Panel is a named region with an h3", () => {
    render(
      <Panel
        title="Gastos"
        description="do mês"
        icon={<span>i</span>}
        actions={<button>x</button>}
      >
        conteúdo
      </Panel>,
      { wrapper: Wrapper },
    );
    const region = screen.getByRole("region", { name: "Gastos" });
    expect(region).toHaveClass("et-lift");
    expect(
      screen.getByRole("heading", { level: 3, name: "Gastos" }),
    ).toBeInTheDocument();
    expect(screen.getByText("do mês")).toBeInTheDocument();
    expect(screen.getByText("conteúdo")).toBeInTheDocument();
  });

  it("Panel can opt out of the hover lift", () => {
    render(
      <Panel title="Tabela" interactive={false}>
        x
      </Panel>,
      { wrapper: Wrapper },
    );
    expect(screen.getByRole("region", { name: "Tabela" })).not.toHaveClass(
      "et-lift",
    );
  });

  it("EmptyState shows text (never only an image) and an action", () => {
    render(
      <EmptyState
        title="Nada por aqui ainda."
        description="Crie o primeiro."
        action={<button>Criar</button>}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByText("Nada por aqui ainda.")).toBeInTheDocument();
    expect(screen.getByText("Crie o primeiro.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar" })).toBeInTheDocument();
    // the illustration is decorative
    expect(document.querySelector(".et-empty__art")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("EmptyState compact", () => {
    render(<EmptyState compact title="Vazio" icon={<span>i</span>} />, {
      wrapper: Wrapper,
    });
    expect(screen.getByText("Vazio").closest(".et-empty")).toHaveAttribute(
      "data-compact",
      "true",
    );
  });
});

describe("StatusBadge", () => {
  it("maps tones, keeps the text and passes data attributes", () => {
    render(
      <>
        <StatusBadge tone="danger" strong data-band="red">
          faltando
        </StatusBadge>
        <StatusBadge dot={false}>neutro</StatusBadge>
      </>,
      { wrapper: Wrapper },
    );
    const strong = screen.getByText("faltando").closest("[data-tone]");
    expect(strong).toHaveAttribute("data-tone", "danger");
    expect(strong).toHaveAttribute("data-band", "red");
    expect(strong).toHaveAttribute("data-variant", "filled");
    expect(screen.getByText("neutro").closest("[data-tone]")).toHaveAttribute(
      "data-tone",
      "neutral",
    );
  });

  it("toneFromColor", () => {
    expect(toneFromColor("green")).toBe("success");
    expect(toneFromColor("orange")).toBe("warning");
    expect(toneFromColor("red")).toBe("danger");
    expect(toneFromColor("blue")).toBe("info");
    expect(toneFromColor("grape")).toBe("accent");
    expect(toneFromColor("nope")).toBe("neutral");
    expect(toneFromColor(undefined)).toBe("neutral");
  });
});

describe("charts", () => {
  it("ChartTooltip renders nothing when inactive or empty", () => {
    const { container, rerender } = render(<ChartTooltip active={false} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ChartTooltip active payload={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ChartTooltip active payload={[{ name: "x", value: 0 }]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("ChartTooltip lists each series with money", () => {
    render(
      <ChartTooltip
        active
        label="out/2026"
        payload={[
          { name: "Gasto", value: 12.5, color: "#B4233F", dataKey: "total" },
          { name: "Casa", value: "3.00", payload: { color: "#0E6B55" } },
        ]}
      />,
    );
    expect(screen.getByText("out/2026")).toBeInTheDocument();
    expect(screen.getByText("Gasto")).toBeInTheDocument();
    expect(screen.getByText("R$ 12,50")).toBeInTheDocument();
    expect(screen.getByText("R$ 3,00")).toBeInTheDocument();
  });

  it("useChartTheme follows the colour scheme and disables animation in tests", async () => {
    mockApi({});
    localStorage.setItem("expense-tracker-color-scheme", "dark");
    let theme: ReturnType<typeof useChartTheme> | null = null;
    function Probe() {
      theme = useChartTheme();
      return null;
    }
    renderPage(<Probe />);
    await waitFor(() => expect(theme?.series(0)).toBe(CHART_PALETTE.dark[0]));
    expect(theme!.series(11)).toBe(CHART_PALETTE.dark[1]);
    expect(theme!.animation.isAnimationActive).toBe(false);
    localStorage.clear();
  });

  it("ContentSkeleton is a busy status region", () => {
    render(<ContentSkeleton cards={2} rows={3} />, { wrapper: Wrapper });
    const status = screen.getByRole("status", { name: "Carregando" });
    expect(status).toHaveAttribute("aria-busy", "true");
  });
});

describe("Guilloche", () => {
  it("generates closed rosette and wave paths", () => {
    const d = rosettePath(150, 40, 70, 160, 160, 10);
    expect(d.startsWith("M")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    expect(wavePath(8, 10, 2, 4, 0)).toMatch(/^M0 10\.00L4 /);
  });

  it("renders decorative SVGs", () => {
    const { container } = render(
      <>
        <Guilloche className="g" />
        <BrandMark size={20} />
      </>,
    );
    const svgs = container.querySelectorAll("svg");
    expect(svgs).toHaveLength(2);
    svgs.forEach((s) => expect(s).toHaveAttribute("aria-hidden", "true"));
  });
});

function Wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider theme={theme}>{children}</MantineProvider>;
}

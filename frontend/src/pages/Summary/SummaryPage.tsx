/** Resumo (R1.6, R1.7, R1.9, R5.5, R11.4; docs/07 "Resumo"). */
import {
  Grid,
  Group,
  MultiSelect,
  Progress,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  UnstyledButton,
} from "@mantine/core";
import {
  IconCalendarStats,
  IconCards,
  IconChartBar,
  IconChartDonut3,
  IconChartHistogram,
  IconCreditCard,
  IconLayoutDashboard,
  IconPigMoney,
  IconReceipt2,
  IconScale,
  IconTable,
  IconTargetArrow,
  IconWallet,
} from "@tabler/icons-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
} from "recharts";
import { useGet, useList, useNames } from "../../api/hooks";
import type { MonthSeries, Projection, Summary } from "../../api/types";
import { QueryState } from "../../components/QueryState";
import {
  ContentSkeleton,
  EmptyState,
  MoneyText,
  PageHeader,
  StatCard,
  StatusBadge,
  type StatDelta,
} from "../../components/ui";

import { readDefaultPeople } from "../../hooks/defaultPeople";
import { formatMonth, useMonth } from "../../hooks/month";
import { formatMoney, METHOD_LABELS, sumMoney } from "../../lib/format";
import {
  BandBadge,
  buildQuery,
  chartAxes,
  chartTooltip,
  METHOD_FILTER_OPTIONS,
  Panel,
  PendingSwitch,
  PeopleSelect,
  plotValue,
  useCategoryInfo,
  useChartColors,
} from "./shared";

const CHART_HEIGHT = 260;
const COMPACT_CHART = 170; // R14.37: "Gasto x renda" and the category history are short

/** Union of the keys of ``pick(series)`` across all months, in first-seen order. */
function seriesKeys(
  series: MonthSeries[],
  pick: (s: MonthSeries) => Record<string, string> | undefined,
): string[] {
  const keys: string[] = [];
  for (const s of series)
    for (const k of Object.keys(pick(s) ?? {}))
      if (!keys.includes(k)) keys.push(k);
  return keys;
}

/** Percent change from ``previous`` to ``current``; null when there is nothing to compare with. */
export function percentChange(
  current: string | null | undefined,
  previous: string | null | undefined,
): number | null {
  const prev = plotValue(previous);
  if (previous === null || previous === undefined || prev === 0) return null;
  return ((plotValue(current) - prev) / Math.abs(prev)) * 100;
}

/** "out/2026" -> "OUT·2026", printed on the banknote like a serial. */
function serialOf(month: string): string {
  return formatMonth(month).toUpperCase().replace("/", " · ");
}

export function SummaryPage() {
  const { selected } = useMonth();
  // R14.25: starts with the default people of Configurações; several = their parts summed
  const [people, setPeople] = useState<string[]>(readDefaultPeople);
  const userId = people.length ? people.join(",") : null;
  const [method, setMethod] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const summaryPath = `/api/reports/summary${buildQuery({
    month: selected,
    user_id: userId,
    include_pending: pending,
    payment_method: method,
  })}`;
  const summary = useGet<Summary>(
    ["reports", "summary", summaryPath],
    summaryPath,
  );
  const projectionPath = `/api/reports/projection${buildQuery({
    user_id: userId,
    include_pending: pending,
  })}`;
  const projection = useGet<Projection>(
    ["reports", "projection", projectionPath],
    projectionPath,
  );

  return (
    <Stack gap="xl">
      <PageHeader
        title="Resumo"
        eyebrow="Visão geral"
        icon={<IconLayoutDashboard size={22} stroke={1.7} />}
        subtitle={`Para onde foi o dinheiro em ${formatMonth(selected)}.`}
      >
        <PeopleSelect value={people} onChange={setPeople} />
        <Select
          label="Meio de pagamento"
          placeholder="Todos"
          data={METHOD_FILTER_OPTIONS}
          value={method}
          onChange={setMethod}
          clearable
          w={220}
        />
        <PendingSwitch checked={pending} onChange={setPending} />
      </PageHeader>
      {summary.isLoading ? (
        <ContentSkeleton cards={3} rows={5} />
      ) : (
        <QueryState isLoading={false} error={summary.error}>
          {summary.data && (
            <SummaryPanels
              data={summary.data}
              projection={projection.data}
              month={selected}
            />
          )}
        </QueryState>
      )}
    </Stack>
  );
}

function SummaryPanels({
  data,
  projection,
  month,
}: {
  data: Summary;
  projection: Projection | undefined;
  month: string;
}) {
  // R14.37: categories shown in the history; none chosen = every category, stacked
  const [historyCats, setHistory] = useState<string[]>([]);
  const index = data.series.findIndex((s) => s.month === month);
  const current = index >= 0 ? data.series[index] : undefined;
  const previous = index > 0 ? data.series[index - 1] : undefined;
  const income = current?.income ?? committedIncome(projection, month);
  const delta: StatDelta = {
    pct: previous ? percentChange(data.total, previous.total) : null,
    label: previous
      ? `vs ${formatMonth(previous.month)}`
      : "com o mês anterior",
    goodWhen: "down",
  };
  const leftover = income ? sumMoney([income, negate(data.total)]) : null;
  return (
    <Stack gap="lg" className="et-stagger">
      <Grid gutter="lg" align="stretch">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <StatCard
            variant="note"
            label="Total do mês"
            value={data.total}
            valueTestId="month-total"
            icon={<IconReceipt2 size={22} stroke={1.6} />}
            serial={serialOf(month)}
            delta={delta}
            hint={formatMonth(month)}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack gap="lg" h="100%">
            <StatCard
              label="Renda do mês"
              value={income}
              tone="neutral"
              icon={<IconWallet size={20} stroke={1.7} />}
              hint={
                income
                  ? "salário e outras receitas cadastradas"
                  : "sem renda cadastrada"
              }
            />
            <StatCard
              label="Sobra do mês"
              value={leftover}
              tone="signed"
              icon={<IconPigMoney size={20} stroke={1.7} />}
              hint={
                leftover
                  ? "renda menos gastos do mês"
                  : "cadastre a renda para ver a sobra"
              }
            />
          </Stack>
        </Grid.Col>
      </Grid>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <CategoryPie data={data} onPick={(id) => setHistory([id])} />
        <Stack gap="lg">
          <SpendVsIncome series={data.series} />
          <CategoryHistory
            series={data.series}
            uncategorizedKey={data.uncategorized_key}
            selected={historyCats}
            onSelected={setHistory}
          />
        </Stack>
      </SimpleGrid>
      {/* R14.36: the per-person table needs the full width; the goals go below it */}
      <CommittedIncome projection={projection} month={month} />
      <Goals goals={data.goals} />
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <ByCard series={data.series} />
        <ByMethod series={data.series} />
      </SimpleGrid>
      <AnnualTables data={data} />
    </Stack>
  );
}

/** Sum of the incomes the projection reports for month (fallback when the series has none). */
export function committedIncome(
  projection: Projection | undefined,
  month: string,
): string | null {
  const values = (projection?.committed_income ?? [])
    .map((c) => c.months.find((m) => m.month === month)?.income)
    .filter((v): v is string => !!v);
  return values.length > 0 ? sumMoney(values) : null;
}

function negate(value: string): string {
  return value.startsWith("-") ? value.slice(1) : `-${value}`;
}

/**
 * R1.9 + R14.33 "Gasto por pessoa": everyone's part of the month; who has income also gets the
 * committed percentage, who has none says so.
 */
function CommittedIncome({
  projection,
  month,
}: {
  projection: Projection | undefined;
  month: string;
}) {
  const names = useNames();
  const rows = (projection?.people ?? projection?.committed_income ?? [])
    .map((c) => ({
      userId: c.user_id,
      row: c.months.find((m) => m.month === month),
    }))
    .filter((r) => r.row);
  return (
    <Panel
      title="Gasto por pessoa"
      icon={<IconScale size={18} stroke={1.7} />}
      description="A parte de cada um nos gastos do mês; com renda cadastrada, quanto dela ficou comprometido."
    >
      {rows.length === 0 ? (
        <EmptyState
          compact
          icon={<IconScale size={22} stroke={1.6} />}
          title={`Ninguém gastou em ${formatMonth(month)}.`}
        />
      ) : (
        <Table.ScrollContainer minWidth={420}>
          <Table aria-label="Gasto por pessoa no mês">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Pessoa</Table.Th>
                <Table.Th ta="right">Gasto</Table.Th>
                <Table.Th ta="right">Renda</Table.Th>
                <Table.Th>Comprometida</Table.Th>
                <Table.Th>Benefício</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map(({ userId, row }) =>
                row ? (
                  <Table.Tr key={userId}>
                    <Table.Td>{names.users[userId] ?? userId}</Table.Td>
                    <Table.Td ta="right">{formatMoney(row.spent)}</Table.Td>
                    <Table.Td ta="right">
                      {row.income ? formatMoney(row.income) : "—"}
                    </Table.Td>
                    <Table.Td>
                      {row.income ? (
                        <BandBadge ratio={row.ratio} band={row.band} />
                      ) : (
                        <Text size="sm" c="dimmed">
                          sem renda cadastrada
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <BandBadge ratio={row.benefit_ratio} band={null} />
                    </Table.Td>
                  </Table.Tr>
                ) : null,
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Panel>
  );
}

function CategoryPie({
  data,
  onPick,
}: {
  data: Summary;
  onPick: (id: string) => void;
}) {
  const info = useCategoryInfo();
  const colors = useChartColors();
  const slices = Object.entries(data.by_category).map(([id, value]) => ({
    id,
    value: plotValue(value),
    amount: value,
    ...info(id, data.uncategorized_key),
  }));
  const total = plotValue(data.total);
  return (
    <Panel
      title="Gastos por categoria"
      icon={<IconChartDonut3 size={18} stroke={1.7} />}
    >
      {slices.length === 0 ? (
        <EmptyState
          compact
          icon={<IconChartDonut3 size={22} stroke={1.6} />}
          title="Sem gastos neste mês."
        />
      ) : (
        <Stack gap="sm">
          <div className="et-donut">
            <ResponsiveContainer width="100%" height={CHART_HEIGHT - 40}>
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="62%"
                  outerRadius="92%"
                  paddingAngle={slices.length > 1 ? 2 : 0}
                  cornerRadius={4}
                  stroke="none"
                  {...colors.animation}
                >
                  {slices.map((s) => (
                    <Cell key={s.id} fill={s.color} />
                  ))}
                </Pie>
                {chartTooltip(colors, false)}
              </PieChart>
            </ResponsiveContainer>
            <div className="et-donut__center" aria-hidden="true">
              <span className="et-donut__caption">total</span>
              <MoneyText
                value={data.total}
                className="et-display et-donut__value"
              />
            </div>
          </div>
          <Table aria-label="Gastos por categoria">
            <Table.Tbody>
              {slices.map((s) => (
                <Table.Tr key={s.id}>
                  <Table.Td>
                    {/* R14.37: a click shows this category's months in the history */}
                    <UnstyledButton
                      onClick={() => onPick(s.id)}
                      aria-label={`Ver histórico de ${s.name}`}
                      className="et-link-button"
                    >
                      <span
                        className="et-swatch"
                        style={{ background: s.color }}
                        aria-hidden="true"
                      />
                      {s.name}
                    </UnstyledButton>
                  </Table.Td>
                  <Table.Td w="38%" visibleFrom="xs">
                    <Progress
                      value={
                        total > 0 ? Math.min(100, (s.value / total) * 100) : 0
                      }
                      color={s.color}
                      size="sm"
                      radius="xl"
                      aria-hidden="true"
                      className="et-bar"
                    />
                  </Table.Td>
                  <Table.Td ta="right">{formatMoney(s.amount)}</Table.Td>
                  {/* R14.37: the share of the month */}
                  <Table.Td ta="right" c="dimmed" w={56}>
                    {total > 0
                      ? `${((s.value / total) * 100).toFixed(0)}%`
                      : "—"}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Stack>
      )}
    </Panel>
  );
}

function SpendVsIncome({ series }: { series: MonthSeries[] }) {
  const colors = useChartColors();
  const rows = series.map((s) => ({
    label: formatMonth(s.month),
    total: plotValue(s.total),
    income: s.income ? plotValue(s.income) : 0,
  }));
  return (
    <Panel
      title="Gasto x renda (12 meses)"
      icon={<IconChartBar size={18} stroke={1.7} />}
    >
      <ResponsiveContainer width="100%" height={COMPACT_CHART}>
        <BarChart data={rows} barGap={3}>
          {chartAxes(colors)}
          {chartTooltip(colors)}
          <Legend
            wrapperStyle={{ color: colors.text, fontSize: 12 }}
            iconType="circle"
            iconSize={8}
          />
          <Bar
            dataKey="total"
            name="Gasto"
            fill={colors.spend}
            radius={[6, 6, 0, 0]}
            maxBarSize={22}
            {...colors.animation}
          />
          <Bar
            dataKey="income"
            name="Renda"
            fill={colors.income}
            radius={[6, 6, 0, 0]}
            maxBarSize={22}
            {...colors.animation}
          />
        </BarChart>
      </ResponsiveContainer>
    </Panel>
  );
}

/**
 * R14.37 "Histórico por categoria": the last 12 months of one category or a group of them,
 * with each month's share of the total on top of the bar and the average, to see what started
 * to cost more. Picked in the selector or by clicking a category in "Gastos por categoria".
 */
export function CategoryHistory({
  series,
  uncategorizedKey,
  selected,
  onSelected,
}: {
  series: MonthSeries[];
  uncategorizedKey: string;
  selected: string[];
  onSelected: (ids: string[]) => void;
}) {
  const info = useCategoryInfo();
  const colors = useChartColors();
  const keys: string[] = [];
  for (const s of series)
    for (const k of Object.keys(s.by_category ?? {}))
      if (!keys.includes(k)) keys.push(k);
  // nothing chosen = every category, stacked, one colour each
  const all = selected.length === 0;
  const shown = all ? keys : selected;
  const rows = series.map((s) => {
    const value = sumMoney(shown.map((k) => s.by_category?.[k]));
    const total = Number(s.total);
    const pct = total > 0 ? (Number(value) / total) * 100 : 0;
    const row: Record<string, string | number> = {
      label: formatMonth(s.month),
      value: plotValue(value),
      pct: !all && Number(value) > 0 ? `${pct.toFixed(0)}%` : "",
      amount: value,
    };
    if (all) for (const k of keys) row[k] = plotValue(s.by_category?.[k]);
    return row;
  });
  const sum = sumMoney(rows.map((r) => String(r.amount)));
  const everything = sumMoney(series.map((s) => s.total));
  const average = rows.length ? Number(sum) / rows.length : 0;
  const share =
    Number(everything) > 0 ? (Number(sum) / Number(everything)) * 100 : 0;
  return (
    <Panel
      title="Histórico por categoria"
      icon={<IconChartHistogram size={18} stroke={1.7} />}
      description="Sem escolha, todas as categorias empilhadas. Escolha uma ou mais (ou clique numa em Gastos por categoria) para ver só elas, com a % do gasto do mês em cima da barra."
    >
      <Stack gap="sm">
        <MultiSelect
          aria-label="Categorias do histórico"
          placeholder="Todas as categorias"
          data={keys.map((k) => ({
            value: k,
            label: info(k, uncategorizedKey).name,
          }))}
          value={selected}
          onChange={onSelected}
          searchable
          clearable
        />
        {keys.length === 0 ? (
          <EmptyState compact title="Sem gastos no período." />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={COMPACT_CHART}>
              <BarChart data={rows} margin={{ top: 18 }}>
                {chartAxes(colors)}
                {chartTooltip(colors)}
                {all ? (
                  keys.map((k, i) => (
                    <Bar
                      key={k}
                      dataKey={k}
                      name={info(k, uncategorizedKey).name}
                      stackId="cats"
                      fill={info(k, uncategorizedKey).color}
                      maxBarSize={22}
                      radius={i === keys.length - 1 ? [6, 6, 0, 0] : undefined}
                      {...colors.animation}
                    />
                  ))
                ) : (
                  <Bar
                    dataKey="value"
                    name="Gasto"
                    fill={
                      selected.length === 1
                        ? info(selected[0] ?? "", uncategorizedKey).color
                        : colors.spend
                    }
                    radius={[6, 6, 0, 0]}
                    maxBarSize={22}
                    {...colors.animation}
                  >
                    <LabelList
                      dataKey="pct"
                      position="top"
                      style={{ fill: colors.text, fontSize: 11 }}
                    />
                  </Bar>
                )}
              </BarChart>
            </ResponsiveContainer>
            <Group gap="xl" aria-label="Resumo do histórico">
              <div>
                <Text size="xs" c="dimmed">
                  Média por mês
                </Text>
                <MoneyText value={average.toFixed(2)} fw={700} />
              </div>
              <div>
                <Text size="xs" c="dimmed">
                  {all ? "Categorias" : "Do total dos 12 meses"}
                </Text>
                <Text fw={700}>
                  {all
                    ? `todas (${keys.length})`
                    : `${share.toFixed(1).replace(".", ",")}%`}
                </Text>
              </div>
            </Group>
          </>
        )}
      </Stack>
    </Panel>
  );
}

function StackedSeries({
  title,
  icon,
  series,
  pick,
  label,
}: {
  title: string;
  icon: ReactNode;
  series: MonthSeries[];
  pick: (s: MonthSeries) => Record<string, string>;
  label: (key: string) => string;
}) {
  const colors = useChartColors();
  const keys = seriesKeys(series, pick);
  const rows = series.map((s) => {
    const row: Record<string, string | number> = {
      label: formatMonth(s.month),
    };
    for (const k of keys) row[k] = plotValue(pick(s)[k]);
    return row;
  });
  return (
    <Panel title={title} icon={icon}>
      {keys.length === 0 ? (
        <EmptyState compact icon={icon} title="Sem gastos no período." />
      ) : (
        <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
          <BarChart data={rows}>
            {chartAxes(colors)}
            {chartTooltip(colors)}
            <Legend
              wrapperStyle={{ color: colors.text, fontSize: 12 }}
              iconType="circle"
              iconSize={8}
            />
            {keys.map((k, i) => (
              <Bar
                key={k}
                dataKey={k}
                name={label(k)}
                stackId="a"
                fill={colors.series(i)}
                maxBarSize={28}
                radius={i === keys.length - 1 ? [6, 6, 0, 0] : undefined}
                {...colors.animation}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

function ByCard({ series }: { series: MonthSeries[] }) {
  const names = useNames();
  return (
    <StackedSeries
      title="Por cartão/conta"
      icon={<IconCards size={18} stroke={1.7} />}
      series={series}
      pick={(s) => s.by_card}
      label={(k) => names.owner(k) || "Sem cartão/conta"}
    />
  );
}

function ByMethod({ series }: { series: MonthSeries[] }) {
  return (
    <StackedSeries
      title="Por meio de pagamento"
      icon={<IconCreditCard size={18} stroke={1.7} />}
      series={series}
      pick={(s) => s.by_method}
      label={(k) => METHOD_LABELS[k] ?? k}
    />
  );
}

function Goals({ goals }: { goals: Summary["goals"] }) {
  const list = useList("savings-goals");
  const names = Object.fromEntries(
    (list.data ?? []).map((g) => [g.id, g.name]),
  );
  const entries = Object.entries(goals);
  if (entries.length === 0) return null;
  return (
    <Panel
      title="Metas de poupança"
      icon={<IconTargetArrow size={18} stroke={1.7} />}
    >
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
        {entries.map(([id, g]) => {
          const target = plotValue(g.target);
          const pct =
            target > 0
              ? Math.min(100, (plotValue(g.achieved) / target) * 100)
              : 0;
          const name = names[id] ?? id;
          return (
            <div key={id} className="et-goal">
              <Group justify="space-between" mb={6} wrap="nowrap">
                <Text fw={600}>{name}</Text>
                <Text size="sm" className="et-num" c="dimmed">
                  {formatMoney(g.achieved)} de {formatMoney(g.target)}
                </Text>
              </Group>
              <Progress
                value={pct}
                size="md"
                radius="xl"
                aria-label={`Meta ${name}`}
              />
            </div>
          );
        })}
      </SimpleGrid>
    </Panel>
  );
}

/**
 * R14.36: one annual table (rows = categories or cards/accounts, columns = months). The footer
 * has the total **without** benefit (the main one) and the total with benefit.
 */
function AnnualTable({
  title,
  label,
  firstHeader,
  annual,
  benefit,
  row,
}: {
  title: string;
  label: string;
  firstHeader: string;
  annual: Record<string, Record<string, string>>;
  benefit: Record<string, string>;
  row: (key: string) => ReactNode;
}) {
  const { current } = useMonth();
  // R14.33: a light tint on the current month column, so it is clear where to look
  const now = (m: string) =>
    m === current ? { className: "et-current-month" } : {};
  const months = Object.keys(annual).sort();
  const keys: string[] = [];
  for (const m of months)
    for (const k of Object.keys(annual[m] ?? {}))
      if (!keys.includes(k)) keys.push(k);
  const withBenefit = (m: string) => sumMoney(Object.values(annual[m] ?? {}));
  const withoutBenefit = (m: string) =>
    sumMoney([withBenefit(m), negate(benefit[m] ?? "0.00")]);
  const year = months[0]?.slice(0, 4) ?? "";
  // narrow screens: open the table scrolled so the current month is in view (no page scroll)
  const tableRef = useRef<HTMLTableElement>(null);
  useEffect(() => {
    const th = tableRef.current?.querySelector<HTMLElement>(
      'th[aria-current="date"]',
    );
    // the first ancestor that really scrolls sideways (whatever Mantine renders around the table)
    let box: HTMLElement | null = tableRef.current?.parentElement ?? null;
    while (box && box !== document.body) {
      const overflow = getComputedStyle(box).overflowX;
      if (
        (overflow === "auto" || overflow === "scroll") &&
        box.scrollWidth > box.clientWidth
      )
        break;
      box = box.parentElement;
    }
    if (box === document.body) box = null;
    if (!th || !box || box.scrollWidth <= box.clientWidth) return;
    box.scrollLeft = Math.max(
      0,
      th.offsetLeft + th.offsetWidth - box.clientWidth + 24,
    );
  }, [current, months.length]);
  const anyBenefit = months.some((m) => Number(benefit[m] ?? 0) !== 0);
  return (
    <Panel
      title={`${title} ${year}`}
      icon={<IconCalendarStats size={18} stroke={1.7} />}
      interactive={false}
    >
      {keys.length === 0 ? (
        <EmptyState
          compact
          icon={<IconTable size={22} stroke={1.6} />}
          title="Sem gastos no ano."
        />
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table
            striped
            aria-label={label}
            ref={tableRef}
            className="et-annual"
          >
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{firstHeader}</Table.Th>
                {months.map((m) => (
                  <Table.Th
                    key={m}
                    ta="right"
                    {...now(m)}
                    aria-current={m === current ? "date" : undefined}
                  >
                    {formatMonth(m)}
                  </Table.Th>
                ))}
                <Table.Th ta="right">Total</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {keys.map((k) => {
                const values = months.map((m) => annual[m]?.[k]);
                return (
                  <Table.Tr key={k}>
                    <Table.Td>{row(k)}</Table.Td>
                    {values.map((v, i) => (
                      <Table.Td
                        key={months[i]}
                        ta="right"
                        {...now(months[i] ?? "")}
                      >
                        {v ? formatMoney(v) : "—"}
                      </Table.Td>
                    ))}
                    <Table.Td ta="right" fw={700}>
                      {formatMoney(sumMoney(values))}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
            <Table.Tfoot>
              <Table.Tr>
                <Table.Th>
                  {anyBenefit ? "Total sem benefício" : "Total"}
                </Table.Th>
                {months.map((m) => (
                  <Table.Th key={m} ta="right" {...now(m)}>
                    {formatMoney(withoutBenefit(m))}
                  </Table.Th>
                ))}
                <Table.Th ta="right">
                  {formatMoney(sumMoney(months.map(withoutBenefit)))}
                </Table.Th>
              </Table.Tr>
              {anyBenefit && (
                <Table.Tr>
                  <Table.Td c="dimmed">Total com benefício</Table.Td>
                  {months.map((m) => (
                    <Table.Td key={m} ta="right" c="dimmed" {...now(m)}>
                      {formatMoney(withBenefit(m))}
                    </Table.Td>
                  ))}
                  <Table.Td ta="right" c="dimmed">
                    {formatMoney(sumMoney(months.map(withBenefit)))}
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tfoot>
          </Table>
        </Table.ScrollContainer>
      )}
    </Panel>
  );
}

/** R14.36: the year by category and by card/account (benefit cards marked). */
function AnnualTables({ data }: { data: Summary }) {
  const info = useCategoryInfo();
  const names = useNames();
  const benefitAccounts = new Set(
    (useList("accounts").data ?? [])
      .filter((a) => a.type === "benefit")
      .map((a) => a.id),
  );
  const benefit = data.annual_benefit ?? {};
  return (
    <>
      <AnnualTable
        title="Resumo anual por categoria"
        label="Resumo anual por categoria"
        firstHeader="Categoria"
        annual={data.annual}
        benefit={benefit}
        row={(c) => {
          const cat = info(c, data.uncategorized_key);
          return (
            <>
              <span
                className="et-swatch"
                style={{ background: cat.color }}
                aria-hidden="true"
              />
              {cat.name}
            </>
          );
        }}
      />
      {data.annual_by_card && (
        <AnnualTable
          title="Resumo anual por cartão/conta"
          label="Resumo anual por cartão/conta"
          firstHeader="Cartão / conta"
          annual={data.annual_by_card}
          benefit={benefit}
          row={(id) => (
            <>
              {names.owner(id)}{" "}
              {benefitAccounts.has(id) && (
                <StatusBadge tone="accent" size="xs">
                  benefício
                </StatusBadge>
              )}
            </>
          )}
        />
      )}
    </>
  );
}

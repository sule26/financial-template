/** Resumo (R1.6, R1.7, R1.9, R5.5, R11.4; docs/07 "Resumo"). */
import {
  Alert,
  Grid,
  Group,
  Progress,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import {
  IconCalendarStats,
  IconCards,
  IconChartBar,
  IconChartDonut3,
  IconCreditCard,
  IconLayoutDashboard,
  IconPigMoney,
  IconReceipt2,
  IconScale,
  IconTable,
  IconTargetArrow,
  IconWallet,
} from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  Cell,
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
  peopleName,
  plotValue,
  StateBadge,
  useCategoryInfo,
  useChartColors,
} from "./shared";

const CHART_HEIGHT = 260;

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
  const names = useNames();
  const personName = peopleName(people, names.users);
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
              personName={personName}
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
  personName,
}: {
  data: Summary;
  projection: Projection | undefined;
  month: string;
  personName: string | null;
}) {
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
        <CategoryPie data={data} />
        <SpendVsIncome series={data.series} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <CommittedIncome projection={projection} month={month} />
        <Panel
          title="Cartões e contas"
          icon={<IconCreditCard size={18} stroke={1.7} />}
          description={
            personName
              ? `Parte de ${personName} nos cartões e contas dele(a).`
              : undefined
          }
        >
          {/* Only what the API returns: with a person, it already keeps their cards/accounts. */}
          <StatesList states={data.states} />
        </Panel>
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <ByCard series={data.series} />
        <ByMethod series={data.series} />
      </SimpleGrid>
      <Goals goals={data.goals} />
      <AnnualTable
        annual={data.annual}
        uncategorizedKey={data.uncategorized_key}
      />
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

function StatesList({ states }: { states: Record<string, string> }) {
  const names = useNames();
  const entries = Object.entries(states);
  if (entries.length === 0)
    return (
      <EmptyState
        compact
        title="Nenhum cartão ou conta com movimento no mês."
      />
    );
  const missing = entries.filter(([, s]) => s === "missing");
  return (
    <Stack gap="sm">
      {missing.length > 0 && (
        <Alert
          color="red"
          variant="light"
          radius="md"
          title="Fatura/extrato faltando"
        >
          {missing.map(([id]) => names.owner(id)).join(", ")}: o mês usa a
          projeção e os saldos ficam incompletos.
        </Alert>
      )}
      <Table aria-label="Estado por cartão/conta">
        <Table.Tbody>
          {entries.map(([id, state]) => (
            <Table.Tr key={id}>
              <Table.Td>{names.owner(id)}</Table.Td>
              <Table.Td ta="right">
                <StateBadge state={state} />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

/** R1.9: one line per user with income in the selected month. */
function CommittedIncome({
  projection,
  month,
}: {
  projection: Projection | undefined;
  month: string;
}) {
  const names = useNames();
  const rows = (projection?.committed_income ?? [])
    .map((c) => ({
      userId: c.user_id,
      row: c.months.find((m) => m.month === month),
    }))
    .filter(
      (r) => r.row && (r.row.ratio !== null || r.row.benefit_ratio !== null),
    );
  return (
    <Panel
      title="Renda comprometida"
      icon={<IconScale size={18} stroke={1.7} />}
    >
      {rows.length === 0 ? (
        <EmptyState
          compact
          icon={<IconScale size={22} stroke={1.6} />}
          title={`Sem renda cadastrada para ${formatMonth(month)}.`}
        />
      ) : (
        <Table.ScrollContainer minWidth={420}>
          <Table aria-label="Renda comprometida no mês">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Pessoa</Table.Th>
                <Table.Th>Gasto / renda</Table.Th>
                <Table.Th>Comprometida</Table.Th>
                <Table.Th>Benefício</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map(({ userId, row }) =>
                row ? (
                  <Table.Tr key={userId}>
                    <Table.Td>{names.users[userId] ?? userId}</Table.Td>
                    <Table.Td>
                      {formatMoney(row.spent)} / {formatMoney(row.income)}
                    </Table.Td>
                    <Table.Td>
                      <BandBadge ratio={row.ratio} band={row.band} />
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

function CategoryPie({ data }: { data: Summary }) {
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
                    <span
                      className="et-swatch"
                      style={{ background: s.color }}
                      aria-hidden="true"
                    />
                    {s.name}
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
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
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

function AnnualTable({
  annual,
  uncategorizedKey,
}: {
  annual: Summary["annual"];
  uncategorizedKey: string;
}) {
  const info = useCategoryInfo();
  const months = Object.keys(annual).sort();
  const categories: string[] = [];
  for (const m of months)
    for (const c of Object.keys(annual[m] ?? {}))
      if (!categories.includes(c)) categories.push(c);
  const year = months[0]?.slice(0, 4) ?? "";
  return (
    <Panel
      title={`Resumo anual ${year}`}
      icon={<IconCalendarStats size={18} stroke={1.7} />}
      interactive={false}
    >
      {categories.length === 0 ? (
        <EmptyState
          compact
          icon={<IconTable size={22} stroke={1.6} />}
          title="Sem gastos no ano."
        />
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped aria-label="Resumo anual por categoria">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Categoria</Table.Th>
                {months.map((m) => (
                  <Table.Th key={m} ta="right">
                    {formatMonth(m)}
                  </Table.Th>
                ))}
                <Table.Th ta="right">Total</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {categories.map((c) => {
                const values = months.map((m) => annual[m]?.[c]);
                const cat = info(c, uncategorizedKey);
                return (
                  <Table.Tr key={c}>
                    <Table.Td>
                      <span
                        className="et-swatch"
                        style={{ background: cat.color }}
                        aria-hidden="true"
                      />
                      {cat.name}
                    </Table.Td>
                    {values.map((v, i) => (
                      <Table.Td key={months[i]} ta="right">
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
                <Table.Th>Total</Table.Th>
                {months.map((m) => (
                  <Table.Th key={m} ta="right">
                    {formatMoney(sumMoney(Object.values(annual[m] ?? {})))}
                  </Table.Th>
                ))}
                <Table.Th ta="right">
                  {formatMoney(
                    sumMoney(
                      months.flatMap((m) => Object.values(annual[m] ?? {})),
                    ),
                  )}
                </Table.Th>
              </Table.Tr>
            </Table.Tfoot>
          </Table>
        </Table.ScrollContainer>
      )}
    </Panel>
  );
}

/** Investimentos (R9, docs/15): totals, evolution, distribution and per-investment positions. */
import { Button, Group, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import {
  IconChartDonut3,
  IconChartLine,
  IconCoins,
  IconPigMoney,
  IconPlus,
  IconTrendingUp,
  IconUsers,
} from "@tabler/icons-react";
import { useState } from "react";
import {
  Area,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "../../components/ui/ChartTooltip";
import { useGet, useList, useNames } from "../../api/hooks";
import type { Investment, InvestmentsReport } from "../../api/types";
import { QueryState } from "../../components/QueryState";
import { formatMonth } from "../../hooks/month";
import { formatDate, formatMoney } from "../../lib/format";
import {
  InvestmentActionModal,
  NewInvestmentModal,
  TYPE_LABELS,
  type InvestmentAction,
} from "./InvestmentForms";
import {
  EmptyState,
  MoneyText,
  PageHeader,
  Panel,
  StatCard,
  StatusBadge,
  useChartTheme,
} from "../../components/ui";
import { compactMoney } from "../Summary/shared";

type Position = InvestmentsReport["positions"][number];

/** Chart data: decimal strings converted to numbers only for plotting (display, not math). */
export function chartData(report: InvestmentsReport) {
  return {
    evolution: report.evolution.map((e) => ({
      month: formatMonth(e.month),
      balance: Number(e.balance),
      contributions: Number(e.contributions),
    })),
    byType: Object.entries(report.by_type)
      .filter(([, v]) => Number(v) > 0)
      .map(([type, v]) => ({
        name: TYPE_LABELS[type as Investment["type"]] ?? type,
        value: Number(v),
      })),
  };
}

export function InvestmentsPage() {
  const report = useGet<InvestmentsReport>(
    ["reports", "investments"],
    "/api/reports/investments",
  );
  const investments = useList("investments");
  const names = useNames();
  const institutions = useList("institutions").data ?? [];
  const institutionName = (inv: Investment): string | null => {
    const id = inv.institution_id;
    if (id)
      return (
        names.accounts[id] ??
        institutions.find((i) => i.id === id)?.name ??
        inv.institution ??
        null
      );
    return inv.institution;
  };
  const [creating, setCreating] = useState(false);
  const [target, setTarget] = useState<{
    inv: Investment;
    action: InvestmentAction;
  } | null>(null);

  const rows = investments.data ?? [];
  const positions = new Map<string, Position>(
    (report.data?.positions ?? []).map((p) => [p.investment_id, p]),
  );
  const data = report.data ? chartData(report.data) : null;
  const chart = useChartTheme();

  return (
    <Stack gap="xl">
      <PageHeader
        title="Investimentos"
        eyebrow="Movimento"
        icon={<IconCoins size={22} stroke={1.7} />}
        subtitle="Saldo, aportes e rendimento de cada aplicação."
        actions={
          <Button
            onClick={() => setCreating(true)}
            leftSection={<IconPlus size={16} stroke={2.2} aria-hidden="true" />}
          >
            Novo investimento
          </Button>
        }
      />

      <QueryState isLoading={report.isLoading} error={report.error}>
        {report.data && data && (
          <Stack gap="lg" className="et-stagger">
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
              <StatCard
                label="Total investido"
                value={report.data.total}
                icon={<IconPigMoney size={20} stroke={1.7} />}
              />
              <StatCard
                label="Rendimento acumulado"
                value={report.data.yield_total}
                tone="signed"
                icon={<IconTrendingUp size={20} stroke={1.7} />}
              />
              <StatCard
                label="Por usuário"
                icon={<IconUsers size={20} stroke={1.7} />}
                display={
                  <Stack gap={4} aria-label="Total por usuário" mt={4}>
                    {Object.entries(report.data.by_user).map(([uid, v]) => (
                      <Group key={uid} justify="space-between">
                        <Text size="sm">{names.users[uid] ?? uid}</Text>
                        <MoneyText value={v} size="sm" fw={700} />
                      </Group>
                    ))}
                    {Object.keys(report.data.by_user).length === 0 && (
                      <Text size="sm" c="dimmed">
                        —
                      </Text>
                    )}
                  </Stack>
                }
              />
            </SimpleGrid>

            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
              <Panel
                title="Evolução do saldo"
                icon={<IconChartLine size={18} stroke={1.7} />}
              >
                <div
                  role="img"
                  aria-label="Gráfico de evolução do saldo total e aportes acumulados"
                >
                  <ResponsiveContainer width="100%" height={260}>
                    <ComposedChart data={data.evolution}>
                      <defs>
                        <linearGradient
                          id="et-inv-area"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor={chart.series(1)}
                            stopOpacity={0.35}
                          />
                          <stop
                            offset="100%"
                            stopColor={chart.series(1)}
                            stopOpacity={0.02}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        stroke={chart.grid}
                        strokeDasharray="2 6"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="month"
                        tick={{ fill: chart.text, fontSize: 12 }}
                        tickLine={false}
                        axisLine={{ stroke: chart.grid }}
                      />
                      <YAxis
                        tick={{ fill: chart.text, fontSize: 12 }}
                        tickLine={false}
                        axisLine={false}
                        width={72}
                        tickFormatter={compactMoney}
                      />
                      <Tooltip
                        content={<ChartTooltip />}
                        cursor={{ stroke: chart.grid }}
                      />
                      <Legend
                        wrapperStyle={{ color: chart.text, fontSize: 12 }}
                        iconType="circle"
                        iconSize={8}
                      />
                      <Area
                        type="monotone"
                        dataKey="contributions"
                        name="Aportes acumulados"
                        fill="url(#et-inv-area)"
                        stroke={chart.series(1)}
                        strokeWidth={2}
                        {...chart.animation}
                      />
                      <Line
                        type="monotone"
                        dataKey="balance"
                        name="Saldo"
                        stroke={chart.series(0)}
                        strokeWidth={2.5}
                        dot={false}
                        activeDot={{ r: 5 }}
                        {...chart.animation}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </Panel>
              <Panel
                title="Distribuição por tipo"
                icon={<IconChartDonut3 size={18} stroke={1.7} />}
              >
                {data.byType.length === 0 ? (
                  <EmptyState
                    compact
                    icon={<IconChartDonut3 size={22} stroke={1.6} />}
                    title="Sem saldo para distribuir ainda."
                  />
                ) : (
                  <div role="img" aria-label="Gráfico de distribuição por tipo">
                    <ResponsiveContainer width="100%" height={260}>
                      <PieChart>
                        <Pie
                          data={data.byType}
                          dataKey="value"
                          nameKey="name"
                          innerRadius="58%"
                          outerRadius="88%"
                          paddingAngle={data.byType.length > 1 ? 2 : 0}
                          cornerRadius={4}
                          stroke="none"
                          {...chart.animation}
                        >
                          {data.byType.map((entry, i) => (
                            <Cell key={entry.name} fill={chart.series(i)} />
                          ))}
                        </Pie>
                        <Tooltip content={<ChartTooltip />} />
                        <Legend
                          wrapperStyle={{ color: chart.text, fontSize: 12 }}
                          iconType="circle"
                          iconSize={8}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <Stack gap={2} mt="xs">
                  {Object.entries(report.data.by_type).map(([type, v]) => (
                    <Group key={type} justify="space-between">
                      <Text size="sm">
                        {TYPE_LABELS[type as Investment["type"]] ?? type}
                      </Text>
                      <MoneyText value={v} size="sm" fw={600} />
                    </Group>
                  ))}
                </Stack>
              </Panel>
            </SimpleGrid>
          </Stack>
        )}
      </QueryState>

      <QueryState
        isLoading={investments.isLoading}
        error={investments.error}
        empty={rows.length === 0}
        emptyText="Nenhum investimento cadastrado. Use “Novo investimento” para começar."
        emptyIcon={<IconCoins size={26} stroke={1.6} />}
      >
        <Table.ScrollContainer minWidth={800} className="et-table-card">
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Investimento</Table.Th>
                <Table.Th>Tipo</Table.Th>
                <Table.Th>Saldo</Table.Th>
                <Table.Th>Último saldo em</Table.Th>
                <Table.Th>Aporte líquido</Table.Th>
                <Table.Th>Rendimento</Table.Th>
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((inv) => {
                const p = positions.get(inv.id);
                return (
                  <Table.Tr key={inv.id}>
                    <Table.Td>
                      {inv.name}
                      {institutionName(inv) && (
                        <Text size="xs" c="dimmed">
                          {institutionName(inv)}
                        </Text>
                      )}
                      {inv.closed_at && (
                        <StatusBadge size="xs" tone="neutral">
                          encerrado em {formatDate(inv.closed_at)}
                        </StatusBadge>
                      )}
                    </Table.Td>
                    <Table.Td>{TYPE_LABELS[inv.type]}</Table.Td>
                    <Table.Td>
                      {formatMoney(p?.balance)}{" "}
                      {p?.estimated && (
                        <StatusBadge
                          size="xs"
                          tone="warning"
                          title="Saldo não informado: usando o aporte líquido"
                        >
                          estimado
                        </StatusBadge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {formatDate(p?.balance_date)}{" "}
                      {p?.stale && (
                        <StatusBadge
                          size="xs"
                          tone="warning"
                          title="Último saldo há mais de 45 dias"
                        >
                          desatualizado
                        </StatusBadge>
                      )}
                    </Table.Td>
                    <Table.Td>{formatMoney(p?.net_contributions)}</Table.Td>
                    <Table.Td>
                      <MoneyText value={p?.yield} tone="signed" fw={600} />
                    </Table.Td>
                    <Table.Td className="et-sticky-end">
                      <Group gap={4} wrap="nowrap">
                        <Button
                          size="xs"
                          variant="light"
                          aria-label={`Registrar saldo de ${inv.name}`}
                          onClick={() => setTarget({ inv, action: "snapshot" })}
                        >
                          Registrar saldo
                        </Button>
                        <Button
                          size="xs"
                          variant="light"
                          aria-label={`Registrar aporte ou resgate de ${inv.name}`}
                          onClick={() => setTarget({ inv, action: "movement" })}
                        >
                          Aporte/resgate
                        </Button>
                        {!inv.closed_at && (
                          <Button
                            size="xs"
                            variant="subtle"
                            color="red"
                            aria-label={`Encerrar ${inv.name}`}
                            onClick={() => setTarget({ inv, action: "close" })}
                          >
                            Encerrar
                          </Button>
                        )}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </QueryState>

      <NewInvestmentModal
        opened={creating}
        onClose={() => setCreating(false)}
      />
      <InvestmentActionModal
        investment={target?.inv ?? null}
        action={target?.action ?? null}
        onClose={() => setTarget(null)}
      />
    </Stack>
  );
}

/** Projeção de 12 meses (R1.9, R1.13, R8.5, R8.9; docs/07 "Projeção de 12 meses"). */
import { Button, CloseButton, Group, Stack, Table, Text } from "@mantine/core";
import {
  IconCalendarEvent,
  IconChartAreaLine,
  IconChartBar,
  IconListDetails,
  IconScale,
  IconTable,
} from "@tabler/icons-react";
import { useState } from "react";
import { Bar, BarChart, Legend, ResponsiveContainer } from "recharts";
import { useGet, useNames } from "../../api/hooks";
import type { MonthStr, Projection } from "../../api/types";
import { QueryState } from "../../components/QueryState";
import {
  EmptyState,
  MoneyText,
  PageHeader,
  StatusBadge,
} from "../../components/ui";
import { formatMonth } from "../../hooks/month";
import { formatDate, formatMoney, sumMoney } from "../../lib/format";
import {
  BandBadge,
  buildQuery,
  chartAxes,
  chartTooltip,
  Panel,
  PendingSwitch,
  PersonSelect,
  plotValue,
  StateBadge,
  useCategoryInfo,
  useChartColors,
} from "../Summary/shared";

/** Shape of GET /api/reports/month-items (services/reports.py item_json). */
export interface MonthItem {
  month: MonthStr;
  description: string;
  amount: string;
  /** Whole amount of the item; differs from `amount` when a person is selected (their part). */
  total_amount?: string;
  kind: string;
  payment_method: string;
  origin: string;
  card_id: string | null;
  account_id: string | null;
  category_id: string | null;
  ref_id: string | null;
  purchase_date: string | null;
  provisional: boolean;
  forecast: boolean;
}

export const ORIGIN_LABELS: Record<string, string> = {
  transaction: "transação",
  staging: "não confirmado",
  plan: "parcela",
  anticipation: "antecipação",
  subscription: "assinatura",
  recurring: "recorrente",
};

/** Keys in first-seen order. Columns come only from the API rows (already filtered by person). */
function unionKeys(rows: Record<string, unknown>[]): string[] {
  const keys: string[] = [];
  for (const r of rows)
    for (const k of Object.keys(r)) if (!keys.includes(k)) keys.push(k);
  return keys;
}

export function ProjectionPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [openMonth, setOpenMonth] = useState<MonthStr | null>(null);
  const path = `/api/reports/projection${buildQuery({
    user_id: userId,
    include_pending: pending,
  })}`;
  const projection = useGet<Projection>(["reports", "projection", path], path);
  const names = useNames();
  const personName = userId ? (names.users[userId] ?? userId) : null;

  return (
    <Stack gap="xl">
      <PageHeader
        title="Projeção"
        eyebrow="Visão geral"
        icon={<IconChartAreaLine size={22} stroke={1.7} />}
        subtitle="Seus cartões nos próximos 12 meses. Cada cartão usa a fatura real quando existe; senão, a projeção (parcelas, assinaturas, recorrentes e lançamentos previstos). Débito, PIX e dinheiro ficam no Resumo."
      >
        <PersonSelect value={userId} onChange={setUserId} />
        <PendingSwitch checked={pending} onChange={setPending} />
      </PageHeader>
      <QueryState
        isLoading={projection.isLoading}
        error={projection.error}
        empty={(projection.data?.months.length ?? 0) === 0}
        emptyText="Sem dados de projeção."
        emptyIcon={<IconChartAreaLine size={26} stroke={1.6} />}
      >
        {projection.data && (
          <Stack gap="lg" className="et-stagger">
            <MonthCardTable
              data={projection.data}
              onOpen={setOpenMonth}
              personName={personName}
            />
            {openMonth && (
              <MonthItems
                month={openMonth}
                pending={pending}
                userId={userId}
                personName={personName}
                onClose={() => setOpenMonth(null)}
              />
            )}
            <CategoryChart data={projection.data} />
            <CommittedTable data={projection.data} />
          </Stack>
        )}
      </QueryState>
    </Stack>
  );
}

function MonthCardTable({
  data,
  onOpen,
  personName,
}: {
  data: Projection;
  onOpen: (month: MonthStr) => void;
  personName: string | null;
}) {
  const names = useNames();
  const owners = unionKeys(data.months.flatMap((m) => [m.by_card, m.states]));
  return (
    <Panel
      title="Mês × cartão"
      icon={<IconTable size={18} stroke={1.7} />}
      description={
        personName
          ? `Parte de ${personName} nos cartões dele(a); adicionais somados no cartão principal. Clique num mês para ver os itens.`
          : "Adicionais somados no cartão principal. Clique num mês para ver os itens."
      }
      interactive={false}
    >
      <Table.ScrollContainer minWidth={700}>
        <Table striped aria-label="Projeção por mês e cartão">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Mês</Table.Th>
              {owners.map((o) => (
                <Table.Th key={o} ta="right">
                  {names.owner(o) || "Sem cartão"}
                </Table.Th>
              ))}
              <Table.Th ta="right" className="et-col-total">
                Total dos cartões
              </Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.months.map((m) => (
              <Table.Tr key={m.month}>
                <Table.Td>
                  <Button
                    variant="subtle"
                    size="compact-sm"
                    onClick={() => onOpen(m.month)}
                    aria-label={`Ver itens de ${formatMonth(m.month)}`}
                  >
                    {formatMonth(m.month)}
                  </Button>
                </Table.Td>
                {owners.map((o) => (
                  <Table.Td key={o} ta="right">
                    <Stack gap={4} align="flex-end">
                      <MoneyText value={m.by_card[o] ?? "0.00"} />
                      <StateBadge state={m.states[o]} />
                    </Stack>
                  </Table.Td>
                ))}
                <Table.Td ta="right" fw={700} className="et-col-total">
                  {formatMoney(m.total)}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th>Total</Table.Th>
              {owners.map((o) => (
                <Table.Th key={o} ta="right">
                  {formatMoney(sumMoney(data.months.map((m) => m.by_card[o])))}
                </Table.Th>
              ))}
              <Table.Th
                ta="right"
                data-testid="projection-total"
                className="et-col-total"
              >
                {formatMoney(sumMoney(data.months.map((m) => m.total)))}
              </Table.Th>
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </Table.ScrollContainer>
    </Panel>
  );
}

function MonthItems({
  month,
  pending,
  userId,
  personName,
  onClose,
}: {
  month: MonthStr;
  pending: boolean;
  userId: string | null;
  personName: string | null;
  onClose: () => void;
}) {
  const names = useNames();
  // R14.2: only card items, and only the selected person's part.
  const path = `/api/reports/month-items${buildQuery({
    month,
    include_pending: pending,
    cards_only: true,
    user_id: userId,
  })}`;
  const items = useGet<MonthItem[]>(["reports", "month-items", path], path);
  const title = personName
    ? `Itens de ${formatMonth(month)} · parte de ${personName}`
    : `Itens de ${formatMonth(month)}`;
  return (
    <Panel
      title={title}
      icon={<IconListDetails size={18} stroke={1.7} />}
      interactive={false}
      className="et-pop-in"
      actions={
        <CloseButton aria-label="Fechar itens do mês" onClick={onClose} />
      }
    >
      <QueryState
        isLoading={items.isLoading}
        error={items.error}
        empty={(items.data?.length ?? 0) === 0}
        emptyText="Nenhum item neste mês."
        emptyIcon={<IconCalendarEvent size={26} stroke={1.6} />}
      >
        <Table.ScrollContainer minWidth={640}>
          <Table aria-label={title}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Data</Table.Th>
                <Table.Th>Descrição</Table.Th>
                <Table.Th>Cartão</Table.Th>
                <Table.Th>Origem</Table.Th>
                <Table.Th ta="right">Valor</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(items.data ?? []).map((item, i) => (
                <Table.Tr key={`${item.ref_id ?? "x"}-${i}`}>
                  <Table.Td>{formatDate(item.purchase_date)}</Table.Td>
                  <Table.Td>{item.description}</Table.Td>
                  <Table.Td>
                    {names.owner(item.card_id ?? item.account_id)}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Text size="sm">
                        {ORIGIN_LABELS[item.origin] ?? item.origin}
                      </Text>
                      {item.forecast && (
                        <StatusBadge tone="accent" size="xs">
                          previsto
                        </StatusBadge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td ta="right">
                    <MoneyText value={item.amount} />
                    {item.total_amount && item.total_amount !== item.amount && (
                      <Text size="xs" c="dimmed">
                        de {formatMoney(item.total_amount)}
                      </Text>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </QueryState>
    </Panel>
  );
}

function CategoryChart({ data }: { data: Projection }) {
  const colors = useChartColors();
  const info = useCategoryInfo();
  const keys = unionKeys(data.months.map((m) => m.by_category ?? {}));
  const rows = data.months.map((m) => {
    const row: Record<string, string | number> = {
      label: formatMonth(m.month),
    };
    for (const k of keys) row[k] = plotValue(m.by_category?.[k]);
    return row;
  });
  return (
    <Panel title="Por categoria" icon={<IconChartBar size={18} stroke={1.7} />}>
      {keys.length === 0 ? (
        <EmptyState
          compact
          icon={<IconChartBar size={22} stroke={1.6} />}
          title="Sem gastos projetados."
        />
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={rows}>
            {chartAxes(colors)}
            {chartTooltip(colors)}
            <Legend
              wrapperStyle={{ color: colors.text, fontSize: 12 }}
              iconType="circle"
              iconSize={8}
            />
            {keys.map((k, i) => {
              const c = info(k);
              return (
                <Bar
                  key={k}
                  dataKey={k}
                  name={c.name}
                  stackId="cat"
                  fill={c.color}
                  maxBarSize={30}
                  radius={i === keys.length - 1 ? [6, 6, 0, 0] : undefined}
                  {...colors.animation}
                />
              );
            })}
          </BarChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

/** R1.9: committed income per user per month; users without income are not listed by the API. */
function CommittedTable({ data }: { data: Projection }) {
  const names = useNames();
  if (data.committed_income.length === 0) return null;
  return (
    <Panel
      title="Renda comprometida"
      icon={<IconScale size={18} stroke={1.7} />}
      interactive={false}
    >
      <Table.ScrollContainer minWidth={900}>
        <Table aria-label="Renda comprometida por mês">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Pessoa</Table.Th>
              {data.months.map((m) => (
                <Table.Th key={m.month}>{formatMonth(m.month)}</Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.committed_income.map((c) => (
              <Table.Tr key={c.user_id}>
                <Table.Td>{names.users[c.user_id] ?? c.user_id}</Table.Td>
                {data.months.map((m) => {
                  const row = c.months.find((r) => r.month === m.month);
                  return (
                    <Table.Td key={m.month}>
                      {row ? (
                        <BandBadge ratio={row.ratio} band={row.band} />
                      ) : (
                        "—"
                      )}
                    </Table.Td>
                  );
                })}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Panel>
  );
}

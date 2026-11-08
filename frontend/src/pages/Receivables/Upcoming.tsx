/**
 * "Próximos recebimentos" (R13.11): one line per card/account and invoice month, by deadline.
 * R13.16: each line can be marked as received/paid (creates a linked settlement) and undone.
 */
import {
  Button,
  Group,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  VisuallyHidden,
} from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  IconArrowBackUp,
  IconCalendarDue,
  IconCalendarTime,
  IconCheck,
} from "@tabler/icons-react";
import { useState } from "react";
import { api } from "../../api/client";
import { useGet, useList, useNames } from "../../api/hooks";
import type {
  ForecastReceivable,
  MarkReceivedBody,
  ReceivableItem,
  Receivables,
  Settlement,
} from "../../api/types";
import { ErrorMessage, QueryState } from "../../components/QueryState";
import { MoneyText, Panel, StatusBadge } from "../../components/ui";
import { addMonths, formatMonth, useMonth } from "../../hooks/month";
import { formatDate, formatMoney, sumMoney } from "../../lib/format";
import { buildQuery } from "../Summary/shared";

/** By deadline (unknown dates last), then invoice month. */
export function byDeadline(a: ReceivableItem, b: ReceivableItem): number {
  if (a.due_date !== b.due_date) {
    if (a.due_date === null) return 1;
    if (b.due_date === null) return -1;
    return a.due_date.localeCompare(b.due_date);
  }
  return a.invoice_month.localeCompare(b.invoice_month);
}

const isPositive = (value: string) => Number(value) > 0;

/** Stable identity of a receivable: (person, direction, card/account, invoice month). */
export function itemKey(it: ReceivableItem): string {
  return [
    it.counterparty_user_id,
    it.direction,
    it.card_id ?? "",
    it.account_id ?? "",
    it.invoice_month,
  ].join("|");
}

/** Who pays whom for a receivable seen from ``me``. */
function payer(me: string, it: ReceivableItem) {
  return it.direction === "receive"
    ? { from: it.counterparty_user_id, to: me }
    : { from: me, to: it.counterparty_user_id };
}

/**
 * The settlement created by mark-received for ``it``: same pair, card/account and invoice month.
 * The newest one wins when there are several (dates compare as ISO strings).
 */
export function findSettlement(
  settlements: Settlement[],
  me: string,
  it: ReceivableItem,
): Settlement | null {
  const { from, to } = payer(me, it);
  const matches = settlements.filter(
    (s) =>
      s.from_user_id === from &&
      s.to_user_id === to &&
      (s.card_id ?? null) === it.card_id &&
      (s.account_id ?? null) === it.account_id &&
      (s.invoice_month ?? null) === it.invoice_month,
  );
  matches.sort((a, b) => a.date.localeCompare(b.date));
  return matches[matches.length - 1] ?? null;
}

function useSettle(me: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries();
  const mark = useMutation({
    mutationFn: (it: ReceivableItem) => {
      const body: MarkReceivedBody = {
        user_id: me,
        counterparty_user_id: it.counterparty_user_id,
        direction: it.direction,
        card_id: it.card_id,
        account_id: it.account_id,
        invoice_month: it.invoice_month,
      };
      return api.post<Settlement>(
        "/api/reports/receivables/mark-received",
        body,
      );
    },
    onSuccess: invalidate,
  });
  const undo = useMutation({
    mutationFn: async (it: ReceivableItem) => {
      // Looked up at click time so the id is never stale.
      const all = await api.get<Settlement[]>("/api/settlements");
      const found = findSettlement(all, me, it);
      if (!found)
        throw new Error(
          "Acerto deste recebimento não encontrado: desfaça em Acertos.",
        );
      return api.del(`/api/settlements/${encodeURIComponent(found.id)}`);
    },
    onSuccess: invalidate,
  });
  return { mark, undo };
}

function ItemsTable({
  title,
  me,
  items,
  hidden,
  flashed,
  onMarked,
  onUndone,
}: {
  title: "Receber" | "Pagar";
  me: string;
  items: ReceivableItem[];
  hidden: number;
  flashed: Set<string>;
  onMarked: (it: ReceivableItem) => void;
  onUndone: (it: ReceivableItem) => void;
}) {
  const names = useNames();
  const { mark, undo } = useSettle(me);
  const [busy, setBusy] = useState<string | null>(null);
  const receiving = title === "Receber";
  const who = receiving ? "Quem deve" : "A quem";
  const doneLabel = receiving ? "recebido" : "pago";
  if (items.length === 0)
    return (
      <Text size="sm" c="dimmed">
        {hidden > 0
          ? receiving
            ? "Tudo recebido."
            : "Tudo pago."
          : receiving
            ? "Nada a receber."
            : "Nada a pagar."}
      </Text>
    );
  const error = mark.error ?? undo.error;
  return (
    <Stack gap="xs">
      {error ? <ErrorMessage error={error} /> : null}
      <Table.ScrollContainer minWidth={720}>
        <Table aria-label={title}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Data limite</Table.Th>
              <Table.Th>{who}</Table.Th>
              <Table.Th>Cartão / conta</Table.Th>
              <Table.Th>Fatura</Table.Th>
              <Table.Th ta="right">Valor</Table.Th>
              <Table.Th>Situação</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((it) => {
              const key = itemKey(it);
              const person =
                names.users[it.counterparty_user_id] ?? it.counterparty_user_id;
              const owner = names.owner(it.card_id ?? it.account_id);
              const describe = `${person}, ${owner}, ${formatMonth(it.invoice_month)}`;
              const received = it.status === "received";
              const start = () => {
                mark.reset();
                undo.reset();
                setBusy(key);
              };
              const opts = (done: (it: ReceivableItem) => void) => ({
                onSuccess: () => done(it),
                onSettled: () => setBusy(null),
              });
              return (
                <Table.Tr
                  key={key}
                  data-status={it.status}
                  className={flashed.has(key) ? "et-settle-flash" : undefined}
                  style={received ? { opacity: 0.72 } : undefined}
                >
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <span>{it.due_date ? formatDate(it.due_date) : "—"}</span>
                      {it.overdue && !received && (
                        <StatusBadge tone="danger">vencido</StatusBadge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>{person}</Table.Td>
                  <Table.Td>{owner}</Table.Td>
                  <Table.Td>{formatMonth(it.invoice_month)}</Table.Td>
                  <Table.Td ta="right">
                    <MoneyText
                      value={received ? it.amount : it.remaining}
                      fw={600}
                      td={received ? "line-through" : undefined}
                    />
                    {it.status === "partial" && (
                      <Text size="xs" c="dimmed">
                        {formatMoney(it.settled)} de {formatMoney(it.amount)}
                      </Text>
                    )}
                    {isPositive(it.settled_month_total) && (
                      <Text size="xs" c="dimmed">
                        já acertado no mês:{" "}
                        <MoneyText value={it.settled_month_total} />
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      {received && (
                        <StatusBadge
                          tone="success"
                          className={flashed.has(key) ? "et-pop-in" : undefined}
                        >
                          {doneLabel}
                        </StatusBadge>
                      )}
                      {it.status === "partial" && (
                        <StatusBadge tone="warning">parcial</StatusBadge>
                      )}
                      {!received && (
                        <Button
                          size="xs"
                          variant="light"
                          color="jade"
                          leftSection={
                            <IconCheck
                              size={14}
                              stroke={2.2}
                              aria-hidden="true"
                            />
                          }
                          aria-label={`${receiving ? "Marcar como recebido" : "Marcar como pago"}: ${describe}`}
                          loading={busy === key && mark.isPending}
                          disabled={busy !== null && busy !== key}
                          onClick={() => {
                            start();
                            mark.mutate(it, opts(onMarked));
                          }}
                        >
                          {receiving
                            ? "Marcar como recebido"
                            : "Marcar como pago"}
                        </Button>
                      )}
                      {it.status !== "open" && (
                        <Button
                          size="xs"
                          variant="subtle"
                          color="gray"
                          leftSection={
                            <IconArrowBackUp
                              size={14}
                              stroke={2}
                              aria-hidden="true"
                            />
                          }
                          aria-label={`Desfazer: ${describe}`}
                          loading={busy === key && undo.isPending}
                          disabled={busy !== null && busy !== key}
                          onClick={() => {
                            start();
                            undo.mutate(it, opts(onUndone));
                          }}
                        >
                          Desfazer
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
    </Stack>
  );
}

/** R14.28: which deadlines "Próximos recebimentos" shows. */
export type Period = "this" | "next" | "all";

/** Month of the deadline (or of the invoice when there is no deadline). */
function deadlineMonth(it: {
  due_date: string | null;
  invoice_month: string;
}): string {
  return it.due_date ? it.due_date.slice(0, 7) : it.invoice_month;
}

export function inPeriod(
  it: {
    due_date: string | null;
    invoice_month: string;
    overdue?: boolean;
    status?: string;
  },
  period: Period,
  current: string,
): boolean {
  if (period === "all") return true;
  // an overdue debt still open is always shown (flagged "vencido"), whatever the period
  if (it.overdue && it.status !== "received") return true;
  const target = period === "this" ? current : addMonths(current, 1);
  return deadlineMonth(it) === target;
}

/** Person filter and deadline period shared by the receivable panels (R14.28). */
export function ReceivableFilters({
  me,
  who,
  onWho,
  period,
  onPeriod,
  pending = false,
}: {
  me: string;
  who: string | null;
  onWho: (who: string | null) => void;
  period: Period;
  onPeriod: (period: Period) => void;
  pending?: boolean;
}) {
  const users = useList("users").data ?? [];
  const { current } = useMonth();
  // R14.28: one tab per person, whatever the kind of spending (confirmed + previsto)
  const path = `/api/reports/receivables${buildQuery({ user_id: me, include_pending: pending })}`;
  const report = useGet<Receivables>(["reports", "receivables", path], path);
  const owed = (id: string) => {
    const open = (report.data?.items ?? []).filter(
      (i) => i.counterparty_user_id === id && i.status !== "received",
    );
    const fc = (report.data?.forecast?.items ?? []).filter(
      (i) => i.counterparty_user_id === id,
    );
    const net = (rows: { direction: string; amount: string }[]) =>
      sumMoney(
        rows.map((i) =>
          i.direction === "receive"
            ? i.amount
            : `-${i.amount}`.replace("--", ""),
        ),
      );
    return {
      confirmed: net(
        open.map((i) => ({ direction: i.direction, amount: i.remaining })),
      ),
      forecast: net(fc),
    };
  };
  const others = users.filter((u) => u.id !== me);
  const chosen = who ? owed(who) : null;
  return (
    <Stack gap="sm" className="et-filters">
      <Tabs
        value={who ?? "all"}
        onChange={(v) => onWho(!v || v === "all" ? null : v)}
        keepMounted={false}
      >
        <Tabs.List aria-label="Pessoa" className="et-tabs-wrap">
          <Tabs.Tab value="all">Todas</Tabs.Tab>
          {others.map((u) => (
            <Tabs.Tab key={u.id} value={u.id}>
              {u.name}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      {who && chosen && (
        <Group gap="xl" aria-label={`Resumo de ${names(users, who)}`}>
          <div>
            <Text size="xs" c="dimmed">
              Confirmado em aberto (saldo: + te deve, − você deve)
            </Text>
            <MoneyText value={chosen.confirmed} fw={700} />
          </div>
          <div>
            <Text size="xs" c="dimmed">
              Previsto (assinaturas, gastos recorrentes, parcelas; este mês e 2
              próximos)
            </Text>
            <MoneyText value={chosen.forecast} fw={700} />
          </div>
        </Group>
      )}
      <Group gap="md" align="flex-end" wrap="wrap">
        <Stack gap={4}>
          <Text size="sm" fw={500} id="et-period-label">
            Vencimento
          </Text>
          <SegmentedControl
            aria-labelledby="et-period-label"
            value={period}
            onChange={(v) => onPeriod(v as Period)}
            data={[
              { value: "this", label: `Este mês (${formatMonth(current)})` },
              {
                value: "next",
                label: `Próximo mês (${formatMonth(addMonths(current, 1))})`,
              },
              { value: "all", label: "Todos em aberto" },
            ]}
          />
        </Stack>
      </Group>
    </Stack>
  );
}

function names(users: { id: string; name: string }[], id: string): string {
  return users.find((u) => u.id === id)?.name ?? id;
}

/** Per-person totals of the visible receivables; a click filters to that person (R14.28). */
function PersonTotals({
  items,
  onWho,
}: {
  items: ReceivableItem[];
  onWho: (who: string | null) => void;
}) {
  const names = useNames();
  const people = new Map<string, { receive: string[]; pay: string[] }>();
  for (const it of items) {
    const p = people.get(it.counterparty_user_id) ?? { receive: [], pay: [] };
    (it.direction === "receive" ? p.receive : p.pay).push(it.remaining);
    people.set(it.counterparty_user_id, p);
  }
  if (people.size === 0) return null;
  return (
    <SimpleGrid
      cols={{ base: 1, sm: 2, lg: 3 }}
      spacing="sm"
      aria-label="Por pessoa"
    >
      {[...people.entries()].map(([id, t]) => (
        <Button
          key={id}
          variant="default"
          h="auto"
          py={8}
          onClick={() => onWho(id)}
          aria-label={`Ver só ${names.users[id] ?? id}`}
          styles={{
            inner: { justifyContent: "space-between" },
            label: { width: "100%" },
          }}
        >
          <Group justify="space-between" w="100%" wrap="nowrap">
            <Text fw={600} size="sm">
              {names.users[id] ?? id}
            </Text>
            <Stack gap={0} align="flex-end">
              {t.receive.length > 0 && (
                <Group gap={6} wrap="nowrap">
                  <Text size="xs" c="dimmed">
                    te deve
                  </Text>
                  <MoneyText
                    value={sumMoney(t.receive)}
                    tone="positive"
                    fw={700}
                    size="sm"
                  />
                </Group>
              )}
              {t.pay.length > 0 && (
                <Group gap={6} wrap="nowrap">
                  <Text size="xs" c="dimmed">
                    você deve
                  </Text>
                  <MoneyText
                    value={sumMoney(t.pay)}
                    tone="negative"
                    fw={700}
                    size="sm"
                  />
                </Group>
              )}
            </Stack>
          </Group>
        </Button>
      ))}
    </SimpleGrid>
  );
}

export function UpcomingReceivables({
  me,
  pending,
  who = null,
  period = "all",
  onWho = () => {},
}: {
  me: string;
  pending: boolean;
  who?: string | null;
  period?: Period;
  onWho?: (who: string | null) => void;
}) {
  const { current } = useMonth();
  const path = `/api/reports/receivables${buildQuery({ user_id: me, include_pending: pending })}`;
  const report = useGet<Receivables>(["reports", "receivables", path], path);
  const [showReceived, setShowReceived] = useState(false);
  // Lines marked in this session stay visible (with "Desfazer") even when received ones are hidden.
  const [flashed, setFlashed] = useState<Set<string>>(new Set());
  const [announce, setAnnounce] = useState("");
  // R14.28: only the chosen person and period, sorted by person then deadline
  const all = [...(report.data?.items ?? [])]
    .filter((i) => (who ? i.counterparty_user_id === who : true))
    .filter((i) => inPeriod(i, period, current))
    .sort(
      (a, b) =>
        a.counterparty_user_id.localeCompare(b.counterparty_user_id) ||
        byDeadline(a, b),
    );
  const sumOf = (direction: ReceivableItem["direction"]) =>
    sumMoney(
      all
        .filter((i) => i.direction === direction && i.status !== "received")
        .map((i) => i.remaining),
    );
  const visible = (i: ReceivableItem) =>
    showReceived || i.status !== "received" || flashed.has(itemKey(i));
  const items = all.filter(visible);
  const hiddenOf = (direction: ReceivableItem["direction"]) =>
    all.filter((i) => i.direction === direction && !visible(i)).length;
  const onMarked = (it: ReceivableItem) => {
    setFlashed((prev) => new Set(prev).add(itemKey(it)));
    setAnnounce(
      it.direction === "receive"
        ? "Marcado como recebido."
        : "Marcado como pago.",
    );
  };
  const onUndone = () => setAnnounce("Marcação desfeita.");
  const tableProps = { me, flashed, onMarked, onUndone };
  return (
    <Panel
      title="Próximos recebimentos"
      icon={<IconCalendarDue size={18} stroke={1.8} />}
      description="Um item por cartão/conta e mês de fatura. A data limite é o vencimento da fatura onde a compra foi feita. Ao marcar como recebido, um acerto vinculado ao cartão/mês é criado."
      actions={
        <Switch
          label="Mostrar recebidos"
          checked={showReceived}
          onChange={(e) => setShowReceived(e.currentTarget.checked)}
        />
      }
      interactive={false}
    >
      <VisuallyHidden role="status" aria-live="polite">
        {announce}
      </VisuallyHidden>
      <QueryState
        isLoading={report.isLoading}
        error={report.error}
        empty={all.length === 0}
        emptyText={
          period === "all"
            ? "Nada pendente para receber ou pagar."
            : "Nada vence nesse período. Escolha “Todos em aberto” para ver o resto."
        }
      >
        <Stack gap="lg">
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <div>
              <Text size="xs" c="dimmed">
                Total a receber
              </Text>
              <MoneyText
                value={sumOf("receive")}
                tone="positive"
                fw={700}
                size="lg"
              />
            </div>
            <div>
              <Text size="xs" c="dimmed">
                Total a pagar
              </Text>
              <MoneyText
                value={sumOf("pay")}
                tone="negative"
                fw={700}
                size="lg"
              />
            </div>
          </SimpleGrid>
          {!who && <PersonTotals items={items} onWho={onWho} />}
          <Stack gap="xs" component="section" aria-label="A receber de outros">
            <Text fw={650}>Receber</Text>
            <ItemsTable
              title="Receber"
              items={items.filter((i) => i.direction === "receive")}
              hidden={hiddenOf("receive")}
              {...tableProps}
            />
          </Stack>
          <Stack gap="xs" component="section" aria-label="A pagar para outros">
            <Text fw={650}>Pagar</Text>
            <ItemsTable
              title="Pagar"
              items={items.filter((i) => i.direction === "pay")}
              hidden={hiddenOf("pay")}
              {...tableProps}
            />
          </Stack>
        </Stack>
      </QueryState>
    </Panel>
  );
}

/**
 * R14.15 "Previsto": what people will owe from subscriptions, recurring purchases and
 * installments split with them, before the invoice/statement arrives. Informative only: it
 * cannot be marked as received and is not in the totals above.
 */
export function ForecastReceivables({
  me,
  pending,
  who = null,
}: {
  me: string;
  pending: boolean;
  who?: string | null;
}) {
  const names = useNames();
  const path = `/api/reports/receivables${buildQuery({ user_id: me, include_pending: pending })}`;
  const report = useGet<Receivables>(["reports", "receivables", path], path);
  const forecast = report.data?.forecast;
  // R14.28: grouped by month, then person (cards summed; the breakdown is shown below)
  const items = (forecast?.items ?? []).filter((i) =>
    who ? i.counterparty_user_id === who : true,
  );
  if (!forecast || items.length === 0) return null;
  const months = [...new Set(items.map((i) => i.invoice_month))].sort();
  const totalOf = (rows: ForecastReceivable[], d: "receive" | "pay") =>
    sumMoney(rows.filter((r) => r.direction === d).map((r) => r.amount));
  return (
    <Panel
      title="Previsto"
      icon={<IconCalendarTime size={18} stroke={1.8} />}
      description="O que vão te dever (ou você vai dever) pelas assinaturas, gastos recorrentes e parcelas divididas, neste mês e nos 2 próximos, por mês e por pessoa. Vira recebimento de verdade quando a fatura ou o extrato chegar."
      interactive={false}
    >
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <div>
            <Text size="xs" c="dimmed">
              Previsto a receber
            </Text>
            <MoneyText
              value={totalOf(items, "receive")}
              tone="positive"
              fw={700}
            />
          </div>
          <div>
            <Text size="xs" c="dimmed">
              Previsto a pagar
            </Text>
            <MoneyText value={totalOf(items, "pay")} tone="negative" fw={700} />
          </div>
        </SimpleGrid>
        <Table.ScrollContainer minWidth={640}>
          <Table aria-label="Previsto">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Mês</Table.Th>
                <Table.Th>Pessoa</Table.Th>
                <Table.Th>De onde</Table.Th>
                <Table.Th ta="right">Valor</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {months.flatMap((m) => {
                const ofMonth = items.filter((i) => i.invoice_month === m);
                const people = [
                  ...new Set(
                    ofMonth.map(
                      (i) => `${i.counterparty_user_id}|${i.direction}`,
                    ),
                  ),
                ];
                return people.map((key, k) => {
                  const [person, direction] = key.split("|") as [
                    string,
                    "receive" | "pay",
                  ];
                  const rows = ofMonth.filter(
                    (i) =>
                      i.counterparty_user_id === person &&
                      i.direction === direction,
                  );
                  return (
                    <Table.Tr key={`${m}-${key}`}>
                      <Table.Td fw={k === 0 ? 600 : undefined}>
                        {k === 0 ? formatMonth(m) : ""}
                      </Table.Td>
                      <Table.Td>
                        {names.users[person] ?? person}{" "}
                        <StatusBadge
                          tone={direction === "receive" ? "success" : "warning"}
                        >
                          {direction === "receive" ? "te deve" : "você deve"}
                        </StatusBadge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">
                          {rows
                            .map(
                              (r) =>
                                `${names.owner(r.card_id ?? r.account_id)} ${formatMoney(r.amount)}`,
                            )
                            .join(" · ")}
                        </Text>
                      </Table.Td>
                      <Table.Td ta="right">
                        <MoneyText
                          value={sumMoney(rows.map((r) => r.amount))}
                          fw={600}
                        />
                      </Table.Td>
                    </Table.Tr>
                  );
                });
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Stack>
    </Panel>
  );
}

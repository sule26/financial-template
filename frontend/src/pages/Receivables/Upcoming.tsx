/**
 * "Próximos recebimentos" (R13.11): one line per card/account and invoice month, by deadline.
 * R13.16: each line can be marked as received/paid (creates a linked settlement) and undone.
 */
import {
  Button,
  Group,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  VisuallyHidden,
} from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  IconArrowBackUp,
  IconCalendarDue,
  IconCheck,
} from "@tabler/icons-react";
import { useState } from "react";
import { api } from "../../api/client";
import { useGet, useNames } from "../../api/hooks";
import type {
  MarkReceivedBody,
  ReceivableItem,
  Receivables,
  Settlement,
} from "../../api/types";
import { ErrorMessage, QueryState } from "../../components/QueryState";
import { MoneyText, Panel, StatusBadge } from "../../components/ui";
import { formatMonth } from "../../hooks/month";
import { formatDate, formatMoney } from "../../lib/format";
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

export function UpcomingReceivables({
  me,
  pending,
}: {
  me: string;
  pending: boolean;
}) {
  const path = `/api/reports/receivables${buildQuery({ user_id: me, include_pending: pending })}`;
  const report = useGet<Receivables>(["reports", "receivables", path], path);
  const [showReceived, setShowReceived] = useState(false);
  // Lines marked in this session stay visible (with "Desfazer") even when received ones are hidden.
  const [flashed, setFlashed] = useState<Set<string>>(new Set());
  const [announce, setAnnounce] = useState("");
  const all = [...(report.data?.items ?? [])].sort(byDeadline);
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
        emptyText="Nada pendente para receber ou pagar."
      >
        <Stack gap="lg">
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <div>
              <Text size="xs" c="dimmed">
                Total a receber
              </Text>
              <MoneyText
                value={report.data?.totals.receive}
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
                value={report.data?.totals.pay}
                tone="negative"
                fw={700}
                size="lg"
              />
            </div>
          </SimpleGrid>
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

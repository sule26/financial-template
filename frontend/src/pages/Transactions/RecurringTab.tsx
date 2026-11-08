import { Button, Group, Modal, Stack, Table } from "@mantine/core";
import { DateField } from "../../components/ui/DateField";
import { notifications } from "@mantine/notifications";
import { useState, type FormEvent } from "react";
import { useAction, useList, useNames } from "../../api/hooks";
import type { RecurringPurchase } from "../../api/types";
import { QueryState, errorText } from "../../components/QueryState";
import { METHOD_LABELS, formatDate, formatMoney } from "../../lib/format";
import { StatusBadge } from "../../components/ui";

const UNIT_LABELS: Record<string, string> = {
  days: "dias",
  weeks: "semanas",
  months: "meses",
};

/** Next expected date: explicit ``next_date`` (after postpone) or ``last_date + every``. */
export function nextDate(rec: RecurringPurchase): string {
  if (rec.next_date) return rec.next_date;
  const [y, m, d] = rec.last_date.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  const { value, unit } = rec.every;
  const date =
    unit === "months"
      ? new Date(Date.UTC(y, m - 1 + value, 1))
      : new Date(Date.UTC(y, m - 1, d + value * (unit === "weeks" ? 7 : 1)));
  if (unit === "months") {
    // clamp to the last day of the target month (31/jan + 1 month = 28/fev)
    const last = new Date(
      Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0),
    ).getUTCDate();
    date.setUTCDate(Math.min(d, last));
  }
  return date.toISOString().slice(0, 10);
}

type Action = { action: "postpone" | "skip" | "end"; date?: string };

export function RecurringTab() {
  const list = useList("recurring-purchases");
  const names = useNames();
  const [postponing, setPostponing] = useState<RecurringPurchase | null>(null);
  const act = useAction<{ id: string } & Action>(
    "post",
    (b) => `/api/recurring-purchases/${encodeURIComponent(b.id)}/action`,
    ({ action, date }) => (date ? { action, date } : { action }),
  );
  const run = (id: string, body: Action, onDone?: () => void) =>
    act.mutate(
      { id, ...body },
      {
        onSuccess: onDone,
        onError: (e) =>
          notifications.show({ message: errorText(e), color: "red" }),
      },
    );
  const rows = list.data ?? [];

  return (
    <>
      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        empty={rows.length === 0}
        emptyText="Nenhuma compra recorrente."
      >
        <Table.ScrollContainer minWidth={800} className="et-table-card">
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Descrição</Table.Th>
                <Table.Th ta="right">Valor estimado</Table.Th>
                <Table.Th>A cada</Table.Th>
                <Table.Th>Última</Table.Th>
                <Table.Th>Próxima prevista</Table.Th>
                <Table.Th>Meio</Table.Th>
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((rec) => {
                const next = nextDate(rec);
                return (
                  <Table.Tr key={rec.id}>
                    <Table.Td>
                      {rec.description}{" "}
                      {!rec.active && (
                        <StatusBadge tone="neutral">encerrada</StatusBadge>
                      )}
                    </Table.Td>
                    <Table.Td ta="right">
                      {formatMoney(rec.estimated_amount)}
                    </Table.Td>
                    <Table.Td>
                      {rec.every.value} {UNIT_LABELS[rec.every.unit]}
                    </Table.Td>
                    <Table.Td>{formatDate(rec.last_date)}</Table.Td>
                    <Table.Td>{rec.active ? formatDate(next) : "—"}</Table.Td>
                    <Table.Td>
                      {METHOD_LABELS[rec.payment_method]}{" "}
                      {names.owner(rec.card_id ?? rec.account_id)}
                    </Table.Td>
                    <Table.Td className="et-sticky-end">
                      {rec.active && (
                        <Group gap={4} wrap="nowrap">
                          <Button
                            size="xs"
                            variant="light"
                            onClick={() => setPostponing(rec)}
                            aria-label={`Adiar ${rec.description}`}
                          >
                            Adiar
                          </Button>
                          <Button
                            size="xs"
                            variant="subtle"
                            onClick={() =>
                              run(rec.id, { action: "skip", date: next })
                            }
                            aria-label={`Pular ${rec.description} de ${formatDate(next)}`}
                          >
                            Pular
                          </Button>
                          <Button
                            size="xs"
                            variant="subtle"
                            color="red"
                            onClick={() => {
                              if (
                                window.confirm(`Encerrar "${rec.description}"?`)
                              )
                                run(rec.id, { action: "end" });
                            }}
                            aria-label={`Encerrar ${rec.description}`}
                          >
                            Encerrar
                          </Button>
                        </Group>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </QueryState>
      <Modal
        opened={postponing !== null}
        onClose={() => setPostponing(null)}
        title="Adiar compra recorrente"
      >
        {postponing && (
          <PostponeForm
            initial={nextDate(postponing)}
            onSubmit={(date) =>
              run(postponing.id, { action: "postpone", date }, () =>
                setPostponing(null),
              )
            }
          />
        )}
      </Modal>
    </>
  );
}

function PostponeForm({
  initial,
  onSubmit,
}: {
  initial: string;
  onSubmit: (date: string) => void;
}) {
  const [date, setDate] = useState(initial);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (date) onSubmit(date);
  };
  return (
    <form onSubmit={submit}>
      <Stack gap="sm">
        <DateField
          label="Nova data prevista"
          value={date}
          onChange={setDate}
          required
        />
        <Group justify="flex-end">
          <Button type="submit">Adiar</Button>
        </Group>
      </Stack>
    </form>
  );
}

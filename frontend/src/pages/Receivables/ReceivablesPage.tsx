/** A receber (R6.4, R6.5, R6.13, R8.9; docs/08 "Saldos" e "Acertos"). */
import {
  Accordion,
  Alert,
  Avatar,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { todayIso } from "../../lib/dates";
import { DateField } from "../../components/ui/DateField";
import { MonthField } from "../../components/ui/MonthField";
import {
  IconArrowsExchange,
  IconReceiptRefund,
  IconUsersGroup,
} from "@tabler/icons-react";
import { useState } from "react";
import { knownPeople, readDefaultPeople } from "../../hooks/defaultPeople";
import { useGet, useList, useNames, useRemove, useSave } from "../../api/hooks";
import type { Balances, Settlement } from "../../api/types";
import { ErrorMessage, QueryState } from "../../components/QueryState";
import { PageHeader, StatusBadge } from "../../components/ui";
import { formatMonth, useMonth } from "../../hooks/month";
import { formatDate, formatMoney, parseMoneyInput } from "../../lib/format";
import { buildQuery, PendingSwitch, PersonSelect } from "../Summary/shared";
import {
  ForecastReceivables,
  ReceivableFilters,
  UpcomingReceivables,
  type Period,
} from "./Upcoming";

/** Absolute value of a decimal string, without going through floats. */
function abs(value: string): string {
  return value.startsWith("-") ? value.slice(1) : value;
}

function sign(value: string): -1 | 0 | 1 {
  if (/^-?0+(\.0+)?$/.test(value)) return 0;
  return value.startsWith("-") ? -1 : 1;
}

/** Plain-language balance: positive = the other person owes me. */
export function balanceText(net: string, other: string): string {
  const s = sign(net);
  if (s === 0) return `Vocês estão quites com ${other}`;
  return s > 0
    ? `${other} te deve ${formatMoney(abs(net))}`
    : `Você deve ${formatMoney(abs(net))} a ${other}`;
}

export function ReceivablesPage() {
  const users = useList("users");
  const [chosen, setChosen] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  // R14.28: who owes (one person or everybody) and which deadlines to show
  const [who, setWho] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("next");
  // R14.25: "Eu sou" starts with the first default person of Configurações
  const preferred = knownPeople(readDefaultPeople(), users.data)[0];
  const me = chosen ?? preferred ?? users.data?.[0]?.id ?? null;
  const path = me
    ? `/api/reports/balances${buildQuery({ user_id: me, include_pending: pending })}`
    : null;
  const balances = useGet<Balances>(["reports", "balances", path], path);

  return (
    <Stack gap="xl">
      <PageHeader
        title="A receber"
        eyebrow="Movimento"
        icon={<IconUsersGroup size={22} stroke={1.7} />}
        subtitle="Quem deve a quem, mês a mês, com os acertos já feitos."
        actions={
          <Button
            onClick={() => setModalOpen(true)}
            disabled={!me}
            leftSection={
              <IconArrowsExchange size={16} stroke={2} aria-hidden="true" />
            }
          >
            Registrar acerto
          </Button>
        }
      >
        <PersonSelect
          value={me}
          onChange={(v) => {
            setChosen(v);
            setWho(null); // R14.28: the person filter belongs to the previous "Eu sou"
          }}
          label="Eu sou"
          allowAll={false}
        />
        <PendingSwitch checked={pending} onChange={setPending} />
      </PageHeader>
      {me && (
        <ReceivableFilters
          me={me}
          who={who}
          onWho={setWho}
          period={period}
          onPeriod={setPeriod}
          pending={pending}
        />
      )}
      {me && (
        <UpcomingReceivables
          me={me}
          pending={pending}
          who={who}
          period={period}
          onWho={setWho}
        />
      )}
      {me && <ForecastReceivables me={me} pending={pending} who={who} />}
      <QueryState
        isLoading={users.isLoading || balances.isLoading}
        error={users.error ?? balances.error}
        empty={!me || (balances.data?.people.length ?? 0) === 0}
        emptyText="Nenhum saldo com outras pessoas."
        emptyIcon={<IconReceiptRefund size={26} stroke={1.6} />}
      >
        {balances.data && (
          <BalancesView
            data={
              who
                ? {
                    ...balances.data,
                    people: balances.data.people.filter(
                      (p) => p.user_id === who,
                    ),
                  }
                : balances.data
            }
          />
        )}
      </QueryState>
      {me && (
        <SettlementModal
          opened={modalOpen}
          onClose={() => setModalOpen(false)}
          me={me}
          defaultFrom={balances.data?.people[0]?.user_id ?? null}
        />
      )}
    </Stack>
  );
}

function BalancesView({ data }: { data: Balances }) {
  const names = useNames();
  const name = (id: string) => names.users[id] ?? id;
  return (
    <Stack>
      {data.incomplete_months.length > 0 && (
        <Alert
          color="yellow"
          variant="light"
          radius="lg"
          title="Saldos incompletos"
        >
          Falta fatura/extrato em{" "}
          {data.incomplete_months.map(formatMonth).join(", ")}: o saldo desses
          meses usa a projeção e pode mudar.
        </Alert>
      )}
      <Accordion
        multiple
        variant="separated"
        radius="lg"
        className="et-stagger"
      >
        {data.people.map((p) => (
          <Accordion.Item key={p.user_id} value={p.user_id}>
            <Accordion.Control
              icon={
                <Avatar
                  radius="xl"
                  size={36}
                  color={sign(p.net) < 0 ? "red" : "jade"}
                  variant="light"
                  aria-hidden="true"
                >
                  {name(p.user_id).slice(0, 1).toUpperCase()}
                </Avatar>
              }
            >
              <Text
                fw={650}
                className="et-num"
                c={
                  sign(p.net) < 0 ? "red" : sign(p.net) > 0 ? "jade" : undefined
                }
              >
                {balanceText(p.net, name(p.user_id))}
              </Text>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack>
                {p.months.length === 0 && (
                  <Text size="sm" c="dimmed">
                    Sem lançamentos.
                  </Text>
                )}
                {p.months.map((m) => (
                  <MonthBlock
                    key={m.month}
                    month={m}
                    other={name(p.user_id)}
                    name={name}
                  />
                ))}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}

function MonthBlock({
  month,
  other,
  name,
}: {
  month: Balances["people"][number]["months"][number];
  other: string;
  name: (id: string) => string;
}) {
  const label = formatMonth(month.month);
  return (
    <Stack gap="xs" component="section" aria-label={`Saldo de ${label}`}>
      <Group gap="xs">
        <Title order={4} size="h5">
          {label}
        </Title>
        <Text size="sm">{balanceText(month.net, other)}</Text>
        {month.incomplete && (
          <StatusBadge tone="warning">incompleto</StatusBadge>
        )}
      </Group>
      {month.lines.length > 0 && (
        <Table aria-label={`Lançamentos de ${label}`}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Lançamento</Table.Th>
              <Table.Th ta="right">Valor (+ te deve / − você deve)</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {month.lines.map((ln, i) => (
              <Table.Tr key={`${ln.ref_id}-${i}`}>
                <Table.Td>{ln.description}</Table.Td>
                <Table.Td ta="right">{formatMoney(ln.amount)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {month.settlements.map((s) => (
        <SettlementRow key={s.id} settlement={s} name={name} />
      ))}
    </Stack>
  );
}

function SettlementRow({
  settlement,
  name,
}: {
  settlement: Settlement;
  name: (id: string) => string;
}) {
  const remove = useRemove("settlements");
  const [confirming, setConfirming] = useState(false);
  const s = settlement;
  return (
    <Stack gap={4}>
      <Group gap="xs">
        <StatusBadge tone="accent">acerto</StatusBadge>
        <Text size="sm">
          {name(s.from_user_id)} pagou {formatMoney(s.amount)} para{" "}
          {name(s.to_user_id)} em {formatDate(s.date)}
          {s.note ? ` — ${s.note}` : ""}
        </Text>
        {s.origin.type === "manual" &&
          (confirming ? (
            <Group gap={4}>
              <Button
                size="compact-xs"
                color="red"
                loading={remove.isPending}
                onClick={() => remove.mutate(s.id)}
              >
                Confirmar exclusão
              </Button>
              <Button
                size="compact-xs"
                variant="default"
                onClick={() => setConfirming(false)}
              >
                Cancelar
              </Button>
            </Group>
          ) : (
            <Button
              size="compact-xs"
              variant="subtle"
              color="red"
              onClick={() => setConfirming(true)}
              aria-label={`Excluir acerto de ${formatMoney(s.amount)}`}
            >
              Excluir
            </Button>
          ))}
      </Group>
      {s.warnings.length > 0 && (
        <Alert color="orange" variant="light" title="Origem removida">
          {s.warnings.join("; ")}
        </Alert>
      )}
      {remove.error && <ErrorMessage error={remove.error} />}
    </Stack>
  );
}

function SettlementModal({
  opened,
  onClose,
  me,
  defaultFrom,
}: {
  opened: boolean;
  onClose: () => void;
  me: string;
  defaultFrom: string | null;
}) {
  const { selected } = useMonth();
  const users = useList("users");
  const save = useSave("settlements");
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso);
  const [month, setMonth] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const fromValue = from ?? defaultFrom;
  const toValue = to ?? me;
  const monthValue = month ?? selected;
  const parsed = parseMoneyInput(amount);
  const amountError =
    submitted && (parsed === null || sign(parsed) <= 0)
      ? "Informe um valor positivo"
      : null;
  const sameError =
    submitted && fromValue && fromValue === toValue
      ? "Escolha pessoas diferentes"
      : null;
  const options = (users.data ?? []).map((u) => ({
    value: u.id,
    label: u.name,
  }));

  const close = () => {
    setFrom(null);
    setTo(null);
    setAmount("");
    setMonth(null);
    setNote("");
    setSubmitted(false);
    save.reset();
    onClose();
  };

  const submit = () => {
    setSubmitted(true);
    if (!fromValue || !toValue || fromValue === toValue) return;
    if (
      parsed === null ||
      sign(parsed) <= 0 ||
      !date ||
      !/^\d{4}-\d{2}$/.test(monthValue)
    )
      return;
    save.mutate(
      {
        from_user_id: fromValue,
        to_user_id: toValue,
        amount: parsed,
        date,
        month: monthValue,
        note: note.trim() || null,
      },
      { onSuccess: close },
    );
  };

  return (
    <Modal
      opened={opened}
      onClose={close}
      title="Registrar acerto"
      classNames={{ content: "et-modal", title: "et-modal__title" }}
    >
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Stack>
          <Select
            label="De (quem pagou)"
            data={options}
            value={fromValue}
            onChange={setFrom}
            required
            error={submitted && !fromValue ? "Obrigatório" : null}
          />
          <Select
            label="Para (quem recebeu)"
            data={options}
            value={toValue}
            onChange={setTo}
            required
            error={sameError}
          />
          <TextInput
            label="Valor"
            placeholder="0,00"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.currentTarget.value)}
            required
            error={amountError}
          />
          <DateField
            label="Data"
            value={date}
            onChange={setDate}
            required
            error={submitted && !date ? "Obrigatório" : null}
          />
          <MonthField
            label="Mês de referência"
            value={monthValue}
            onChange={setMonth}
            required
            error={
              submitted && !/^\d{4}-\d{2}$/.test(monthValue)
                ? "Escolha o mês"
                : null
            }
          />
          <Textarea
            label="Nota"
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
          />
          {save.error && <ErrorMessage error={save.error} />}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancelar
            </Button>
            <Button type="submit" loading={save.isPending}>
              Salvar acerto
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

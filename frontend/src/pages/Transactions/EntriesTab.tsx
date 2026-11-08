import {
  Button,
  Checkbox,
  Group,
  Modal,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { DateField } from "../../components/ui/DateField";
import { notifications } from "@mantine/notifications";
import { IconFilterOff } from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useAction,
  useGet,
  useList,
  useNames,
  useOwnerLabels,
} from "../../api/hooks";
import type { Allocation, Kind, Transaction } from "../../api/types";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { useDefaultSplit } from "../../components/defaultSplit";
import {
  checkPayment,
  PaymentTarget,
  paymentBody,
  type PaymentDraft,
} from "../Catalog/shared";
import { CategorySelect } from "../../components/CategorySelect";
import { QueryState, errorText } from "../../components/QueryState";
import {
  KIND_LABELS,
  METHOD_LABELS,
  formatDate,
  formatMoney,
  parseMoneyInput,
} from "../../lib/format";
import { formatMonth, useMonth } from "../../hooks/month";
import { MoneyText, StatusBadge } from "../../components/ui";

interface Filters {
  card_id: string | null;
  account_id: string | null;
  payment_method: string | null;
  q: string;
  provisional: boolean;
}

/** Query string for GET /api/transactions; "sem categoria" ignores the month (R1.12). */
export function transactionsQuery(
  month: string,
  uncategorized: boolean,
  f: Filters,
): string {
  const qs = new URLSearchParams();
  if (uncategorized) qs.set("uncategorized", "true");
  else qs.set("month", month);
  if (f.card_id) qs.set("card_id", f.card_id);
  if (f.account_id) qs.set("account_id", f.account_id);
  if (f.payment_method) qs.set("payment_method", f.payment_method);
  if (f.q.trim()) qs.set("q", f.q.trim());
  if (f.provisional) qs.set("provisional", "true");
  return qs.toString();
}

function originBadge(tx: Transaction) {
  if (tx.provisional) return <StatusBadge tone="warning">previsto</StatusBadge>;
  if (tx.source.type === "import")
    return <StatusBadge tone="info">importado</StatusBadge>;
  return <StatusBadge tone="neutral">manual</StatusBadge>;
}

export function EntriesTab() {
  const { selected: month } = useMonth();
  const [params, setParams] = useSearchParams();
  const uncategorized = params.get("uncategorized") === "1";
  const [filters, setFilters] = useState<Filters>({
    card_id: null,
    account_id: null,
    payment_method: null,
    q: "",
    provisional: false,
  });
  const cards = useList("cards");
  const accounts = useList("accounts");
  const ownerLabel = useOwnerLabels();
  const names = useNames();
  const qs = transactionsQuery(month, uncategorized, filters);
  const list = useGet<Transaction[]>(
    ["transactions", qs],
    `/api/transactions?${qs}`,
  );
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [batchCategory, setBatchCategory] = useState<string | null>(null);
  const [editing, setEditing] = useState<Transaction | null>(null);

  const recategorize = useAction<
    { ids: string[]; category_id: string },
    { updated: number }
  >("post", () => "/api/transactions/recategorize");
  const remove = useAction<string>(
    "del",
    (id) => `/api/transactions/${encodeURIComponent(id)}`,
  );

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));
  const toggleUncategorized = (on: boolean) => {
    const next = new URLSearchParams(params);
    if (on) next.set("uncategorized", "1");
    else next.delete("uncategorized");
    setParams(next);
  };

  const rows = list.data ?? [];
  const visibleIds = rows.map((t) => t.id);
  const selectedIds = visibleIds.filter((id) => selection.has(id));
  const allSelected =
    visibleIds.length > 0 && selectedIds.length === visibleIds.length;
  const toggle = (id: string) =>
    setSelection((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const applyBatch = () => {
    if (!batchCategory || selectedIds.length === 0) return;
    recategorize.mutate(
      { ids: selectedIds, category_id: batchCategory },
      {
        onSuccess: (r) => {
          notifications.show({
            message: `${r?.updated ?? selectedIds.length} item(ns) recategorizado(s).`,
            color: "green",
          });
          setSelection(new Set());
        },
        onError: (e) =>
          notifications.show({ message: errorText(e), color: "red" }),
      },
    );
  };

  const confirmDelete = (tx: Transaction) => {
    if (!window.confirm(`Excluir o lançamento "${tx.description}"?`)) return;
    remove.mutate(tx.id, {
      onError: (e) =>
        notifications.show({ message: errorText(e), color: "red" }),
    });
  };

  return (
    <Stack>
      <Group align="flex-end" wrap="wrap" className="et-filters">
        <Select
          label="Cartão"
          clearable
          data={(cards.data ?? []).map((c) => ({
            value: c.id,
            label: ownerLabel[c.id] ?? c.name,
          }))}
          value={filters.card_id}
          onChange={(v) => setFilter("card_id", v)}
        />
        <Select
          label="Conta"
          clearable
          data={(accounts.data ?? []).map((a) => ({
            value: a.id,
            label: ownerLabel[a.id] ?? a.name,
          }))}
          value={filters.account_id}
          onChange={(v) => setFilter("account_id", v)}
        />
        <Select
          label="Meio"
          clearable
          data={Object.entries(METHOD_LABELS)
            .filter(([k]) => k !== "account")
            .map(([value, label]) => ({ value, label }))}
          value={filters.payment_method}
          onChange={(v) => setFilter("payment_method", v)}
        />
        <TextInput
          label="Buscar"
          placeholder="descrição"
          value={filters.q}
          onChange={(e) => setFilter("q", e.currentTarget.value)}
        />
        <Switch
          label="Sem categoria"
          checked={uncategorized}
          onChange={(e) => toggleUncategorized(e.currentTarget.checked)}
        />
        <Switch
          label="Só previstos"
          checked={filters.provisional}
          onChange={(e) => setFilter("provisional", e.currentTarget.checked)}
        />
      </Group>
      <Text size="sm" c="dimmed">
        {uncategorized
          ? "Todos os meses: lançamentos sem categoria"
          : `Mês de fatura ${formatMonth(month)}`}
      </Text>
      {selectedIds.length > 0 && (
        <Group align="flex-end">
          <CategorySelect
            label="Nova categoria"
            value={batchCategory}
            onChange={setBatchCategory}
          />
          <Button
            onClick={applyBatch}
            disabled={!batchCategory}
            loading={recategorize.isPending}
          >
            Recategorizar ({selectedIds.length})
          </Button>
        </Group>
      )}
      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        empty={rows.length === 0}
        emptyText="Nenhum lançamento com esses filtros."
        emptyIcon={<IconFilterOff size={26} stroke={1.6} />}
      >
        <Table.ScrollContainer minWidth={800} className="et-table-card">
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>
                  <Checkbox
                    aria-label="Selecionar todos"
                    checked={allSelected}
                    indeterminate={selectedIds.length > 0 && !allSelected}
                    onChange={() =>
                      setSelection(
                        allSelected ? new Set() : new Set(visibleIds),
                      )
                    }
                  />
                </Table.Th>
                <Table.Th>Data</Table.Th>
                <Table.Th>Descrição</Table.Th>
                <Table.Th ta="right">Valor</Table.Th>
                <Table.Th>Categoria</Table.Th>
                <Table.Th>Meio</Table.Th>
                <Table.Th>Dono</Table.Th>
                <Table.Th>Origem</Table.Th>
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((tx) => (
                <Table.Tr key={tx.id}>
                  <Table.Td>
                    <Checkbox
                      aria-label={`Selecionar ${tx.description}`}
                      checked={selection.has(tx.id)}
                      onChange={() => toggle(tx.id)}
                    />
                  </Table.Td>
                  <Table.Td>{formatDate(tx.purchase_date)}</Table.Td>
                  <Table.Td>
                    {tx.description}
                    {tx.installment && (
                      <Text span size="xs" c="dimmed">
                        {" "}
                        ({tx.installment.n}/{tx.installment.of})
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td ta="right">
                    <MoneyText value={tx.amount} fw={600} />
                  </Table.Td>
                  <Table.Td>
                    {tx.category_id ? (
                      (names.categories[tx.category_id] ?? tx.category_id)
                    ) : (
                      <StatusBadge tone="danger">sem categoria</StatusBadge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {METHOD_LABELS[tx.payment_method] ?? tx.payment_method}
                  </Table.Td>
                  <Table.Td>
                    {names.owner(tx.card_id ?? tx.account_id)}
                  </Table.Td>
                  <Table.Td>{originBadge(tx)}</Table.Td>
                  <Table.Td className="et-sticky-end">
                    <Group gap={4} wrap="nowrap">
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() => setEditing(tx)}
                        aria-label={`Editar ${tx.description}`}
                      >
                        Editar
                      </Button>
                      {tx.source.type === "manual" && (
                        <Button
                          size="xs"
                          variant="subtle"
                          color="red"
                          onClick={() => confirmDelete(tx)}
                          aria-label={`Excluir ${tx.description}`}
                        >
                          Excluir
                        </Button>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </QueryState>
      <PlannedInstallments month={month} />
      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title="Editar lançamento"
        classNames={{ content: "et-modal", title: "et-modal__title" }}
      >
        {editing && (
          <EditTransactionForm tx={editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
    </Stack>
  );
}

/** Edit form: classification fields always; description/amount/date only for manual entries. */
export function EditTransactionForm({
  tx,
  onDone,
}: {
  tx: Transaction;
  onDone: () => void;
}) {
  const manual = tx.source.type === "manual";
  // R14.23: a manual entry can move to another payment method / card / account.
  const [payment, setPayment] = useState<PaymentDraft>({
    payment_method: tx.payment_method,
    card_id: tx.card_id,
    account_id: tx.account_id,
  });
  const defaultHint = useDefaultSplit(payment.card_id, payment.account_id);
  const [categoryId, setCategoryId] = useState<string | null>(tx.category_id);
  const [allocations, setAllocations] = useState<Allocation | null>(
    tx.allocations,
  );
  const [note, setNote] = useState(tx.note ?? "");
  const [kind, setKind] = useState<Kind>(tx.kind);
  const [description, setDescription] = useState(tx.description);
  const [amountText, setAmountText] = useState(tx.amount.replace(".", ","));
  const [date, setDate] = useState(tx.purchase_date);
  const [error, setError] = useState<string | null>(null);
  const save = useAction<Record<string, unknown>, Transaction>(
    "patch",
    () => `/api/transactions/${encodeURIComponent(tx.id)}`,
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!categoryId) return setError("Categoria é obrigatória");
    if (!allocationValid(allocations))
      return setError("Divisão inválida: os percentuais precisam somar 100%");
    const body: Record<string, unknown> = {
      category_id: categoryId,
      allocations,
      note: note.trim() || null,
      kind,
    };
    if (manual) {
      const paymentError = checkPayment(payment);
      if (paymentError) return setError(paymentError);
      if (
        payment.payment_method !== tx.payment_method ||
        payment.card_id !== tx.card_id ||
        payment.account_id !== tx.account_id
      )
        Object.assign(body, paymentBody(payment));
      const amount = parseMoneyInput(amountText);
      if (!amount) return setError("Valor inválido");
      if (!description.trim()) return setError("Informe a descrição");
      Object.assign(body, {
        description: description.trim(),
        amount,
        purchase_date: date,
      });
    }
    setError(null);
    save.mutate(body, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="sm">
        {manual ? (
          <>
            <PaymentTarget
              value={payment}
              onChange={(patch) => setPayment((p) => ({ ...p, ...patch }))}
            />
            <TextInput
              label="Descrição"
              value={description}
              onChange={(e) => setDescription(e.currentTarget.value)}
            />
            <TextInput
              label="Valor"
              inputMode="decimal"
              value={amountText}
              onChange={(e) => setAmountText(e.currentTarget.value)}
            />
            <DateField label="Data" value={date} onChange={setDate} />
          </>
        ) : (
          <Text size="sm">
            {formatDate(tx.purchase_date)} · {tx.description} ·{" "}
            {formatMoney(tx.amount)}
          </Text>
        )}
        <Select
          label="Tipo"
          data={Object.entries(KIND_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
          value={kind}
          onChange={(v) => v && setKind(v as Kind)}
          allowDeselect={false}
        />
        <CategorySelect value={categoryId} onChange={setCategoryId} />
        <AllocationPicker
          value={allocations}
          onChange={setAllocations}
          defaultHint={defaultHint}
        />
        <TextInput
          label="Nota"
          value={note}
          onChange={(e) => setNote(e.currentTarget.value)}
        />
        {(error || save.error) && (
          <Text c="red" size="sm" role="alert">
            {error ?? errorText(save.error)}
          </Text>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Cancelar
          </Button>
          <Button type="submit" loading={save.isPending}>
            Salvar
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

/** One item of GET /api/reports/month-items, as far as this panel needs it. */
interface PlannedItem {
  description: string;
  amount: string;
  origin: string;
  card_id: string | null;
  account_id: string | null;
  ref_id: string | null;
  purchase_date: string | null;
  installment: { n: number; of: number } | null;
}

const PLANNED_ORIGINS = ["plan", "anticipation", "subscription", "recurring"];

function plannedBadge(i: PlannedItem) {
  if (i.installment)
    return (
      <StatusBadge tone="neutral">
        parcela {i.installment.n}/{i.installment.of}
      </StatusBadge>
    );
  if (i.origin === "anticipation")
    return <StatusBadge tone="accent">antecipação</StatusBadge>;
  if (i.origin === "subscription")
    return <StatusBadge tone="accent">assinatura</StatusBadge>;
  return <StatusBadge tone="accent">gasto recorrente</StatusBadge>;
}

/**
 * R14.19 + R14.29: what is still expected this month and not launched yet — installments
 * (with "parcela N/M"), subscriptions and gastos recorrentes (contas da casa included). They
 * become real lançamentos when the invoice/statement is imported or the payment is registered.
 */
export function PlannedInstallments({ month }: { month: string }) {
  const names = useNames();
  const path = `/api/reports/month-items?month=${encodeURIComponent(month)}`;
  const items = useGet<PlannedItem[]>(["reports", "month-items", path], path);
  const planned = (items.data ?? []).filter((i) =>
    PLANNED_ORIGINS.includes(i.origin),
  );
  if (planned.length === 0) return null;
  return (
    <Stack gap={6} mt="lg" component="section" aria-label="Previstos neste mês">
      <Text fw={650}>Previstos neste mês</Text>
      <Text size="xs" c="dimmed">
        Parcelas, assinaturas e gastos recorrentes que ainda não viraram
        lançamento: viram quando a fatura/extrato for importada (ou o pagamento
        da conta for registrado).
      </Text>
      <Table.ScrollContainer minWidth={640} className="et-table-card">
        <Table aria-label="Previstos neste mês">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Descrição</Table.Th>
              <Table.Th>Tipo</Table.Th>
              <Table.Th>Data</Table.Th>
              <Table.Th>Cartão / conta</Table.Th>
              <Table.Th ta="right">Valor</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {planned.map((i, k) => (
              <Table.Tr key={`${i.origin}-${i.ref_id}-${k}`}>
                <Table.Td>{i.description}</Table.Td>
                <Table.Td>{plannedBadge(i)}</Table.Td>
                <Table.Td>
                  {i.purchase_date ? formatDate(i.purchase_date) : "—"}
                </Table.Td>
                <Table.Td>{names.owner(i.card_id ?? i.account_id)}</Table.Td>
                <Table.Td ta="right">{formatMoney(i.amount)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}

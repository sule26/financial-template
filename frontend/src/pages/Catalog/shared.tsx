/** Shared building blocks for the catalog tabs: generic CRUD table + modal, field helpers. */
import {
  Alert,
  Button,
  Group,
  Modal,
  NativeSelect,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { useState, type ComponentType, type ReactNode } from "react";
import {
  useList,
  useOwnerLabels,
  useRemove,
  useSave,
  type Resource,
  type ResourceMap,
} from "../../api/hooks";
import {
  isSplitRef,
  type Allocation,
  type PaymentMethod,
} from "../../api/types";
import { ErrorMessage, QueryState } from "../../components/QueryState";
import { formatPct, METHOD_LABELS, parseMoneyInput } from "../../lib/format";

export const MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
export const DATE_RE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** Empty text -> null; otherwise trimmed text. */
export const orNull = (text: string | null | undefined): string | null => {
  const t = (text ?? "").trim();
  return t ? t : null;
};

/** Money text typed by the user -> canonical decimal string; "" stays null. */
export function moneyOrNull(text: string): string | null {
  return text.trim() ? parseMoneyInput(text) : null;
}

/** "1234.50" -> "1234,50" so editing round-trips with parseMoneyInput. */
export function moneyToInput(value: string | null | undefined): string {
  return value ? value.replace(".", ",") : "";
}

/** Validates an optional money field; returns an error message or null. */
export function checkMoney(
  text: string,
  label: string,
  required = false,
): string | null {
  if (!text.trim()) return required ? `${label}: obrigatório` : null;
  return parseMoneyInput(text) === null ? `${label}: valor inválido` : null;
}

export interface FormProps<D> {
  draft: D;
  set: (patch: Partial<D>) => void;
}

export interface Column<T> {
  header: string;
  cell: (item: T) => ReactNode;
}

interface CrudTabProps<R extends Resource, D> {
  resource: R;
  title: string;
  noun: string;
  columns: Column<ResourceMap[R]>[];
  rowName: (item: ResourceMap[R]) => string;
  blank: () => D;
  fromItem: (item: ResourceMap[R]) => D;
  toBody: (draft: D) => Partial<ResourceMap[R]>;
  validate?: (draft: D) => string | null;
  form: ComponentType<FormProps<D>>;
  deleteWarning?: ReactNode;
  deleteResult?: (result: {
    uncategorized?: Record<string, number>;
  }) => ReactNode;
  intro?: ReactNode;
  emptyText?: string;
}

/** Generic list + "Novo" + edit modal + delete confirmation for one catalog resource. */
export function CrudTab<R extends Resource, D>(props: CrudTabProps<R, D>) {
  const { resource, title, noun, columns, rowName } = props;
  const list = useList(resource);
  const save = useSave(resource);
  const remove = useRemove(resource);
  const [editing, setEditing] = useState<{
    item: ResourceMap[R] | null;
    draft: D;
  } | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ResourceMap[R] | null>(null);
  const [deleted, setDeleted] = useState<ReactNode>(null);
  const Form = props.form;

  const open = (item: ResourceMap[R] | null) => {
    save.reset();
    setInvalid(null);
    setDeleted(null);
    setEditing({ item, draft: item ? props.fromItem(item) : props.blank() });
  };
  const set = (patch: Partial<D>) =>
    setEditing((e) => (e ? { ...e, draft: { ...e.draft, ...patch } } : e));

  const submit = () => {
    if (!editing) return;
    const problem = props.validate?.(editing.draft) ?? null;
    setInvalid(problem);
    if (problem) return;
    const body = props.toBody(editing.draft);
    // Editing keeps fields this form does not manage (e.g. skipped_dates, snapshots).
    const payload = editing.item ? { ...editing.item, ...body } : body;
    save.mutate(payload, { onSuccess: () => setEditing(null) });
  };

  const confirmDelete = () => {
    if (!deleting) return;
    remove.mutate(deleting.id, {
      onSuccess: (result) => {
        setDeleting(null);
        setDeleted(props.deleteResult?.(result ?? {}) ?? null);
      },
    });
  };

  const rows = list.data ?? [];
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={3}>{title}</Title>
        <Button
          onClick={() => open(null)}
          leftSection={<IconPlus size={16} stroke={2.2} aria-hidden="true" />}
        >
          Novo
        </Button>
      </Group>
      {props.intro}
      {deleted}
      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        empty={rows.length === 0}
        emptyText={props.emptyText ?? `Nenhum ${noun} cadastrado.`}
      >
        <Table.ScrollContainer minWidth={600} className="et-table-card">
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                {columns.map((c) => (
                  <Table.Th key={c.header}>{c.header}</Table.Th>
                ))}
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((item) => (
                <Table.Tr key={item.id}>
                  {columns.map((c) => (
                    <Table.Td key={c.header}>{c.cell(item)}</Table.Td>
                  ))}
                  <Table.Td className="et-sticky-end">
                    <Group gap={4} wrap="nowrap">
                      <Button
                        size="xs"
                        variant="light"
                        aria-label={`Editar ${rowName(item)}`}
                        onClick={() => open(item)}
                      >
                        Editar
                      </Button>
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        aria-label={`Excluir ${rowName(item)}`}
                        onClick={() => {
                          remove.reset();
                          setDeleting(item);
                        }}
                      >
                        Excluir
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </QueryState>

      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.item ? `Editar ${noun}` : `Novo ${noun}`}
        size="lg"
        classNames={{ content: "et-modal", title: "et-modal__title" }}
      >
        {editing && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <Stack gap="sm">
              <Form draft={editing.draft} set={set} />
              {invalid && (
                <Alert color="red" role="alert" title="Verifique os campos">
                  {invalid}
                </Alert>
              )}
              {save.error && <ErrorMessage error={save.error} />}
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setEditing(null)}>
                  Cancelar
                </Button>
                <Button type="submit" loading={save.isPending}>
                  Salvar
                </Button>
              </Group>
            </Stack>
          </form>
        )}
      </Modal>

      <Modal
        opened={deleting !== null}
        onClose={() => setDeleting(null)}
        title={`Excluir ${noun}`}
      >
        {deleting && (
          <Stack gap="sm">
            <Text>
              Excluir “{rowName(deleting)}”? Esta ação não pode ser desfeita.
            </Text>
            {props.deleteWarning}
            {remove.error && <ErrorMessage error={remove.error} />}
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setDeleting(null)}>
                Cancelar
              </Button>
              <Button
                color="red"
                onClick={confirmDelete}
                loading={remove.isPending}
              >
                Confirmar exclusão
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}

/** A list of editable rows ("vigências") with add/remove buttons. */
export function EntryList<T>({
  label,
  items,
  onChange,
  make,
  row,
  addLabel = "+ vigência",
}: {
  label: string;
  items: T[];
  onChange: (items: T[]) => void;
  make: () => T;
  row: (
    item: T,
    update: (patch: Partial<T>) => void,
    index: number,
  ) => ReactNode;
  addLabel?: string;
}) {
  return (
    <Stack gap={4} role="group" aria-label={label}>
      <Text size="sm" fw={500}>
        {label}
      </Text>
      {items.length === 0 && (
        <Text size="xs" c="dimmed">
          Nenhuma vigência.
        </Text>
      )}
      {items.map((item, i) => (
        <Group key={i} gap="xs" align="flex-end" wrap="nowrap">
          {row(
            item,
            (patch) =>
              onChange(
                items.map((it, j) => (j === i ? { ...it, ...patch } : it)),
              ),
            i,
          )}
          <Button
            variant="subtle"
            color="red"
            size="xs"
            aria-label={`Remover ${label} ${i + 1}`}
            onClick={() => onChange(items.filter((_, j) => j !== i))}
          >
            ✕
          </Button>
        </Group>
      ))}
      <Group>
        <Button
          variant="light"
          size="xs"
          onClick={() => onChange([...items, make()])}
        >
          {addLabel}
        </Button>
      </Group>
    </Stack>
  );
}

/** Native select over id/name rows with an optional "none" choice. */
export function IdSelect({
  label,
  value,
  onChange,
  options,
  none,
  required,
}: {
  label: string;
  value: string | null;
  onChange: (value: string | null) => void;
  options: { id: string; name: string }[];
  none?: string;
  required?: boolean;
}) {
  const labels = useOwnerLabels();
  const data = [
    ...(none !== undefined || value === null
      ? [{ value: "", label: none ?? "Escolha…" }]
      : []),
    // R14.3: cards/accounts with the same name get their distinguishing label.
    ...options.map((o) => ({ value: o.id, label: labels[o.id] ?? o.name })),
  ];
  return (
    <NativeSelect
      label={label}
      data={data}
      value={value ?? ""}
      required={required}
      onChange={(e) => onChange(e.currentTarget.value || null)}
    />
  );
}

/** Account types that accept each payment method (mirrors backend ACCOUNT_METHODS). */
export const ACCOUNT_TYPE_FOR: Record<string, string> = {
  benefit: "benefit",
  cash: "cash",
  debit: "checking",
  pix: "checking",
  transfer: "checking",
  boleto: "checking",
};

export const PAYMENT_METHODS: PaymentMethod[] = [
  "credit",
  "benefit",
  "debit",
  "pix",
  "transfer",
  "boleto",
  "cash",
];

export interface PaymentDraft {
  payment_method: PaymentMethod;
  card_id: string | null;
  account_id: string | null;
}

/** Payment method + the card (credit) or account (other methods) it goes through. */
export function PaymentTarget({
  value,
  onChange,
}: {
  value: PaymentDraft;
  onChange: (patch: Partial<PaymentDraft>) => void;
}) {
  const cards = useList("cards").data ?? [];
  const accounts = useList("accounts").data ?? [];
  const credit = value.payment_method === "credit";
  const accType = ACCOUNT_TYPE_FOR[value.payment_method];
  return (
    <Group grow align="flex-end">
      <NativeSelect
        label="Meio de pagamento"
        data={PAYMENT_METHODS.map((m) => ({
          value: m,
          label: METHOD_LABELS[m] ?? m,
        }))}
        value={value.payment_method}
        onChange={(e) =>
          onChange({
            payment_method: e.currentTarget.value as PaymentMethod,
            card_id: null,
            account_id: null,
          })
        }
      />
      {credit ? (
        <IdSelect
          label="Cartão"
          value={value.card_id}
          onChange={(v) => onChange({ card_id: v })}
          options={cards}
          required
        />
      ) : (
        <IdSelect
          label="Conta"
          value={value.account_id}
          onChange={(v) => onChange({ account_id: v })}
          options={accounts.filter((a) => a.type === accType)}
          required
        />
      )}
    </Group>
  );
}

/** Validation shared by subscriptions and recurring purchases. */
export function checkPayment(p: PaymentDraft): string | null {
  if (p.payment_method === "credit")
    return p.card_id ? null : "Escolha o cartão";
  return p.account_id ? null : "Escolha a conta";
}

export function paymentBody(p: PaymentDraft): PaymentDraft {
  return p.payment_method === "credit"
    ? { payment_method: p.payment_method, card_id: p.card_id, account_id: null }
    : {
        payment_method: p.payment_method,
        card_id: null,
        account_id: p.account_id,
      };
}

/** Human text for an allocation: "Casal", "Eu 100%", "Eu 60% · Ana 40%" or the fallback. */
export function describeAllocation(
  value: Allocation | null | undefined,
  names: { users: Record<string, string>; splits: Record<string, string> },
  fallback = "Padrão",
): string {
  if (!value) return fallback;
  if (isSplitRef(value)) return names.splits[value.split_id] ?? value.split_id;
  return value
    .map((s) => `${names.users[s.user_id] ?? s.user_id} ${formatPct(s.pct)}`)
    .join(" · ");
}

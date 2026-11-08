import {
  Alert,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconChecklist,
  IconFileInvoice,
  IconRosetteDiscountCheck,
} from "@tabler/icons-react";
import { useState } from "react";
import { useAction, useGet, useList, useNames } from "../../api/hooks";
import type {
  Allocation,
  Kind,
  ReviewFile,
  Suggestion,
  Transaction,
} from "../../api/types";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { CategorySelect } from "../../components/CategorySelect";
import { QueryState, errorText } from "../../components/QueryState";
import { formatMonth } from "../../hooks/month";
import {
  KIND_LABELS,
  formatDate,
  formatMoney,
  sumMoney,
} from "../../lib/format";
import { ApiError } from "../../api/client";
import { useDefaultSplit } from "../../components/defaultSplit";
import {
  allocationText,
  isChoice,
  originLabel,
  suggestionLabel,
  warningText,
} from "./labels";
import {
  MoneyText,
  PageHeader,
  StatusBadge,
  toneFromColor,
} from "../../components/ui";

export interface RuleSuggestion {
  description_regex: string;
  priority: number;
  category_id: string | null;
  allocations: Allocation | null;
}

interface LinePatch {
  id: string;
  category_id?: string | null;
  allocations?: Allocation | null;
  kind?: Kind;
  note?: string | null;
  choose?: { type: string; target_id: string };
  reject?: string;
  accept?: string;
}

const KIND_OPTIONS = Object.entries(KIND_LABELS).map(([value, label]) => ({
  value,
  label,
}));
/** R14.8: a card invoice line is spending (or an investment charged on the card, R9.4). */
const CARD_KINDS = new Set(["expense", "refund", "fee", "investment"]);
export const CARD_KIND_OPTIONS = KIND_OPTIONS.filter((o) =>
  CARD_KINDS.has(o.value),
);

type Resolver = (kind: "plan" | "manual" | "investment", id: string) => string;

function useResolver(): Resolver {
  const plans = useList("installment-plans");
  const investments = useList("investments");
  const manuals = useGet<Transaction[]>(
    ["transactions", "provisional=true"],
    "/api/transactions?provisional=true",
  );
  return (kind, id) => {
    if (kind === "plan")
      return plans.data?.find((p) => p.id === id)?.description ?? id;
    if (kind === "investment")
      return investments.data?.find((i) => i.id === id)?.name ?? id;
    const tx = manuals.data?.find((t) => t.id === id);
    return tx
      ? `${tx.description} ${formatDate(tx.purchase_date)} ${formatMoney(tx.amount)}`
      : id;
  };
}

const choiceKind = (type: string): "plan" | "manual" | "investment" =>
  type === "choose_plan"
    ? "plan"
    : type === "choose_investment"
      ? "investment"
      : "manual";

function confirmErrorText(error: unknown): string {
  if (error instanceof ApiError && error.code === "cannot_confirm")
    return `Não dá para confirmar: ${error.message}`;
  return errorText(error);
}

/** Review of imported lines before they become transactions (R5, R3.11, docs/09). */
export function ReviewPage() {
  const files = useGet<ReviewFile[]>(["review"], "/api/review");
  const [rule, setRule] = useState<RuleSuggestion | null>(null);
  const createRule = useAction<RuleSuggestion>(
    "post",
    () => "/api/rules",
    (r) => ({
      priority: r.priority,
      enabled: true,
      when: { description_regex: r.description_regex },
      then: { category_id: r.category_id, allocations: r.allocations },
    }),
  );
  const resolve = useResolver();
  const rows = files.data ?? [];

  return (
    <Stack gap="xl">
      <PageHeader
        title="Revisão"
        eyebrow="Movimento"
        icon={<IconChecklist size={22} stroke={1.7} />}
        subtitle="Linhas importadas esperando sua confirmação. Ajuste categoria e divisão e confirme o arquivo."
      />
      {rule && (
        <Alert
          color="blue"
          title="Criar regra?"
          withCloseButton
          onClose={() => setRule(null)}
        >
          <Text size="sm">
            Você fez a mesma edição para "
            {rule.description_regex.replace(/\\/g, "")}" em dois arquivos. Criar
            uma regra para aplicar automaticamente?
          </Text>
          <Group mt="xs">
            <Button
              size="xs"
              loading={createRule.isPending}
              onClick={() =>
                createRule.mutate(rule, {
                  onSuccess: () => {
                    notifications.show({
                      message: "Regra criada.",
                      color: "green",
                    });
                    setRule(null);
                  },
                  onError: (e) =>
                    notifications.show({ message: errorText(e), color: "red" }),
                })
              }
            >
              Criar regra
            </Button>
            <Button size="xs" variant="default" onClick={() => setRule(null)}>
              Agora não
            </Button>
          </Group>
        </Alert>
      )}
      <QueryState
        isLoading={files.isLoading}
        error={files.error}
        empty={rows.length === 0}
        emptyText="Nada para revisar."
        emptyIcon={<IconRosetteDiscountCheck size={26} stroke={1.6} />}
      >
        <Stack gap="lg" className="et-stagger">
          {rows.map((f) => (
            <ReviewFileCard
              key={f.file.path}
              item={f}
              resolve={resolve}
              onRuleSuggestion={setRule}
            />
          ))}
        </Stack>
      </QueryState>
    </Stack>
  );
}

function ReviewFileCard({
  item,
  resolve,
  onRuleSuggestion,
}: {
  item: ReviewFile;
  resolve: Resolver;
  onRuleSuggestion: (r: RuleSuggestion) => void;
}) {
  const { file, lines } = item;
  const names = useNames();
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [editingSplit, setEditingSplit] = useState<Transaction | null>(null);
  const confirm = useAction<
    { ids: string[] } | { path: string },
    { confirmed: number }
  >("post", () => "/api/review/confirm");
  const patch = useAction<
    LinePatch,
    { rule_suggestion: RuleSuggestion | null }
  >(
    "patch",
    ({ id }) => `/api/review/lines/${encodeURIComponent(id)}`,
    (input) => {
      const { id, ...body } = input;
      void id; // the id goes in the URL only
      return body;
    },
  );
  const supersede = useAction<{ path: string; decision: "approve" | "reject" }>(
    "post",
    ({ decision }) => `/api/sync/supersede/${decision}`,
    ({ path }) => ({ path }),
  );

  const edit = (body: LinePatch) =>
    patch.mutate(body, {
      onSuccess: (res) => {
        if (res?.rule_suggestion) onRuleSuggestion(res.rule_suggestion);
      },
      onError: (e) =>
        notifications.show({ message: errorText(e), color: "red" }),
    });
  const doConfirm = (body: { ids: string[] } | { path: string }) =>
    confirm.mutate(body, {
      onSuccess: (r) => {
        notifications.show({
          message: `${r?.confirmed ?? 0} linha(s) confirmada(s).`,
          color: "green",
        });
        setSelection(new Set());
      },
    });

  const selectable = lines.filter((l) => l.review?.status !== "overlap");
  const selectedIds = selectable
    .map((l) => l.id)
    .filter((id) => selection.has(id));
  const allSelected =
    selectable.length > 0 && selectedIds.length === selectable.length;
  const toggle = (id: string) =>
    setSelection((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const sum = sumMoney(
    lines.filter((l) => l.review?.status !== "overlap").map((l) => l.amount),
  );
  const mismatch = file.total !== null && Number(file.total) !== Number(sum);
  const owner = names.owner(file.card_id ?? file.account_id);
  const fileWarnings = file.warnings ?? [];

  return (
    <Card padding="lg" component="section" aria-label={`Arquivo ${file.path}`}>
      <Stack gap="sm">
        <Group justify="space-between" wrap="wrap">
          <Group gap="sm" wrap="nowrap" align="flex-start">
            <span className="et-icon-chip" aria-hidden="true">
              <IconFileInvoice size={18} stroke={1.7} />
            </span>
            <div>
              <Title order={3} size="h4">
                {file.path}
              </Title>
              <Text size="sm" c="dimmed">
                {file.kind === "fatura" ? "Fatura" : "Extrato"} ·{" "}
                {owner || "dono não definido"}
                {file.invoice_month && ` · ${formatMonth(file.invoice_month)}`}
                {file.open_invoice && " · fatura aberta"} · {item.label}
              </Text>
            </div>
          </Group>
          <Text size="sm" className="et-num">
            Total do PDF: <b>{formatMoney(file.total)}</b> · soma das linhas:{" "}
            <MoneyText
              value={sum}
              tone={mismatch ? "negative" : "neutral"}
              fw={700}
            />
            {file.amount_due && (
              <>
                {" "}
                · a pagar: <b>{formatMoney(file.amount_due)}</b>
              </>
            )}
          </Text>
        </Group>
        {fileWarnings.length > 0 && (
          <Alert color="yellow" variant="light" title="Avisos">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {fileWarnings.map((w) => (
                <li key={w}>{warningText(w, (k, id) => resolve(k, id))}</li>
              ))}
            </ul>
          </Alert>
        )}
        {file.supersedes_candidate && (
          <Alert color="orange" title="Nova versão de fatura">
            <Text size="sm">
              Substituir a fatura {file.supersedes_candidate} por esta?
            </Text>
            <Group mt="xs">
              <Button
                size="xs"
                loading={supersede.isPending}
                onClick={() =>
                  supersede.mutate(
                    { path: file.path, decision: "approve" },
                    {
                      onError: (e) =>
                        notifications.show({
                          message: errorText(e),
                          color: "red",
                        }),
                    },
                  )
                }
              >
                Aprovar substituição
              </Button>
              <Button
                size="xs"
                variant="default"
                onClick={() =>
                  supersede.mutate(
                    { path: file.path, decision: "reject" },
                    {
                      onError: (e) =>
                        notifications.show({
                          message: errorText(e),
                          color: "red",
                        }),
                    },
                  )
                }
              >
                Recusar
              </Button>
            </Group>
          </Alert>
        )}
        {confirm.error && (
          <Alert color="red" role="alert">
            {confirmErrorText(confirm.error)}
          </Alert>
        )}
        <Table.ScrollContainer minWidth={1100}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>
                  <Checkbox
                    aria-label={`Selecionar todas de ${file.path}`}
                    checked={allSelected}
                    indeterminate={selectedIds.length > 0 && !allSelected}
                    onChange={() =>
                      setSelection(
                        allSelected
                          ? new Set()
                          : new Set(selectable.map((l) => l.id)),
                      )
                    }
                  />
                </Table.Th>
                <Table.Th>Data</Table.Th>
                <Table.Th>Descrição</Table.Th>
                <Table.Th ta="right">Valor</Table.Th>
                <Table.Th>Tipo</Table.Th>
                <Table.Th>Categoria</Table.Th>
                <Table.Th>Divisão</Table.Th>
                <Table.Th>Sugestões</Table.Th>
                <Table.Th>Nota</Table.Th>
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {lines.map((line) => (
                <ReviewLineRow
                  key={line.id}
                  line={line}
                  selected={selection.has(line.id)}
                  onToggle={() => toggle(line.id)}
                  onEdit={edit}
                  onEditSplit={() => setEditingSplit(line)}
                  onConfirm={() => doConfirm({ ids: [line.id] })}
                  resolve={resolve}
                  users={names.users}
                  splits={names.splits}
                />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group justify="flex-end">
          <Button
            variant="light"
            disabled={selectedIds.length === 0}
            loading={confirm.isPending}
            onClick={() => doConfirm({ ids: selectedIds })}
          >
            Confirmar selecionadas ({selectedIds.length})
          </Button>
          <Button
            loading={confirm.isPending}
            onClick={() => doConfirm({ path: file.path })}
          >
            Confirmar arquivo
          </Button>
        </Group>
      </Stack>
      <Modal
        opened={editingSplit !== null}
        onClose={() => setEditingSplit(null)}
        title={`Divisão — ${editingSplit?.description ?? ""}`}
      >
        {editingSplit && (
          <SplitEditor
            initial={editingSplit.allocations}
            cardId={editingSplit.card_id}
            accountId={editingSplit.account_id}
            onApply={(allocations) => {
              edit({ id: editingSplit.id, allocations });
              setEditingSplit(null);
            }}
          />
        )}
      </Modal>
    </Card>
  );
}

function SplitEditor({
  initial,
  onApply,
  cardId,
  accountId,
}: {
  initial: Allocation | null;
  onApply: (a: Allocation | null) => void;
  cardId: string | null;
  accountId: string | null;
}) {
  const [value, setValue] = useState<Allocation | null>(initial);
  const defaultHint = useDefaultSplit(cardId, accountId);
  const valid = allocationValid(value);
  return (
    <Stack>
      <AllocationPicker
        value={value}
        onChange={setValue}
        defaultHint={defaultHint}
      />
      <Group justify="flex-end">
        <Button disabled={!valid} onClick={() => onApply(value)}>
          Aplicar
        </Button>
      </Group>
    </Stack>
  );
}

function ReviewLineRow({
  line,
  selected,
  onToggle,
  onEdit,
  onEditSplit,
  onConfirm,
  resolve,
  users,
  splits,
}: {
  line: Transaction;
  selected: boolean;
  onToggle: () => void;
  onEdit: (p: LinePatch) => void;
  onEditSplit: () => void;
  onConfirm: () => void;
  resolve: Resolver;
  users: Record<string, string>;
  splits: Record<string, string>;
}) {
  const status = line.review?.status ?? "pending";
  const overlap = status === "overlap";
  const warnings = line.review?.warnings ?? [];
  const missingCategory = warnings.includes("category_missing");
  const [note, setNote] = useState(line.note ?? "");
  const bg =
    status === "needs_choice"
      ? "var(--mantine-color-yellow-light)"
      : missingCategory
        ? "var(--mantine-color-red-light)"
        : undefined;
  const d = line.description;

  return (
    <Table.Tr
      style={{ opacity: overlap ? 0.5 : 1, background: bg }}
      aria-disabled={overlap || undefined}
      data-status={status}
    >
      <Table.Td>
        <Checkbox
          aria-label={`Selecionar ${d}`}
          checked={selected && !overlap}
          disabled={overlap}
          onChange={onToggle}
        />
      </Table.Td>
      <Table.Td>{formatDate(line.purchase_date)}</Table.Td>
      <Table.Td>
        {d}
        {line.installment && (
          <Text span size="xs" c="dimmed">
            {" "}
            ({line.installment.n}/{line.installment.of})
          </Text>
        )}
        <Group gap={4} mt={2}>
          {overlap && (
            <StatusBadge size="xs" tone="neutral">
              já coberta por outro documento
            </StatusBadge>
          )}
          {status === "needs_choice" && (
            <StatusBadge size="xs" tone="warning">
              precisa escolher
            </StatusBadge>
          )}
          {warnings.map((w) => (
            <StatusBadge
              key={w}
              size="xs"
              tone={toneFromColor(w === "category_missing" ? "red" : "orange")}
            >
              {warningText(w, (k, id) => resolve(k, id))}
            </StatusBadge>
          ))}
        </Group>
      </Table.Td>
      <Table.Td ta="right">{formatMoney(line.amount)}</Table.Td>
      <Table.Td>
        <Select
          aria-label={`Tipo de ${d}`}
          data={line.card_id ? CARD_KIND_OPTIONS : KIND_OPTIONS}
          value={line.kind}
          disabled={overlap}
          allowDeselect={false}
          onChange={(v) =>
            v && v !== line.kind && onEdit({ id: line.id, kind: v as Kind })
          }
          w={140}
        />
      </Table.Td>
      <Table.Td>
        <CategorySelect
          label={null}
          aria-label={`Categoria de ${d}`}
          required={false}
          value={line.category_id}
          disabled={overlap}
          error={missingCategory}
          onChange={(v) =>
            v !== line.category_id && onEdit({ id: line.id, category_id: v })
          }
          w={170}
        />
      </Table.Td>
      <Table.Td>
        <Button
          size="xs"
          variant="subtle"
          disabled={overlap}
          onClick={onEditSplit}
          aria-label={`Divisão de ${d}: ${allocationText(line.allocations, users, splits)}`}
        >
          {allocationText(line.allocations, users, splits)}
        </Button>
        <Text size="xs" c="dimmed">
          origem: {originLabel(line.allocation_origin)}
        </Text>
      </Table.Td>
      <Table.Td>
        <Stack gap={4}>
          {(line.review?.suggestions ?? []).map((s) => (
            <SuggestionControl
              key={s.type}
              s={s}
              line={line}
              disabled={overlap}
              onEdit={onEdit}
              resolve={resolve}
            />
          ))}
        </Stack>
      </Table.Td>
      <Table.Td>
        <TextInput
          aria-label={`Nota de ${d}`}
          value={note}
          disabled={overlap}
          onChange={(e) => setNote(e.currentTarget.value)}
          onBlur={() => {
            const next = note.trim() || null;
            if (next !== (line.note ?? null))
              onEdit({ id: line.id, note: next });
          }}
          w={140}
        />
      </Table.Td>
      <Table.Td className="et-sticky-end">
        <Button
          size="xs"
          disabled={overlap}
          onClick={onConfirm}
          aria-label={`Confirmar ${d}`}
        >
          Confirmar
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}

function SuggestionControl({
  s,
  line,
  disabled,
  onEdit,
  resolve,
}: {
  s: Suggestion;
  line: Transaction;
  disabled: boolean;
  onEdit: (p: LinePatch) => void;
  resolve: Resolver;
}) {
  const label = suggestionLabel(s.type);
  const choice = isChoice(s.type) && s.candidates.length > 0;
  return (
    <Group gap={4} wrap="nowrap">
      <StatusBadge
        tone={toneFromColor(s.rejected ? "gray" : "teal")}
        style={s.rejected ? { textDecoration: "line-through" } : undefined}
      >
        {label}
      </StatusBadge>
      {choice && !s.rejected && (
        <Select
          aria-label={`${label} para ${line.description}`}
          placeholder="escolha…"
          size="xs"
          disabled={disabled}
          data={s.candidates.map((id) => ({
            value: id,
            label: resolve(choiceKind(s.type), id),
          }))}
          value={s.target_id}
          onChange={(v) =>
            v && onEdit({ id: line.id, choose: { type: s.type, target_id: v } })
          }
          w={180}
        />
      )}
      {s.rejected ? (
        <Button
          size="compact-xs"
          variant="subtle"
          disabled={disabled}
          onClick={() => onEdit({ id: line.id, accept: s.type })}
          aria-label={`Aceitar ${label} em ${line.description}`}
        >
          Aceitar
        </Button>
      ) : (
        <Button
          size="compact-xs"
          variant="subtle"
          color="red"
          disabled={disabled}
          onClick={() => onEdit({ id: line.id, reject: s.type })}
          aria-label={`Rejeitar ${label} em ${line.description}`}
        >
          Rejeitar
        </Button>
      )}
    </Group>
  );
}

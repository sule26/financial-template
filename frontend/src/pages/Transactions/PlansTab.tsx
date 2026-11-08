import {
  Alert,
  Button,
  Group,
  Menu,
  Modal,
  NumberInput,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { MonthField } from "../../components/ui/MonthField";
import { notifications } from "@mantine/notifications";
import { useState, type FormEvent } from "react";
import { useAction, useGet, useList, useNames, useSave } from "../../api/hooks";
import type { Allocation, InstallmentPlan } from "../../api/types";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { CategorySelect } from "../../components/CategorySelect";
import { useDefaultSplit } from "../../components/defaultSplit";
import { IdSelect } from "../Catalog/shared";
import { QueryState, errorText } from "../../components/QueryState";
import { formatMonth } from "../../hooks/month";
import { formatMoney, parseMoneyInput } from "../../lib/format";
import { StatusBadge, toneFromColor } from "../../components/ui";

const STATUS_COLORS: Record<string, string> = {
  pago: "green",
  terminando: "yellow",
  "em andamento": "blue",
  cancelado: "gray",
};

type PlanAction = "anticipate" | "cancel" | "bank";

/** GET /api/installment-plans-progress (R14.19). */
interface Progress {
  status: string;
  remaining: number;
  remaining_amount: string;
  next_n: number | null;
  next_month: string | null;
  next_amount: string | null;
  /** R14.21: the monthly installment value. */
  installment_amount: string;
}
const FINISHED = new Set(["pago", "cancelado"]);

const ACTION_TITLES: Record<PlanAction, string> = {
  anticipate: "Antecipar parcelamento",
  cancel: "Cancelar parcelamento",
  bank: "Antecipada no banco",
};

function notifyError(e: unknown) {
  notifications.show({ title: "Erro", message: errorText(e), color: "red" });
}

export function PlansTab() {
  const plans = useList("installment-plans");
  const statuses = useGet<Record<string, string>>(
    ["installment-plans-status"],
    "/api/installment-plans-status",
  );
  const progress = useGet<Record<string, Progress>>(
    ["installment-plans-progress"],
    "/api/installment-plans-progress",
  );
  const [showFinished, setShowFinished] = useState(false);
  const [editing, setEditing] = useState<InstallmentPlan | null>(null);
  const names = useNames();
  const [action, setAction] = useState<{
    plan: InstallmentPlan;
    kind: PlanAction;
  } | null>(null);
  const undo = useAction<string>(
    "del",
    (id) => `/api/installment-plans/${encodeURIComponent(id)}/anticipation`,
  );
  const all = plans.data ?? [];
  const statusOf = (p: InstallmentPlan) =>
    progress.data?.[p.id]?.status ?? statuses.data?.[p.id];
  // R14.19: finished (paid or cancelled) plans leave the list unless asked for.
  const rows = all.filter(
    (p) => showFinished || !FINISHED.has(statusOf(p) ?? ""),
  );
  const hidden = all.length - rows.length;

  return (
    <>
      <Group justify="space-between" mb="sm">
        <Text size="sm" c="dimmed">
          {hidden > 0 && !showFinished
            ? `${hidden} parcelamento(s) terminado(s) escondido(s).`
            : " "}
        </Text>
        <Switch
          label="Mostrar terminados"
          checked={showFinished}
          onChange={(e) => setShowFinished(e.currentTarget.checked)}
        />
      </Group>
      <QueryState
        isLoading={plans.isLoading}
        error={plans.error}
        empty={rows.length === 0}
        emptyText={
          hidden > 0
            ? "Nenhum parcelamento em andamento."
            : "Nenhum parcelamento."
        }
      >
        <Table.ScrollContainer minWidth={900} className="et-table-card">
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Descrição</Table.Th>
                <Table.Th>Cartão</Table.Th>
                <Table.Th>Parcelas</Table.Th>
                <Table.Th ta="right">Total</Table.Th>
                <Table.Th>1ª fatura</Table.Th>
                <Table.Th>Falta</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Antecipação</Table.Th>
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((plan) => {
                const status = statusOf(plan);
                const prog = progress.data?.[plan.id];
                const ant = plan.anticipation;
                const locked = !!ant && ant.linked_fingerprints.length > 0;
                return (
                  <Table.Tr key={plan.id}>
                    <Table.Td>
                      {plan.description}
                      {plan.warnings.map((w) => (
                        <StatusBadge key={w} tone="warning" ml={4}>
                          {w}
                        </StatusBadge>
                      ))}
                    </Table.Td>
                    <Table.Td>{names.owner(plan.card_id)}</Table.Td>
                    <Table.Td>
                      {plan.total_installments}x de{" "}
                      <b>
                        {formatMoney(
                          prog?.installment_amount ?? plan.installment_amount,
                        )}
                      </b>
                      <Text size="xs" c="dimmed">
                        por mês
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">
                      {formatMoney(plan.total_amount)}
                    </Table.Td>
                    <Table.Td>{formatMonth(plan.first_invoice_month)}</Table.Td>
                    <Table.Td>
                      {prog && prog.remaining > 0 ? (
                        <>
                          <Text size="sm">
                            {prog.remaining}x ·{" "}
                            {formatMoney(prog.remaining_amount)}
                          </Text>
                          {prog.next_n && prog.next_month && (
                            <Text size="xs" c="dimmed">
                              próxima: {prog.next_n}/{plan.total_installments}{" "}
                              em {formatMonth(prog.next_month)}
                              {prog.next_amount &&
                                ` (${formatMoney(prog.next_amount)})`}
                            </Text>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </Table.Td>
                    <Table.Td>
                      {status && (
                        <StatusBadge
                          tone={toneFromColor(STATUS_COLORS[status] ?? "gray")}
                        >
                          {status}
                        </StatusBadge>
                      )}
                      {plan.status_override?.status ===
                        "anticipated_at_bank" && (
                        <Text size="xs" c="dimmed">
                          antecipada no banco a partir da{" "}
                          {plan.status_override.from_n}ª
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {ant ? (
                        <Text size="sm">
                          {ant.from_n}ª em diante →{" "}
                          {formatMonth(ant.target_month)}
                          {ant.amount && ` (${formatMoney(ant.amount)})`}
                        </Text>
                      ) : (
                        "—"
                      )}
                    </Table.Td>
                    <Table.Td className="et-sticky-end">
                      <Group gap={4} wrap="nowrap">
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() => setEditing(plan)}
                          aria-label={`Editar ${plan.description}`}
                        >
                          Editar
                        </Button>
                        {ant ? (
                          <Button
                            size="xs"
                            variant="light"
                            disabled={locked}
                            title={
                              locked
                                ? "Já casada com linhas importadas"
                                : undefined
                            }
                            onClick={() =>
                              undo.mutate(plan.id, { onError: notifyError })
                            }
                            aria-label={`Desfazer antecipação de ${plan.description}`}
                          >
                            Desfazer antecipação
                          </Button>
                        ) : (
                          <Button
                            size="xs"
                            variant="light"
                            onClick={() =>
                              setAction({ plan, kind: "anticipate" })
                            }
                            aria-label={`Antecipar ${plan.description}`}
                          >
                            Antecipar
                          </Button>
                        )}
                        {/* R14.6: rarer actions in a menu so the row fits and Status stays visible */}
                        <Menu position="bottom-end" withinPortal>
                          <Menu.Target>
                            <Button
                              size="xs"
                              variant="subtle"
                              aria-label={`Mais ações de ${plan.description}`}
                            >
                              Mais…
                            </Button>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item
                              onClick={() => setAction({ plan, kind: "bank" })}
                              aria-label={`Antecipada no banco: ${plan.description}`}
                            >
                              Antecipada no banco
                            </Menu.Item>
                            <Menu.Item
                              color="red"
                              onClick={() =>
                                setAction({ plan, kind: "cancel" })
                              }
                              aria-label={`Cancelar ${plan.description}`}
                            >
                              Cancelar
                            </Menu.Item>
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </QueryState>
      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title="Editar parcelamento"
      >
        {editing && (
          <PlanEditForm plan={editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
      <Modal
        opened={action !== null}
        onClose={() => setAction(null)}
        title={action ? ACTION_TITLES[action.kind] : ""}
      >
        {action && (
          <PlanActionForm
            plan={action.plan}
            kind={action.kind}
            onDone={() => setAction(null)}
          />
        )}
      </Modal>
    </>
  );
}

/** Anticipate (R7.1) / cancel from n / anticipated at the bank (docs/09 row 7). */
export function PlanActionForm({
  plan,
  kind,
  onDone,
}: {
  plan: InstallmentPlan;
  kind: PlanAction;
  onDone: () => void;
}) {
  const [fromN, setFromN] = useState("");
  const [month, setMonth] = useState("");
  const [amountText, setAmountText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const suffix =
    kind === "anticipate"
      ? "anticipate"
      : kind === "cancel"
        ? "cancel"
        : "anticipated-at-bank";
  const run = useAction<Record<string, unknown>, InstallmentPlan>(
    "post",
    () => `/api/installment-plans/${encodeURIComponent(plan.id)}/${suffix}`,
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const n = fromN.trim() ? Number(fromN) : null;
    if (
      n !== null &&
      (!Number.isInteger(n) || n < 1 || n > plan.total_installments)
    )
      return setError(`Parcela entre 1 e ${plan.total_installments}`);
    const body: Record<string, unknown> = {};
    if (kind === "anticipate") {
      if (n !== null) body.from_n = n;
      if (month) body.target_month = month;
      if (amountText.trim()) {
        const amount = parseMoneyInput(amountText);
        if (!amount) return setError("Valor inválido");
        body.amount = amount;
      }
    } else {
      if (n === null) return setError("Informe a parcela");
      body.from_n = n;
    }
    setError(null);
    run.mutate(body, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="sm">
        <Text size="sm">
          {plan.description} — {plan.total_installments}x
        </Text>
        <TextInput
          label={
            kind === "anticipate"
              ? "Parcela inicial (opcional)"
              : "A partir da parcela"
          }
          inputMode="numeric"
          value={fromN}
          onChange={(e) => setFromN(e.currentTarget.value)}
          description={
            kind === "anticipate"
              ? "Vazio = a primeira parcela ainda não faturada"
              : undefined
          }
        />
        {kind === "anticipate" && (
          <>
            <MonthField
              label="Mês alvo (opcional)"
              value={month}
              onChange={setMonth}
              description="Vazio = a próxima fatura ainda não importada"
            />
            <TextInput
              label="Valor cobrado (opcional)"
              inputMode="decimal"
              value={amountText}
              onChange={(e) => setAmountText(e.currentTarget.value)}
              description="Com desconto, se o banco deu"
            />
          </>
        )}
        {(error || run.error) && (
          <Alert color="red" role="alert">
            {error ?? errorText(run.error)}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Voltar
          </Button>
          <Button type="submit" loading={run.isPending}>
            Confirmar
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

/**
 * R14.20: edit a plan after it was created. Description, category and split always; the
 * schedule (card, amount, installments, first invoice) only for plans entered by hand, since an
 * imported plan follows the invoice.
 */
export function PlanEditForm({
  plan,
  onDone,
}: {
  plan: InstallmentPlan;
  onDone: () => void;
}) {
  const cards = (useList("cards").data ?? []).filter(
    (c) => c.parent_card_id === null || c.id === plan.card_id,
  );
  const save = useSave("installment-plans");
  const manual = plan.origin.type === "manual";
  const [description, setDescription] = useState(plan.description);
  const [cardId, setCardId] = useState<string | null>(plan.card_id);
  const [total, setTotal] = useState(plan.total_amount.replace(".", ","));
  const [count, setCount] = useState<number>(plan.total_installments);
  const [first, setFirst] = useState(plan.first_invoice_month);
  const [categoryId, setCategoryId] = useState<string | null>(plan.category_id);
  const [allocations, setAllocations] = useState<Allocation | null>(
    plan.allocations,
  );
  const [error, setError] = useState<string | null>(null);
  const defaultHint = useDefaultSplit(cardId, null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!description.trim()) return setError("Descrição: obrigatória");
    const amount = parseMoneyInput(total);
    if (manual) {
      if (!amount || Number(amount) <= 0)
        return setError("Valor total inválido");
      if (!Number.isInteger(count) || count < 1 || count > 120)
        return setError("Parcelas: entre 1 e 120");
      if (!first) return setError("1ª fatura: escolha o mês");
      if (!cardId) return setError("Cartão: obrigatório");
    }
    if (!allocationValid(allocations))
      return setError("Divisão inválida: os percentuais precisam somar 100%");
    setError(null);
    const body: InstallmentPlan = {
      ...plan,
      description: description.trim(),
      category_id: categoryId,
      allocations,
      ...(manual
        ? {
            card_id: cardId ?? plan.card_id,
            total_amount: amount ?? plan.total_amount,
            total_installments: count,
            first_invoice_month: first,
            // the per-installment amount follows the new total (rest on the 1st, R1.2)
            installment_amount: null,
          }
        : {}),
    };
    save.mutate(body, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="sm">
        <TextInput
          label="Descrição"
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />
        {manual ? (
          <>
            <IdSelect
              label="Cartão"
              value={cardId}
              onChange={setCardId}
              options={cards}
              required
            />
            <Group grow>
              <TextInput
                label="Valor total"
                inputMode="decimal"
                value={total}
                onChange={(e) => setTotal(e.currentTarget.value)}
              />
              <NumberInput
                label="Parcelas"
                min={1}
                max={120}
                allowDecimal={false}
                value={count}
                onChange={(v) => setCount(Math.trunc(Number(v || 0)))}
              />
            </Group>
            <MonthField
              label="1ª fatura"
              clearable={false}
              value={first}
              onChange={setFirst}
            />
          </>
        ) : (
          <Text size="xs" c="dimmed">
            Parcelamento vindo da fatura: valores e meses seguem o que o banco
            cobra. Aqui você muda descrição, categoria e divisão.
          </Text>
        )}
        <CategorySelect value={categoryId} onChange={setCategoryId} />
        <AllocationPicker
          value={allocations}
          onChange={setAllocations}
          defaultHint={defaultHint}
        />
        {(error || save.error) && (
          <Alert color="red" role="alert">
            {error ?? errorText(save.error)}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Voltar
          </Button>
          <Button type="submit" loading={save.isPending}>
            Salvar
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

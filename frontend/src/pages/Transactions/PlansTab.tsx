import {
  Alert,
  Button,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { MonthField } from "../../components/ui/MonthField";
import { notifications } from "@mantine/notifications";
import { useState, type FormEvent } from "react";
import { useAction, useGet, useList, useNames } from "../../api/hooks";
import type { InstallmentPlan } from "../../api/types";
import { QueryState, errorText } from "../../components/QueryState";
import { formatMonth } from "../../hooks/month";
import { formatMoney, parseMoneyInput } from "../../lib/format";
import { StatusBadge, toneFromColor } from "../../components/ui";

const STATUS_COLORS: Record<string, string> = {
  pago: "green",
  "quase acabando": "yellow",
  "em andamento": "blue",
  cancelado: "gray",
};

type PlanAction = "anticipate" | "cancel" | "bank";

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
  const names = useNames();
  const [action, setAction] = useState<{
    plan: InstallmentPlan;
    kind: PlanAction;
  } | null>(null);
  const undo = useAction<string>(
    "del",
    (id) => `/api/installment-plans/${encodeURIComponent(id)}/anticipation`,
  );
  const rows = plans.data ?? [];

  return (
    <>
      <QueryState
        isLoading={plans.isLoading}
        error={plans.error}
        empty={rows.length === 0}
        emptyText="Nenhum parcelamento."
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
                <Table.Th>Status</Table.Th>
                <Table.Th>Antecipação</Table.Th>
                <Table.Th className="et-sticky-end">Ações</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((plan) => {
                const status = statuses.data?.[plan.id];
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
                      {plan.total_installments}x{" "}
                      {plan.installment_amount &&
                        formatMoney(plan.installment_amount)}
                    </Table.Td>
                    <Table.Td ta="right">
                      {formatMoney(plan.total_amount)}
                    </Table.Td>
                    <Table.Td>{formatMonth(plan.first_invoice_month)}</Table.Td>
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
                        <Button
                          size="xs"
                          variant="subtle"
                          onClick={() => setAction({ plan, kind: "bank" })}
                          aria-label={`Antecipada no banco: ${plan.description}`}
                        >
                          Antecipada no banco
                        </Button>
                        <Button
                          size="xs"
                          variant="subtle"
                          color="red"
                          onClick={() => setAction({ plan, kind: "cancel" })}
                          aria-label={`Cancelar ${plan.description}`}
                        >
                          Cancelar
                        </Button>
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

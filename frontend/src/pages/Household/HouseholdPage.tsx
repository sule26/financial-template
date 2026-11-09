/**
 * Contas da casa (R14.26): luz, água, aluguel, condomínio, internet… — the subscriptions marked
 * as "conta da casa", per month: due date, expected, paid and status, with "Registrar pagamento".
 */
import {
  Alert,
  Anchor,
  Button,
  Group,
  Modal,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { IconHome } from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAction, useGet, useNames } from "../../api/hooks";
import type { Allocation, PaymentMethod } from "../../api/types";
import { BenefitPicker, useBenefitNames } from "../../components/BenefitPicker";
import { errorText, QueryState } from "../../components/QueryState";
import { DateField } from "../../components/ui/DateField";
import { MoneyText, PageHeader, Panel, StatusBadge } from "../../components/ui";
import { formatMonth, useMonth } from "../../hooks/month";
import {
  formatDate,
  formatMoney,
  METHOD_LABELS,
  parseMoneyInput,
} from "../../lib/format";

export interface HouseholdBill {
  /** "recurring" = gasto recorrente marcado como conta da casa; "subscription" = first version. */
  source: "recurring" | "subscription";
  id: string;
  description: string;
  category_id: string | null;
  payment_method: PaymentMethod;
  card_id: string | null;
  account_id: string | null;
  benefit_id?: string | null; // R14.32
  allocations: Allocation | null;
  due_date: string | null;
  expected: string;
  paid: string;
  status: "paga" | "pendente" | "atrasada" | "desativada";
  transaction_ids: string[];
}
interface HouseholdReport {
  month: string;
  items: HouseholdBill[];
  totals: { expected: string; paid: string };
}

const STATUS_TONES = {
  paga: "success",
  pendente: "neutral",
  atrasada: "danger",
  desativada: "neutral",
} as const;

export function HouseholdPage() {
  const { selected } = useMonth();
  const names = useNames();
  const benefitNames = useBenefitNames();
  const path = `/api/reports/household?month=${encodeURIComponent(selected)}`;
  const report = useGet<HouseholdReport>(["reports", "household", path], path);
  const [paying, setPaying] = useState<HouseholdBill | null>(null);
  const items = report.data?.items ?? [];
  return (
    <Stack gap="lg">
      <PageHeader
        title="Contas da casa"
        eyebrow="Movimento"
        icon={<IconHome size={22} stroke={1.7} />}
        subtitle={`Luz, água, aluguel, condomínio, internet… de ${formatMonth(selected)}: quanto se espera, o que já foi pago e o que está atrasado.`}
      />
      <Panel
        title="Este mês"
        interactive={false}
        description={
          <>
            Uma conta da casa é um gasto recorrente marcado como “Conta da casa”
            em{" "}
            <Anchor component={Link} to="/cadastros?tab=recorrentes">
              Cadastros → Gastos recorrentes
            </Anchor>{" "}
            (a data de cada ocorrência é o vencimento; reajustes e períodos
            desativada também ficam lá). Ao registrar o pagamento, o valor
            previsto do mês é trocado pelo valor pago.
          </>
        }
      >
        <QueryState
          isLoading={report.isLoading}
          error={report.error}
          empty={items.length === 0}
          emptyText="Nenhuma conta da casa neste mês. Cadastre em Cadastros → Gastos recorrentes, tipo “Conta da casa”."
          emptyIcon={<IconHome size={26} stroke={1.6} />}
        >
          <Stack gap="md">
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              <div>
                <Text size="xs" c="dimmed">
                  Previsto no mês
                </Text>
                <MoneyText
                  value={report.data?.totals.expected}
                  fw={700}
                  size="lg"
                />
              </div>
              <div>
                <Text size="xs" c="dimmed">
                  Já pago
                </Text>
                <MoneyText
                  value={report.data?.totals.paid}
                  tone="positive"
                  fw={700}
                  size="lg"
                />
              </div>
            </SimpleGrid>
            <Table.ScrollContainer minWidth={760}>
              <Table aria-label="Contas da casa">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Conta</Table.Th>
                    <Table.Th>Vencimento</Table.Th>
                    <Table.Th>Pagamento</Table.Th>
                    <Table.Th ta="right">Previsto</Table.Th>
                    <Table.Th ta="right">Pago</Table.Th>
                    <Table.Th>Situação</Table.Th>
                    <Table.Th className="et-sticky-end">Ações</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {items.map((b) => (
                    <Table.Tr
                      key={`${b.source}-${b.id}`}
                      data-status={b.status}
                    >
                      <Table.Td>
                        <Text size="sm" fw={600}>
                          {b.description}
                        </Text>
                        {b.category_id && (
                          <Text size="xs" c="dimmed">
                            {names.categories[b.category_id] ?? b.category_id}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>{formatDate(b.due_date)}</Table.Td>
                      <Table.Td>
                        {METHOD_LABELS[b.payment_method] ?? b.payment_method} ·{" "}
                        {names.owner(b.card_id ?? b.account_id)}
                        {b.benefit_id &&
                          ` · ${benefitNames[b.benefit_id] ?? b.benefit_id}`}
                      </Table.Td>
                      <Table.Td ta="right">{formatMoney(b.expected)}</Table.Td>
                      <Table.Td ta="right">
                        {Number(b.paid) > 0 ? formatMoney(b.paid) : "—"}
                      </Table.Td>
                      <Table.Td>
                        <StatusBadge tone={STATUS_TONES[b.status]}>
                          {b.status}
                        </StatusBadge>
                      </Table.Td>
                      <Table.Td className="et-sticky-end">
                        {b.status !== "paga" && b.status !== "desativada" && (
                          <Button
                            size="xs"
                            variant="light"
                            onClick={() => setPaying(b)}
                            aria-label={`Registrar pagamento de ${b.description}`}
                          >
                            Registrar pagamento
                          </Button>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Stack>
        </QueryState>
      </Panel>
      <Modal
        opened={paying !== null}
        onClose={() => setPaying(null)}
        title="Registrar pagamento"
      >
        {paying && (
          <PayBillForm
            bill={paying}
            month={selected}
            onDone={() => setPaying(null)}
          />
        )}
      </Modal>
    </Stack>
  );
}

/** Creates the month's payment as a manual entry linked to the bill (R14.26). */
export function PayBillForm({
  bill,
  month,
  onDone,
}: {
  bill: HouseholdBill;
  month: string;
  onDone: () => void;
}) {
  const [amount, setAmount] = useState(bill.expected.replace(".", ","));
  const [date, setDate] = useState(bill.due_date ?? `${month}-01`);
  // R14.32: which benefit of the card pays it (starts on the bill's)
  const [benefitId, setBenefitId] = useState<string | null>(
    bill.benefit_id ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const save = useAction<Record<string, unknown>>(
    "post",
    () => "/api/transactions",
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = parseMoneyInput(amount);
    if (!value || Number(value) <= 0) return setError("Valor inválido");
    if (!date) return setError("Escolha a data do pagamento");
    setError(null);
    const body: Record<string, unknown> = {
      purchase_date: date,
      amount: value,
      description: bill.description,
      category_id: bill.category_id,
      payment_method: bill.payment_method,
      // the bill and the bill month this pays (a card payment may land on next month's invoice)
      ...(bill.source === "recurring"
        ? { recurring_purchase_id: bill.id, recurring_month: month }
        : { subscription_id: bill.id, subscription_month: month }),
    };
    if (bill.card_id) body.card_id = bill.card_id;
    else body.account_id = bill.account_id;
    if (bill.allocations) body.allocations = bill.allocations;
    if (bill.payment_method === "benefit" && benefitId)
      body.benefit_id = benefitId;
    save.mutate(body, { onSuccess: onDone });
  };
  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="sm">
        <Text size="sm">
          {bill.description} · previsto {formatMoney(bill.expected)}
        </Text>
        <TextInput
          label="Valor pago"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.currentTarget.value)}
        />
        <DateField label="Data do pagamento" value={date} onChange={setDate} />
        {bill.payment_method === "benefit" && (
          <BenefitPicker
            accountId={bill.account_id}
            value={benefitId}
            onChange={setBenefitId}
          />
        )}
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
            Registrar
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

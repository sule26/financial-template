import {
  Autocomplete,
  Button,
  Group,
  Kbd,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { T } from "../i18n/i18n";
import { todayIso } from "../lib/dates";
import { DateField } from "./ui/DateField";
import { useDebouncedValue, useDisclosure, useHotkeys } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconBolt, IconPlus } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "../api/client";
import { useAction, useList, useOwnerLabels } from "../api/hooks";
import type {
  AccountType,
  Allocation,
  InstallmentPlan,
  PaymentMethod,
  Transaction,
} from "../api/types";
import { METHOD_LABELS, parseMoneyInput } from "../lib/format";
import { useDefaultSplit } from "./defaultSplit";
import { AllocationPicker, allocationValid } from "./AllocationPicker";
import { BenefitPicker } from "./BenefitPicker";
import { CategorySelect } from "./CategorySelect";
import { errorText } from "./QueryState";
import { formatMonth, useMonth } from "../hooks/month";

export const METHOD_STORAGE_KEY = "expense-tracker.quick-entry.method";
export const ownerStorageKey = (method: PaymentMethod) =>
  `expense-tracker.quick-entry.owner.${method}`;

const METHODS: PaymentMethod[] = [
  "credit",
  "benefit",
  "debit",
  "pix",
  "transfer",
  "boleto",
  "cash",
];

/** Account type allowed for each non-credit payment method (mirrors the backend check). */
export const ACCOUNT_TYPE_FOR: Record<PaymentMethod, AccountType | null> = {
  credit: null,
  debit: "checking",
  pix: "checking",
  transfer: "checking",
  boleto: "checking",
  benefit: "benefit",
  cash: "cash",
};

export interface Suggest {
  category_id: string | null;
  category_origin: string | null;
  allocations: Allocation | null;
  allocation_origin: string | null;
  descriptions: string[];
}

export interface Reconciliation {
  status: "absorbed" | "not_in_document" | "projected";
  into?: string;
  document?: string;
  message?: string;
}

export interface ManualEntryResult {
  transaction?: Transaction;
  reconciliation?: Reconciliation | null;
  plan?: InstallmentPlan;
}

function storedMethod(): PaymentMethod {
  const value = window.localStorage.getItem(METHOD_STORAGE_KEY);
  return METHODS.includes(value as PaymentMethod)
    ? (value as PaymentMethod)
    : "credit";
}

/** User-facing message for the reconciliation outcome of a manual entry (R10.3). */
export function reconciliationMessage(result: ManualEntryResult): string {
  if (result.plan)
    return `Parcelamento criado: ${result.plan.description} em ${result.plan.total_installments}x.`;
  const rec = result.reconciliation;
  if (!rec) return "Lançamento salvo.";
  if (rec.status === "absorbed")
    return `Já estava em ${rec.document ?? "um documento importado"}: o lançamento foi casado com a linha importada.`;
  if (rec.status === "not_in_document")
    return `Lançamento salvo, mas ${rec.message ?? `não está no documento ${rec.document ?? ""}`}.`;
  return "Lançamento previsto salvo; será casado quando a fatura/extrato chegar.";
}

interface FormErrors {
  amount?: string;
  description?: string;
  owner?: string;
  category?: string;
  allocation?: string;
}

/** The quick entry form (docs/16 "Lançamento rápido", R10.1, R10.2, R1.11). */
export function QuickEntryForm({ onDone }: { onDone: () => void }) {
  const cards = useList("cards");
  const accounts = useList("accounts");
  const ownerLabel = useOwnerLabels();
  const [amountText, setAmountText] = useState("");
  const [description, setDescription] = useState("");
  const [method, setMethod] = useState<PaymentMethod>(storedMethod);
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const isCreditMethod = method === "credit";
  const defaultHint = useDefaultSplit(
    isCreditMethod ? ownerId : null,
    isCreditMethod ? null : ownerId,
  );
  const [date, setDate] = useState(todayIso);
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [categoryTouched, setCategoryTouched] = useState(false);
  const [allocations, setAllocations] = useState<Allocation | null>(null);
  const [allocationTouched, setAllocationTouched] = useState(false);
  const [installments, setInstallments] = useState<number>(1);
  const [note, setNote] = useState("");
  const [benefitId, setBenefitId] = useState<string | null>(null); // R14.32
  // another card or method: the benefit chosen for the previous one no longer applies
  useEffect(() => setBenefitId(null), [ownerId, method]);
  const [errors, setErrors] = useState<FormErrors>({});

  const isCredit = method === "credit";
  const ownerOptions = useMemo(() => {
    if (isCredit)
      return (cards.data ?? []).map((c) => ({
        value: c.id,
        label: ownerLabel[c.id] ?? c.name,
      }));
    const type = ACCOUNT_TYPE_FOR[method];
    return (accounts.data ?? [])
      .filter((a) => a.type === type)
      .map((a) => ({ value: a.id, label: ownerLabel[a.id] ?? a.name }));
  }, [isCredit, method, cards.data, accounts.data, ownerLabel]);

  // Default owner: the last used for this payment method, else the first allowed one.
  useEffect(() => {
    if (ownerId && ownerOptions.some((o) => o.value === ownerId)) return;
    const last = window.localStorage.getItem(ownerStorageKey(method));
    const pick =
      ownerOptions.find((o) => o.value === last) ?? ownerOptions[0] ?? null;
    setOwnerId(pick ? pick.value : null);
  }, [ownerOptions, ownerId, method]);

  const amount = parseMoneyInput(amountText);
  const [debouncedDescription] = useDebouncedValue(description.trim(), 300);
  const suggestParams = new URLSearchParams({
    description: debouncedDescription,
    payment_method: method,
    amount: amount ?? "0",
  });
  if (ownerId) suggestParams.set(isCredit ? "card_id" : "account_id", ownerId);
  const suggestion = useQuery({
    queryKey: ["suggest", suggestParams.toString()],
    queryFn: () =>
      api.get<Suggest>(`/api/transactions/suggest?${suggestParams.toString()}`),
    enabled: debouncedDescription.length >= 2,
  });

  // R10.2: prefill category/allocation from rules + history unless the user chose already.
  useEffect(() => {
    const data = suggestion.data;
    if (!data) return;
    if (!categoryTouched && data.category_id) setCategoryId(data.category_id);
    if (!allocationTouched) setAllocations(data.allocations);
  }, [suggestion.data, categoryTouched, allocationTouched]);

  const { selected, setSelected } = useMonth();
  const save = useAction<Record<string, unknown>, ManualEntryResult>(
    "post",
    () => "/api/transactions",
  );

  const changeMethod = (value: string | null) => {
    if (!value) return;
    setMethod(value as PaymentMethod);
    setOwnerId(null);
    if (value !== "credit") setInstallments(1);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next: FormErrors = {};
    if (!amount) next.amount = "Informe um valor válido (ex.: 12,50)";
    if (!description.trim()) next.description = "Informe a descrição";
    if (!ownerId)
      next.owner = isCredit ? "Escolha o cartão" : "Escolha a conta";
    if (!categoryId) next.category = "Categoria é obrigatória";
    if (!allocationValid(allocations))
      next.allocation = "Divisão inválida: os percentuais precisam somar 100%";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const body: Record<string, unknown> = {
      purchase_date: date,
      amount,
      description: description.trim(),
      category_id: categoryId,
      payment_method: method,
    };
    body[isCredit ? "card_id" : "account_id"] = ownerId;
    if (method === "benefit" && benefitId) body.benefit_id = benefitId;
    // "Padrão" (untouched or explicit null) = let the backend precedence decide.
    if (allocationTouched && allocations !== null)
      body.allocations = allocations;
    if (isCredit && installments > 1) body.installments = installments;
    if (note.trim()) body.note = note.trim();
    save.mutate(body, {
      onSuccess: (result) => {
        window.localStorage.setItem(METHOD_STORAGE_KEY, method);
        if (ownerId)
          window.localStorage.setItem(ownerStorageKey(method), ownerId);
        // R14.17: an entry in another invoice month (future date, or after the card closing)
        // is not in the month on screen; go to it so it does not look like it vanished.
        const landed =
          result.transaction?.invoice_month ?? result.plan?.first_invoice_month;
        const moved = landed !== undefined && landed !== selected;
        if (moved) setSelected(landed);
        notifications.show({
          title: result.plan ? "Parcelamento criado" : "Lançamento salvo",
          message: moved
            ? `${reconciliationMessage(result)} Entrou na fatura/mês de ${formatMonth(landed)}: mostrando esse mês.`
            : reconciliationMessage(result),
          color:
            result.reconciliation?.status === "not_in_document"
              ? "yellow"
              : "green",
        });
        onDone();
      },
    });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="md">
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="md">
          <TextInput
            label="Valor"
            placeholder="0,00"
            inputMode="decimal"
            required
            data-autofocus
            size="md"
            leftSection={
              <Text size="sm" fw={700} c="dimmed" aria-hidden="true">
                R$
              </Text>
            }
            classNames={{ input: "et-num et-amount-input" }}
            value={amountText}
            onChange={(e) => setAmountText(e.currentTarget.value)}
            error={errors.amount}
          />
          <DateField
            label="Data"
            size="md"
            value={date}
            onChange={setDate}
            required
          />
        </SimpleGrid>
        <Autocomplete
          label="Descrição"
          required
          value={description}
          onChange={setDescription}
          data={suggestion.data?.descriptions ?? []}
          error={errors.description}
        />
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="md">
          <Select
            label="Meio de pagamento"
            data={METHODS.map((m) => ({
              value: m,
              label: METHOD_LABELS[m] ?? m,
            }))}
            value={method}
            onChange={changeMethod}
            allowDeselect={false}
          />
          <Select
            label={
              isCredit
                ? "Cartão"
                : method === "benefit"
                  ? "Cartão de benefícios"
                  : "Conta"
            }
            data={ownerOptions}
            value={ownerId}
            onChange={setOwnerId}
            error={errors.owner}
            nothingFoundMessage="Nenhum cadastro para esse meio"
            required
          />
        </SimpleGrid>
        {method === "benefit" && (
          <BenefitPicker
            key={ownerId ?? ""}
            accountId={ownerId}
            value={benefitId}
            onChange={setBenefitId}
          />
        )}
        <CategorySelect
          value={categoryId}
          onChange={(v) => {
            setCategoryTouched(true);
            setCategoryId(v);
          }}
          error={errors.category}
          description={
            suggestion.data?.category_id && !categoryTouched
              ? "sugerida pela descrição"
              : undefined
          }
        />
        <AllocationPicker
          defaultHint={defaultHint}
          value={allocations}
          onChange={(v) => {
            setAllocationTouched(true);
            setAllocations(v);
          }}
        />
        {errors.allocation && (
          <Text size="sm" c="red" role="alert">
            {errors.allocation}
          </Text>
        )}
        {isCredit && (
          <NumberInput
            label="Parcelas"
            min={1}
            max={120}
            allowDecimal={false}
            value={installments}
            onChange={(v) => setInstallments(Number(v) || 1)}
          />
        )}
        <TextInput
          label="Nota"
          value={note}
          onChange={(e) => setNote(e.currentTarget.value)}
        />
        {save.error && (
          <Text size="sm" c="red" role="alert">
            {errorText(save.error)}
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

/** Global quick entry ("+" button, key N) — docs/16. */
export function QuickEntryButton() {
  const [opened, { open, close }] = useDisclosure(false);
  // useHotkeys ignores key presses inside inputs, textareas and selects by default.
  useHotkeys([["n", open]]);
  return (
    <>
      <Button
        size="sm"
        radius="xl"
        onClick={open}
        aria-keyshortcuts="n"
        aria-label="+ Lançar"
        className="et-quick"
        leftSection={<IconPlus size={16} stroke={2.4} aria-hidden="true" />}
        rightSection={
          <Kbd size="xs" className="et-quick__kbd" aria-hidden="true">
            N
          </Kbd>
        }
      >
        <span className="et-quick__text">
          <T>Lançar</T>
        </span>
      </Button>
      <Modal
        opened={opened}
        onClose={close}
        size="lg"
        classNames={{ content: "et-modal", header: "et-modal__header" }}
        title={
          <Group gap="sm" wrap="nowrap">
            <span className="et-icon-chip" aria-hidden="true">
              <IconBolt size={18} stroke={1.8} />
            </span>
            <span className="et-modal__title">Lançamento rápido</span>
          </Group>
        }
      >
        <Text size="sm" c="dimmed" mb="md">
          Crédito, VR, débito, PIX ou dinheiro. Quando a fatura ou o extrato
          chegar, o lançamento é casado com a linha importada, sem duplicar.
        </Text>
        {opened && <QuickEntryForm onDone={close} />}
      </Modal>
    </>
  );
}

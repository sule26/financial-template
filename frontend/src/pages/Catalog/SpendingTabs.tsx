/** Catalog tabs for spending definitions: categories, goals, subscriptions, recurring, rules. */
import {
  Alert,
  ColorInput,
  ColorSwatch,
  Group,
  NativeSelect,
  NumberInput,
  Radio,
  Switch,
  Text,
  TextInput,
} from "@mantine/core";
import { DateField } from "../../components/ui/DateField";
import { MonthField } from "../../components/ui/MonthField";
import { useList, useNames } from "../../api/hooks";
import type {
  Allocation,
  Category,
  RecurringPurchase,
  Rule,
  SavingsGoal,
  Subscription,
} from "../../api/types";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { CategorySelect } from "../../components/CategorySelect";
import {
  formatDate,
  formatMoney,
  METHOD_LABELS,
  parseMoneyInput,
} from "../../lib/format";
import { formatMonth } from "../../hooks/month";
import {
  checkMoney,
  checkPayment,
  CrudTab,
  DATE_RE,
  describeAllocation,
  IdSelect,
  moneyOrNull,
  moneyToInput,
  MONTH_RE,
  orNull,
  PaymentTarget,
  paymentBody,
  type FormProps,
  type PaymentDraft,
} from "./shared";

const MONTH_LABELS = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

const checkAlloc = (a: Allocation | null): string | null =>
  allocationValid(a) ? null : "Divisão: a soma precisa ser 100%";

// ---------------------------------------------------------------- categories (R1.11, R1.12)

interface CategoryDraft {
  name: string;
  color: string;
  budget: string;
}

/** Portuguese names of the collections touched when a category is deleted. */
export const COLLECTION_LABELS: Record<string, string> = {
  transactions: "lançamentos",
  staging: "lançamentos em revisão",
  installment_plans: "parcelamentos",
  subscriptions: "assinaturas",
  recurring_purchases: "compras recorrentes",
  annotations: "edições guardadas",
  rules: "regras",
};

/** Text for the delete result: which items became uncategorized (R1.12). */
export function describeUncategorized(
  counts: Record<string, number> | undefined,
): string {
  const parts = Object.entries(counts ?? {})
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${COLLECTION_LABELS[k] ?? k}`);
  return parts.length
    ? `Categoria excluída. Ficaram sem categoria: ${parts.join(", ")}. Recategorize pelo alerta no topo.`
    : "Categoria excluída. Nenhum item estava usando esta categoria.";
}

function CategoryForm({ draft, set }: FormProps<CategoryDraft>) {
  return (
    <>
      <TextInput
        label="Nome"
        required
        value={draft.name}
        onChange={(e) => set({ name: e.currentTarget.value })}
      />
      <ColorInput
        label="Cor"
        format="hex"
        value={draft.color}
        onChange={(color) => set({ color })}
      />
      <TextInput
        label="Orçamento mensal"
        description="Opcional"
        placeholder="0,00"
        inputMode="decimal"
        value={draft.budget}
        onChange={(e) => set({ budget: e.currentTarget.value })}
      />
    </>
  );
}

export function CategoriesTab() {
  return (
    <CrudTab<"categories", CategoryDraft>
      resource="categories"
      title="Categorias"
      noun="categoria"
      emptyText="Nenhuma categoria cadastrada."
      rowName={(c) => c.name}
      columns={[
        {
          header: "Nome",
          cell: (c: Category) => (
            <Group gap={6} wrap="nowrap">
              <ColorSwatch color={c.color} size={14} aria-hidden />
              {c.name}
            </Group>
          ),
        },
        { header: "Orçamento", cell: (c: Category) => formatMoney(c.budget) },
      ]}
      blank={() => ({ name: "", color: "#868E96", budget: "" })}
      fromItem={(c) => ({
        name: c.name,
        color: c.color,
        budget: moneyToInput(c.budget),
      })}
      validate={(d) =>
        (!d.name.trim() ? "Nome: obrigatório" : null) ??
        (/^#[0-9a-fA-F]{6}$/.test(d.color)
          ? null
          : "Cor: use o formato #RRGGBB") ??
        checkMoney(d.budget, "Orçamento")
      }
      toBody={(d) => ({
        name: d.name.trim(),
        color: d.color,
        budget: moneyOrNull(d.budget),
      })}
      form={CategoryForm}
      deleteWarning={
        <Alert color="yellow" variant="light">
          Se a categoria estiver em uso, os lançamentos, parcelamentos,
          assinaturas, compras recorrentes e regras que a usam ficam{" "}
          <strong>sem categoria</strong> e aparecem no alerta para
          recategorizar.
        </Alert>
      }
      deleteResult={(r) => (
        <Alert color="blue" variant="light" role="status">
          {describeUncategorized(r.uncategorized)}
        </Alert>
      )}
    />
  );
}

// ---------------------------------------------------------------- savings goals

interface GoalDraft {
  name: string;
  monthly_amount: string;
  user_id: string | null;
}

function GoalForm({ draft, set }: FormProps<GoalDraft>) {
  const users = useList("users").data ?? [];
  return (
    <>
      <TextInput
        label="Nome"
        required
        value={draft.name}
        onChange={(e) => set({ name: e.currentTarget.value })}
      />
      <TextInput
        label="Valor mensal"
        required
        placeholder="0,00"
        inputMode="decimal"
        value={draft.monthly_amount}
        onChange={(e) => set({ monthly_amount: e.currentTarget.value })}
      />
      <IdSelect
        label="Usuário"
        value={draft.user_id}
        onChange={(v) => set({ user_id: v })}
        options={users}
        none="(todos)"
      />
    </>
  );
}

export function GoalsTab() {
  const names = useNames();
  return (
    <CrudTab<"savings-goals", GoalDraft>
      resource="savings-goals"
      title="Metas de poupança"
      noun="meta"
      emptyText="Nenhuma meta cadastrada."
      rowName={(g) => g.name}
      columns={[
        { header: "Nome", cell: (g: SavingsGoal) => g.name },
        {
          header: "Valor mensal",
          cell: (g: SavingsGoal) => formatMoney(g.monthly_amount),
        },
        {
          header: "Usuário",
          cell: (g: SavingsGoal) =>
            g.user_id ? (names.users[g.user_id] ?? g.user_id) : "todos",
        },
      ]}
      blank={() => ({ name: "", monthly_amount: "", user_id: null })}
      fromItem={(g) => ({
        name: g.name,
        monthly_amount: moneyToInput(g.monthly_amount),
        user_id: g.user_id,
      })}
      validate={(d) =>
        (!d.name.trim() ? "Nome: obrigatório" : null) ??
        checkMoney(d.monthly_amount, "Valor mensal", true)
      }
      toBody={(d) => ({
        name: d.name.trim(),
        monthly_amount: parseMoneyInput(d.monthly_amount) ?? "",
        user_id: d.user_id,
      })}
      form={GoalForm}
    />
  );
}

// ---------------------------------------------------------------- subscriptions (R1.4)

interface SubscriptionDraft extends PaymentDraft {
  description: string;
  amount: string;
  period: Subscription["period"];
  month_of_year: number | null;
  start_month: string;
  end_month: string;
  category_id: string | null;
  allocations: Allocation | null;
}

export function checkSubscription(d: SubscriptionDraft): string | null {
  if (!d.description.trim()) return "Descrição: obrigatória";
  const money = checkMoney(d.amount, "Valor", true);
  if (money) return money;
  if (d.period === "annual" && d.month_of_year === null)
    return "Mês da cobrança: obrigatório";
  if (!MONTH_RE.test(d.start_month.trim())) return "Início: escolha o mês";
  if (d.end_month.trim()) {
    if (!MONTH_RE.test(d.end_month.trim())) return "Fim: escolha o mês";
    if (d.end_month.trim() < d.start_month.trim()) return "Fim antes do início";
  }
  return checkPayment(d) ?? checkAlloc(d.allocations);
}

function SubscriptionForm({ draft, set }: FormProps<SubscriptionDraft>) {
  return (
    <>
      <TextInput
        label="Descrição"
        required
        value={draft.description}
        onChange={(e) => set({ description: e.currentTarget.value })}
      />
      <Group grow align="flex-end">
        <TextInput
          label="Valor"
          required
          placeholder="0,00"
          inputMode="decimal"
          value={draft.amount}
          onChange={(e) => set({ amount: e.currentTarget.value })}
        />
        <Radio.Group
          label="Período"
          value={draft.period}
          onChange={(v) =>
            set({
              period: v as Subscription["period"],
              month_of_year: v === "annual" ? (draft.month_of_year ?? 1) : null,
            })
          }
        >
          <Group mt={4}>
            <Radio value="monthly" label="Mensal" />
            <Radio value="annual" label="Anual" />
          </Group>
        </Radio.Group>
        {draft.period === "annual" && (
          <NativeSelect
            label="Mês da cobrança"
            data={MONTH_LABELS.map((label, i) => ({
              value: String(i + 1),
              label,
            }))}
            value={String(draft.month_of_year ?? 1)}
            onChange={(e) =>
              set({ month_of_year: Number(e.currentTarget.value) })
            }
          />
        )}
      </Group>
      <PaymentTarget value={draft} onChange={set} />
      <Group grow>
        <MonthField
          label="Início"
          required
          value={draft.start_month}
          onChange={(start_month) => set({ start_month })}
        />
        <MonthField
          label="Fim"
          description="Opcional"
          value={draft.end_month}
          onChange={(end_month) => set({ end_month })}
        />
      </Group>
      <CategorySelect
        required={false}
        clearable
        value={draft.category_id}
        onChange={(v) => set({ category_id: v })}
      />
      <AllocationPicker
        value={draft.allocations}
        onChange={(allocations) => set({ allocations })}
      />
    </>
  );
}

export function SubscriptionsTab() {
  const names = useNames();
  return (
    <CrudTab<"subscriptions", SubscriptionDraft>
      resource="subscriptions"
      title="Assinaturas"
      noun="assinatura"
      emptyText="Nenhuma assinatura cadastrada."
      rowName={(s) => s.description}
      columns={[
        { header: "Descrição", cell: (s: Subscription) => s.description },
        { header: "Valor", cell: (s: Subscription) => formatMoney(s.amount) },
        {
          header: "Período",
          cell: (s: Subscription) =>
            s.period === "monthly"
              ? "Mensal"
              : `Anual (${MONTH_LABELS[(s.month_of_year ?? 1) - 1]})`,
        },
        {
          header: "Pagamento",
          cell: (s: Subscription) =>
            `${METHOD_LABELS[s.payment_method] ?? s.payment_method} · ${names.owner(s.card_id ?? s.account_id)}`,
        },
        {
          header: "Vigência",
          cell: (s: Subscription) =>
            `${formatMonth(s.start_month)} → ${s.end_month ? formatMonth(s.end_month) : "sem fim"}`,
        },
        {
          header: "Categoria",
          cell: (s: Subscription) =>
            s.category_id
              ? (names.categories[s.category_id] ?? s.category_id)
              : "sem categoria",
        },
        {
          header: "Divisão",
          cell: (s: Subscription) => describeAllocation(s.allocations, names),
        },
      ]}
      blank={() => ({
        description: "",
        amount: "",
        period: "monthly",
        month_of_year: null,
        payment_method: "credit",
        card_id: null,
        account_id: null,
        start_month: "",
        end_month: "",
        category_id: null,
        allocations: null,
      })}
      fromItem={(s) => ({
        description: s.description,
        amount: moneyToInput(s.amount),
        period: s.period,
        month_of_year: s.month_of_year,
        payment_method: s.payment_method,
        card_id: s.card_id,
        account_id: s.account_id,
        start_month: s.start_month,
        end_month: s.end_month ?? "",
        category_id: s.category_id,
        allocations: s.allocations,
      })}
      validate={checkSubscription}
      toBody={(d) => ({
        description: d.description.trim(),
        amount: parseMoneyInput(d.amount) ?? "",
        period: d.period,
        month_of_year: d.period === "annual" ? d.month_of_year : null,
        ...paymentBody(d),
        start_month: d.start_month.trim(),
        end_month: orNull(d.end_month),
        category_id: d.category_id,
        allocations: d.allocations,
      })}
      form={SubscriptionForm}
    />
  );
}

// ---------------------------------------------------------------- recurring purchases (R12.1)

interface RecurringDraft extends PaymentDraft {
  description: string;
  match_description: string;
  estimated_amount: string;
  every_value: number | null;
  every_unit: RecurringPurchase["every"]["unit"];
  last_date: string;
  category_id: string | null;
  allocations: Allocation | null;
  active: boolean;
}

const UNIT_LABELS: Record<string, string> = {
  days: "dias",
  weeks: "semanas",
  months: "meses",
};

export function checkRecurring(d: RecurringDraft): string | null {
  if (!d.description.trim()) return "Descrição: obrigatória";
  const money = checkMoney(d.estimated_amount, "Valor estimado", true);
  if (money) return money;
  if (!d.every_value || d.every_value < 1)
    return "Intervalo: informe um número ≥ 1";
  if (!DATE_RE.test(d.last_date.trim())) return "Última compra: escolha a data";
  return checkPayment(d) ?? checkAlloc(d.allocations);
}

function RecurringForm({ draft, set }: FormProps<RecurringDraft>) {
  return (
    <>
      <TextInput
        label="Descrição"
        required
        value={draft.description}
        onChange={(e) => set({ description: e.currentTarget.value })}
      />
      <TextInput
        label="Texto na fatura/extrato"
        description="Opcional: como a compra aparece no documento, para casar automaticamente"
        value={draft.match_description}
        onChange={(e) => set({ match_description: e.currentTarget.value })}
      />
      <Group grow align="flex-end">
        <TextInput
          label="Valor estimado"
          required
          placeholder="0,00"
          inputMode="decimal"
          value={draft.estimated_amount}
          onChange={(e) => set({ estimated_amount: e.currentTarget.value })}
        />
        <NumberInput
          label="A cada"
          min={1}
          allowDecimal={false}
          value={draft.every_value ?? ""}
          onChange={(v) =>
            set({ every_value: v === "" ? null : Math.trunc(Number(v)) })
          }
        />
        <NativeSelect
          label="Unidade"
          data={Object.entries(UNIT_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
          value={draft.every_unit}
          onChange={(e) =>
            set({
              every_unit: e.currentTarget.value as RecurringDraft["every_unit"],
            })
          }
        />
      </Group>
      <DateField
        label="Data da última compra"
        required
        value={draft.last_date}
        onChange={(last_date) => set({ last_date })}
      />
      <PaymentTarget value={draft} onChange={set} />
      <CategorySelect
        required={false}
        clearable
        value={draft.category_id}
        onChange={(v) => set({ category_id: v })}
      />
      <AllocationPicker
        value={draft.allocations}
        onChange={(allocations) => set({ allocations })}
      />
      <Switch
        label="Ativa"
        checked={draft.active}
        onChange={(e) => set({ active: e.currentTarget.checked })}
      />
    </>
  );
}

export function RecurringTab() {
  const names = useNames();
  return (
    <CrudTab<"recurring-purchases", RecurringDraft>
      resource="recurring-purchases"
      title="Compras recorrentes"
      noun="compra recorrente"
      emptyText="Nenhuma compra recorrente cadastrada."
      rowName={(r) => r.description}
      columns={[
        { header: "Descrição", cell: (r: RecurringPurchase) => r.description },
        {
          header: "Valor estimado",
          cell: (r: RecurringPurchase) => formatMoney(r.estimated_amount),
        },
        {
          header: "Intervalo",
          cell: (r: RecurringPurchase) =>
            `a cada ${r.every.value} ${UNIT_LABELS[r.every.unit] ?? r.every.unit}`,
        },
        {
          header: "Última",
          cell: (r: RecurringPurchase) => formatDate(r.last_date),
        },
        {
          header: "Próxima",
          cell: (r: RecurringPurchase) => formatDate(r.next_date),
        },
        {
          header: "Pagamento",
          cell: (r: RecurringPurchase) =>
            `${METHOD_LABELS[r.payment_method] ?? r.payment_method} · ${names.owner(r.card_id ?? r.account_id)}`,
        },
        {
          header: "Situação",
          cell: (r: RecurringPurchase) => (r.active ? "ativa" : "pausada"),
        },
      ]}
      blank={() => ({
        description: "",
        match_description: "",
        estimated_amount: "",
        every_value: 30,
        every_unit: "days",
        last_date: "",
        payment_method: "credit",
        card_id: null,
        account_id: null,
        category_id: null,
        allocations: null,
        active: true,
      })}
      fromItem={(r) => ({
        description: r.description,
        match_description: r.match_description ?? "",
        estimated_amount: moneyToInput(r.estimated_amount),
        every_value: r.every.value,
        every_unit: r.every.unit,
        last_date: r.last_date,
        payment_method: r.payment_method,
        card_id: r.card_id,
        account_id: r.account_id,
        category_id: r.category_id,
        allocations: r.allocations,
        active: r.active,
      })}
      validate={checkRecurring}
      toBody={(d) => ({
        description: d.description.trim(),
        match_description: orNull(d.match_description),
        estimated_amount: parseMoneyInput(d.estimated_amount) ?? "",
        every: { value: d.every_value ?? 1, unit: d.every_unit },
        last_date: d.last_date.trim(),
        ...paymentBody(d),
        category_id: d.category_id,
        allocations: d.allocations,
        active: d.active,
      })}
      form={RecurringForm}
    />
  );
}

// ---------------------------------------------------------------- rules

interface RuleDraft {
  priority: number | null;
  enabled: boolean;
  regex: string;
  card_id: string | null;
  account_id: string | null;
  when_category_id: string | null;
  min_amount: string;
  max_amount: string;
  then_category_id: string | null;
  then_allocations: Allocation | null;
}

export function checkRule(d: RuleDraft): string | null {
  if (d.priority === null) return "Prioridade: obrigatória";
  // The regex is validated by the backend (Python syntax), not here.
  const money =
    checkMoney(d.min_amount, "Valor mínimo") ??
    checkMoney(d.max_amount, "Valor máximo");
  if (money) return money;
  if (d.then_category_id === null && d.then_allocations === null)
    return "Então: defina uma categoria e/ou uma divisão";
  return checkAlloc(d.then_allocations);
}

function RuleForm({ draft, set }: FormProps<RuleDraft>) {
  const cards = useList("cards").data ?? [];
  const accounts = useList("accounts").data ?? [];
  return (
    <>
      <Group grow align="flex-end">
        <NumberInput
          label="Prioridade"
          description="Menor número aplica primeiro"
          allowDecimal={false}
          value={draft.priority ?? ""}
          onChange={(v) =>
            set({ priority: v === "" ? null : Math.trunc(Number(v)) })
          }
        />
        <Switch
          label="Habilitada"
          checked={draft.enabled}
          onChange={(e) => set({ enabled: e.currentTarget.checked })}
        />
      </Group>
      <Text fw={600}>Quando</Text>
      <TextInput
        label="Descrição (regex)"
        placeholder="ex.: UBER|99"
        value={draft.regex}
        onChange={(e) => set({ regex: e.currentTarget.value })}
      />
      <Group grow>
        <IdSelect
          label="Cartão"
          value={draft.card_id}
          onChange={(v) => set({ card_id: v })}
          options={cards}
          none="(qualquer)"
        />
        <IdSelect
          label="Conta"
          value={draft.account_id}
          onChange={(v) => set({ account_id: v })}
          options={accounts}
          none="(qualquer)"
        />
      </Group>
      <CategorySelect
        label="Categoria atual"
        required={false}
        clearable
        value={draft.when_category_id}
        onChange={(v) => set({ when_category_id: v })}
      />
      <Group grow>
        <TextInput
          label="Valor mínimo"
          inputMode="decimal"
          value={draft.min_amount}
          onChange={(e) => set({ min_amount: e.currentTarget.value })}
        />
        <TextInput
          label="Valor máximo"
          inputMode="decimal"
          value={draft.max_amount}
          onChange={(e) => set({ max_amount: e.currentTarget.value })}
        />
      </Group>
      <Text fw={600}>Então</Text>
      <CategorySelect
        label="Definir categoria"
        required={false}
        clearable
        value={draft.then_category_id}
        onChange={(v) => set({ then_category_id: v })}
      />
      <AllocationPicker
        label="Definir divisão (Padrão = não mexe)"
        value={draft.then_allocations}
        onChange={(then_allocations) => set({ then_allocations })}
      />
    </>
  );
}

/** Short text for a rule's conditions. */
export function describeWhen(
  r: Rule,
  names: ReturnType<typeof useNames>,
): string {
  const w = r.when;
  const parts = [
    w.description_regex && `descrição ~ /${w.description_regex}/`,
    w.card_id && `cartão ${names.cards[w.card_id] ?? w.card_id}`,
    w.account_id && `conta ${names.accounts[w.account_id] ?? w.account_id}`,
    w.category_id &&
      `categoria ${names.categories[w.category_id] ?? w.category_id}`,
    w.min_amount && `≥ ${formatMoney(w.min_amount)}`,
    w.max_amount && `≤ ${formatMoney(w.max_amount)}`,
  ].filter(Boolean);
  return parts.length ? parts.join(" e ") : "sempre";
}

export function RulesTab() {
  const names = useNames();
  return (
    <CrudTab<"rules", RuleDraft>
      resource="rules"
      title="Regras"
      noun="regra"
      emptyText="Nenhuma regra cadastrada."
      rowName={(r) => `regra ${r.priority} (${r.id})`}
      columns={[
        { header: "Prioridade", cell: (r: Rule) => r.priority },
        { header: "Quando", cell: (r: Rule) => describeWhen(r, names) },
        {
          header: "Então",
          cell: (r: Rule) =>
            [
              r.then.category_id &&
                `categoria ${names.categories[r.then.category_id] ?? r.then.category_id}`,
              r.then.allocations &&
                `divisão ${describeAllocation(r.then.allocations, names)}`,
            ]
              .filter(Boolean)
              .join(" + ") || "—",
        },
        {
          header: "Situação",
          cell: (r: Rule) => (r.enabled ? "habilitada" : "desabilitada"),
        },
      ]}
      blank={() => ({
        priority: 100,
        enabled: true,
        regex: "",
        card_id: null,
        account_id: null,
        when_category_id: null,
        min_amount: "",
        max_amount: "",
        then_category_id: null,
        then_allocations: null,
      })}
      fromItem={(r) => ({
        priority: r.priority,
        enabled: r.enabled,
        regex: r.when.description_regex ?? "",
        card_id: r.when.card_id,
        account_id: r.when.account_id,
        when_category_id: r.when.category_id,
        min_amount: moneyToInput(r.when.min_amount),
        max_amount: moneyToInput(r.when.max_amount),
        then_category_id: r.then.category_id,
        then_allocations: r.then.allocations,
      })}
      validate={checkRule}
      toBody={(d) => ({
        priority: d.priority ?? 100,
        enabled: d.enabled,
        when: {
          description_regex: orNull(d.regex),
          card_id: d.card_id,
          account_id: d.account_id,
          category_id: d.when_category_id,
          min_amount: moneyOrNull(d.min_amount),
          max_amount: moneyOrNull(d.max_amount),
        },
        then: {
          category_id: d.then_category_id,
          allocations: d.then_allocations,
        },
      })}
      form={RuleForm}
    />
  );
}

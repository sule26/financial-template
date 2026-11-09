/** Catalog tabs for where money goes through: accounts and cards (R1.1, R1.10, R6.7–R6.9). */
import {
  Alert,
  Anchor,
  NativeSelect,
  NumberInput,
  Radio,
  Group,
  TagsInput,
  Text,
  TextInput,
} from "@mantine/core";
import { Link } from "react-router-dom";
import { MonthField } from "../../components/ui/MonthField";
import { useList, useNames } from "../../api/hooks";
import type {
  Account,
  AccountType,
  Allocation,
  BillingEntry,
  Card,
} from "../../api/types";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { formatMoney } from "../../lib/format";
import { formatMonth } from "../../hooks/month";
import {
  checkMoney,
  CrudTab,
  describeAllocation,
  EntryList,
  IdSelect,
  moneyOrNull,
  moneyToInput,
  MONTH_RE,
  orNull,
  type FormProps,
} from "./shared";
import { StatusBadge } from "../../components/ui";
import {
  describeInherited,
  resolveCardOwnership,
  type InheritedFrom,
} from "./cardInheritance";
import {
  BankSelect,
  FolderHint,
  FormSection,
  OwnershipSummary,
  ResponsiblesField,
} from "./guided";

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  checking: "Conta corrente",
  benefit: "Cartão de benefícios",
  cash: "Dinheiro (carteira)",
};

const toInt = (value: string | number): number | null =>
  value === "" || value === null ? null : Math.trunc(Number(value));

// ---------------------------------------------------------------- accounts

interface AccountDraft {
  name: string;
  type: AccountType;
  owners: Allocation | null;
  responsible_user_id: string | null;
  responsibles: Allocation | null;
  profile_id: string;
  account_hint: string;
  confirm_manual_after_days: number | null;
  renewal_day: number | null;
}

function AccountForm({ draft, set }: FormProps<AccountDraft>) {
  const users = useList("users").data ?? [];
  const isBenefit = draft.type === "benefit";
  const isCash = draft.type === "cash";
  return (
    <>
      <FormSection
        title="Identificação"
        hint="Conta corrente (extrato, débito, PIX), cartão de benefícios (Caju, Flash, Alelo…) ou dinheiro na carteira."
      >
        <TextInput
          label="Nome"
          description="Como aparece nas telas (ex.: Inter, Conta conjunta, VR)."
          required
          value={draft.name}
          onChange={(e) => set({ name: e.currentTarget.value })}
        />
        <NativeSelect
          label="Tipo"
          data={Object.entries(ACCOUNT_TYPE_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
          value={draft.type}
          description={
            isBenefit
              ? "cartão de benefícios: cada benefício dele (VR, VA, Home office…) é cadastrado na aba Benefícios; não tem fechamento nem vencimento, só dia de renovação"
              : undefined
          }
          onChange={(e) => set({ type: e.currentTarget.value as AccountType })}
        />
        {isBenefit && (
          <NumberInput
            label="Dia de renovação"
            description="Opcional: dia do mês em que o saldo do benefício é creditado"
            min={1}
            max={31}
            allowDecimal={false}
            value={draft.renewal_day ?? ""}
            onChange={(v) => set({ renewal_day: toInt(v) })}
          />
        )}
      </FormSection>
      <FormSection
        title="Quem usa e quem paga"
        hint="Quem usa define a divisão padrão dos gastos; quem paga é quem acerta com o banco e recebe dos outros."
      >
        <AllocationPicker
          label="Quem usa (donos)"
          allowEmpty={false}
          value={draft.owners}
          onChange={(owners) => set({ owners })}
        />
        <IdSelect
          label={
            isBenefit
              ? "Responsável (titular do benefício)"
              : "Responsável (quem paga o banco)"
          }
          value={draft.responsible_user_id}
          onChange={(v) => set({ responsible_user_id: v })}
          options={users}
          required
        />
        <ResponsiblesField
          value={draft.responsibles}
          principal={draft.responsible_user_id}
          onChange={(responsibles, responsible_user_id) =>
            set({ responsibles, responsible_user_id })
          }
        />
      </FormSection>
      {!isCash && (
        <FormSection title="Leitura do extrato">
          {draft.name.trim() && (
            <FolderHint kind="extratos" name={draft.name} />
          )}
          <BankSelect
            kind="extrato"
            value={draft.profile_id}
            onChange={(profile_id) => set({ profile_id })}
          />
          <TextInput
            label="Identificação no extrato"
            description="Opcional: agência/conta como aparece no PDF, para reconhecer o extrato fora da pasta"
            value={draft.account_hint}
            onChange={(e) => set({ account_hint: e.currentTarget.value })}
          />
          <NumberInput
            label="Confirmar lançamento manual após (dias)"
            description="Opcional: silencia o aviso “não apareceu no extrato” após N dias"
            min={1}
            allowDecimal={false}
            value={draft.confirm_manual_after_days ?? ""}
            onChange={(v) => set({ confirm_manual_after_days: toInt(v) })}
          />
        </FormSection>
      )}
    </>
  );
}

export function AccountsTab() {
  const names = useNames();
  const users = useList("users").data ?? [];
  return (
    <CrudTab<"accounts", AccountDraft>
      resource="accounts"
      title="Contas"
      noun="conta"
      emptyText="Nenhuma conta cadastrada."
      rowName={(a) => a.name}
      columns={[
        { header: "Nome", cell: (a: Account) => a.name },
        {
          header: "Tipo",
          cell: (a: Account) =>
            a.type === "benefit" ? (
              <>
                <span>cartão de benefícios</span>
                {a.renewal_day != null && (
                  <>
                    {" "}
                    <StatusBadge tone="neutral" size="xs">
                      renova dia {a.renewal_day}
                    </StatusBadge>
                  </>
                )}
              </>
            ) : (
              ACCOUNT_TYPE_LABELS[a.type]
            ),
        },
        {
          header: "Donos",
          cell: (a: Account) => describeAllocation(a.owners, names),
        },
        {
          header: "Responsável",
          cell: (a: Account) =>
            a.responsibles
              ? describeAllocation(a.responsibles, names)
              : (names.users[a.responsible_user_id] ?? a.responsible_user_id),
        },
      ]}
      blank={() => {
        const first = users[0]?.id ?? null;
        return {
          name: "",
          type: "checking",
          owners: first ? [{ user_id: first, pct: "100.00" }] : null,
          responsible_user_id: first,
          responsibles: null,
          profile_id: "",
          account_hint: "",
          confirm_manual_after_days: null,
          renewal_day: null,
        };
      }}
      fromItem={(a) => ({
        name: a.name,
        type: a.type,
        owners: a.owners,
        responsible_user_id: a.responsible_user_id,
        responsibles: a.responsibles ?? null,
        profile_id: a.profile_id ?? "",
        account_hint: a.account_hint ?? "",
        confirm_manual_after_days: a.confirm_manual_after_days,
        renewal_day: a.renewal_day ?? null,
      })}
      validate={(d) => {
        if (!d.name.trim()) return "Nome: obrigatório";
        if (d.owners === null || !allocationValid(d.owners))
          return "Donos: escolha os donos (soma 100%)";
        if (!d.responsible_user_id) return "Responsável: obrigatório";
        if (d.responsibles !== null && !allocationValid(d.responsibles))
          return "Quem paga o banco: a soma precisa ser 100%";
        return null;
      }}
      toBody={(d) => ({
        name: d.name.trim(),
        type: d.type,
        owners: d.owners ?? undefined,
        responsible_user_id: d.responsible_user_id ?? "",
        responsibles: d.responsibles,
        profile_id: orNull(d.profile_id),
        account_hint: orNull(d.account_hint),
        confirm_manual_after_days: d.confirm_manual_after_days,
        // Only benefit accounts renew (R13.17); the backend rejects it elsewhere.
        renewal_day: d.type === "benefit" ? d.renewal_day : null,
      })}
      form={AccountForm}
    />
  );
}

// ---------------------------------------------------------------- cards

interface CardDraft {
  id: string | null;
  name: string;
  additional: boolean;
  parent_card_id: string | null;
  account_id: string | null;
  owners: Allocation | null;
  responsible_user_id: string | null;
  responsibles: Allocation | null;
  last_digits: string[];
  billing: BillingEntry[];
  limit: string;
  profile_id: string;
}

export function checkCard(d: CardDraft): string | null {
  if (!d.name.trim()) return "Nome: obrigatório";
  if (d.additional && !d.parent_card_id)
    return "Cartão principal: obrigatório para adicional";
  if (!d.additional && d.billing.length === 0)
    return "Fechamento/vencimento: cartão principal precisa de ao menos uma vigência";
  for (const b of d.billing) {
    if (!MONTH_RE.test(b.from_month.trim())) return "Vigência: escolha o mês";
    if (
      !(
        b.closing_day >= 1 &&
        b.closing_day <= 31 &&
        b.due_day >= 1 &&
        b.due_day <= 31
      )
    )
      return "Vigência: dias devem estar entre 1 e 31";
  }
  const bad = d.last_digits.find((x) => !/^\d{4}$/.test(x));
  if (bad !== undefined)
    return `Finais: “${bad}” deve ter exatamente 4 dígitos`;
  if (d.owners !== null && !allocationValid(d.owners))
    return "Donos: a soma precisa ser 100%";
  if (d.responsibles !== null && !allocationValid(d.responsibles))
    return "Quem paga o banco: a soma precisa ser 100%";
  if (d.responsibles !== null && !d.responsible_user_id)
    return "Responsável: escolha o responsável principal";
  return checkMoney(d.limit, "Limite");
}

function CardForm({ draft, set }: FormProps<CardDraft>) {
  const users = useList("users").data ?? [];
  const cards = useList("cards").data ?? [];
  const accounts = useList("accounts").data ?? [];
  const mains = cards.filter(
    (c) => c.parent_card_id === null && c.id !== draft.id,
  );
  // R14.5: live summary of what this card will use, resolved like the backend does.
  const preview = resolveCardOwnership(
    {
      id: draft.id ?? "__new__",
      name: draft.name,
      parent_card_id: draft.additional ? draft.parent_card_id : null,
      account_id: draft.account_id,
      owners: draft.owners,
      responsible_user_id: draft.responsible_user_id,
      responsibles: draft.responsibles,
      last_digits: draft.last_digits,
      billing_history: draft.billing,
      limit: null,
      profile_id: null,
    },
    cards,
    accounts,
  );
  return (
    <>
      <FormSection
        title="Identificação"
        hint="Um cartão principal tem fatura própria. Um adicional (o cartão que outra pessoa usa) sai na fatura do principal."
      >
        <TextInput
          label="Nome"
          description="Como aparece nas telas (ex.: Inter, Nubank). Cartões com o mesmo nome de uma conta são diferenciados pelos finais."
          required
          value={draft.name}
          onChange={(e) => set({ name: e.currentTarget.value })}
        />
        <Radio.Group
          label="Tipo de cartão"
          value={draft.additional ? "additional" : "main"}
          onChange={(v) =>
            set({
              additional: v === "additional",
              parent_card_id: null,
              // an additional card bills on the main card: no closing/due days of its own
              billing:
                v === "additional"
                  ? []
                  : draft.billing.length > 0
                    ? draft.billing
                    : [{ from_month: "", closing_day: 1, due_day: 10 }],
            })
          }
        >
          <Group mt={4}>
            <Radio value="main" label="Principal" />
            <Radio value="additional" label="Adicional (fatura do principal)" />
          </Group>
        </Radio.Group>
        {draft.additional && (
          <IdSelect
            label="Cartão principal"
            value={draft.parent_card_id}
            onChange={(v) => set({ parent_card_id: v })}
            options={mains}
            required
          />
        )}
        <TagsInput
          label="Finais do cartão"
          description="Os 4 últimos dígitos de cada cartão físico ou virtual (Enter para adicionar). Servem para separar as compras de cada um na fatura."
          value={draft.last_digits}
          onChange={(last_digits) => set({ last_digits })}
        />
      </FormSection>

      <FormSection
        title="Quem usa e quem paga"
        hint="Deixe em “Padrão” / “(herdar)” para usar o que está na conta vinculada ou no cartão principal (ex.: cartão da conta conjunta)."
      >
        <IdSelect
          label="Conta vinculada"
          value={draft.account_id}
          onChange={(v) => set({ account_id: v })}
          options={accounts}
          none="(nenhuma)"
        />
        <AllocationPicker
          label="Quem usa (donos)"
          value={draft.owners}
          onChange={(owners) => set({ owners })}
        />
        <IdSelect
          label="Responsável"
          value={draft.responsible_user_id}
          onChange={(v) =>
            set({
              responsible_user_id: v,
              // without an own responsible the card inherits payers too (R14.1)
              responsibles: v === null ? null : draft.responsibles,
            })
          }
          options={users}
          none="(herdar)"
        />
        <ResponsiblesField
          value={draft.responsibles}
          principal={draft.responsible_user_id}
          onChange={(responsibles, responsible_user_id) =>
            set({ responsibles, responsible_user_id })
          }
        />
        <OwnershipSummary
          owners={preview.owners.value}
          ownersFrom={
            preview.owners.from && describeInherited(preview.owners.from)
          }
          responsible={preview.responsible.value}
          responsibles={preview.responsibles}
          responsibleFrom={
            preview.responsible.from &&
            describeInherited(preview.responsible.from)
          }
        />
      </FormSection>

      {!draft.additional && (
        <FormSection
          title="Fatura"
          hint="Fechamento: dia em que a fatura fecha. Vencimento: dia de pagar. Se o banco mudar as datas, adicione uma vigência nova a partir do mês da mudança; os meses anteriores não mudam."
        >
          <EntryList
            label="Fechamento e vencimento"
            items={draft.billing}
            onChange={(billing) => set({ billing })}
            make={() => ({ from_month: "", closing_day: 1, due_day: 10 })}
            row={(b, update, i) => (
              <>
                <MonthField
                  label={`A partir de (vigência ${i + 1})`}
                  clearable={false}
                  value={b.from_month}
                  onChange={(from_month) => update({ from_month })}
                />
                <NumberInput
                  label={`Fechamento (vigência ${i + 1})`}
                  min={1}
                  max={31}
                  allowDecimal={false}
                  value={b.closing_day}
                  onChange={(v) => update({ closing_day: toInt(v) ?? 0 })}
                />
                <NumberInput
                  label={`Vencimento (vigência ${i + 1})`}
                  min={1}
                  max={31}
                  allowDecimal={false}
                  value={b.due_day}
                  onChange={(v) => update({ due_day: toInt(v) ?? 0 })}
                />
              </>
            )}
          />
          <TextInput
            label="Limite"
            description="Opcional."
            placeholder="0,00"
            inputMode="decimal"
            value={draft.limit}
            onChange={(e) => set({ limit: e.currentTarget.value })}
          />
        </FormSection>
      )}

      {!draft.additional && (
        <FormSection title="Leitura do PDF">
          {draft.name.trim() && <FolderHint kind="faturas" name={draft.name} />}
          <BankSelect
            kind="fatura"
            value={draft.profile_id}
            onChange={(profile_id) => set({ profile_id })}
          />
        </FormSection>
      )}
    </>
  );
}

/** A resolved owners/responsible cell: the value and, when inherited, where it comes from. */
function InheritedCell({
  text,
  from,
  missing,
}: {
  text: string | null;
  from: InheritedFrom | null;
  missing: string;
}) {
  if (text === null)
    return (
      <Text span size="sm" c="red">
        {missing}
      </Text>
    );
  return (
    <>
      <span>{text}</span>
      {from && (
        <>
          {" "}
          <Text span size="xs" c="dimmed">
            ({describeInherited(from)})
          </Text>
        </>
      )}
    </>
  );
}

export function CardsTab() {
  const names = useNames();
  const cards = useList("cards").data ?? [];
  const accounts = useList("accounts").data ?? [];
  const ownership = (c: Card) => resolveCardOwnership(c, cards, accounts);
  return (
    <CrudTab<"cards", CardDraft>
      resource="cards"
      title="Cartões"
      noun="cartão"
      rowName={(c) => c.name}
      intro={
        <Alert color="blue" variant="light">
          Cartão de benefícios? Cadastre em{" "}
          <Anchor component={Link} to="?tab=contas">
            Contas
          </Anchor>{" "}
          com tipo Benefício — ele não tem fechamento nem vencimento, só dia de
          renovação.
        </Alert>
      }
      columns={[
        {
          header: "Nome",
          cell: (c: Card) => (
            <>
              {c.name}{" "}
              {c.parent_card_id && (
                <StatusBadge tone="neutral" size="xs">
                  adicional de{" "}
                  {names.cards[c.parent_card_id] ?? c.parent_card_id}
                </StatusBadge>
              )}
            </>
          ),
        },
        {
          header: "Finais",
          cell: (c: Card) => c.last_digits.join(", ") || "—",
        },
        {
          header: "Donos",
          cell: (c: Card) => {
            const { owners } = ownership(c);
            return (
              <InheritedCell
                text={
                  owners.value ? describeAllocation(owners.value, names) : null
                }
                from={owners.from}
                missing="sem dono (configure)"
              />
            );
          },
        },
        {
          header: "Responsável",
          cell: (c: Card) => {
            const { responsible, responsibles } = ownership(c);
            return (
              <InheritedCell
                text={
                  responsibles
                    ? describeAllocation(responsibles, names)
                    : responsible.value
                      ? (names.users[responsible.value] ?? responsible.value)
                      : null
                }
                from={responsible.from}
                missing="sem responsável (configure)"
              />
            );
          },
        },
        {
          header: "Fechamento/vencimento",
          cell: (c: Card) => {
            const last = [...c.billing_history]
              .sort((a, b) => a.from_month.localeCompare(b.from_month))
              .pop();
            return last
              ? `dia ${last.closing_day} / dia ${last.due_day} (desde ${formatMonth(last.from_month)})`
              : "da fatura principal";
          },
        },
        { header: "Limite", cell: (c: Card) => formatMoney(c.limit) },
      ]}
      blank={() => ({
        id: null,
        name: "",
        additional: false,
        parent_card_id: null,
        account_id: null,
        owners: null,
        responsible_user_id: null,
        responsibles: null,
        last_digits: [],
        billing: [{ from_month: "", closing_day: 1, due_day: 10 }],
        limit: "",
        profile_id: "",
      })}
      fromItem={(c) => ({
        id: c.id,
        name: c.name,
        additional: c.parent_card_id !== null,
        parent_card_id: c.parent_card_id,
        account_id: c.account_id,
        owners: c.owners,
        responsible_user_id: c.responsible_user_id,
        responsibles: c.responsibles ?? null,
        last_digits: c.last_digits,
        billing: c.billing_history,
        limit: moneyToInput(c.limit),
        profile_id: c.profile_id ?? "",
      })}
      validate={checkCard}
      toBody={(d) => ({
        name: d.name.trim(),
        parent_card_id: d.additional ? d.parent_card_id : null,
        account_id: d.account_id,
        owners: d.owners,
        responsible_user_id: d.responsible_user_id,
        responsibles: d.responsibles,
        last_digits: d.last_digits,
        billing_history: d.billing.map((b) => ({
          ...b,
          from_month: b.from_month.trim(),
        })),
        limit: moneyOrNull(d.limit),
        profile_id: orNull(d.profile_id),
      })}
      form={CardForm}
    />
  );
}

/** Catalog tab for work benefits (R11.5): VR/VA on a benefit card, allowances in a checking account. */
import {
  Alert,
  SegmentedControl,
  Stack,
  Switch,
  Text,
  TextInput,
} from "@mantine/core";
import { MonthField } from "../../components/ui/MonthField";
import { useList, useNames } from "../../api/hooks";
import type { Account, AccountType, Benefit } from "../../api/types";
import { useMonth } from "../../hooks/month";
import {
  checkIncome,
  currentIncome,
  toIncome,
  toIncomeDraft,
  type IncomeDraft,
} from "./PeopleTabs";
import { CrudTab, EntryList, IdSelect, type FormProps } from "./shared";

type Destination = Benefit["destination"];

/** Account type each destination requires (mirrors the backend validation). */
export const BENEFIT_ACCOUNT_TYPE: Record<Destination, AccountType> = {
  card: "benefit",
  account: "checking",
};

export const DESTINATION_LABELS: Record<Destination, string> = {
  card: "Cartão de benefício",
  account: "Na conta",
};

export interface BenefitDraft {
  name: string;
  user_id: string | null;
  destination: Destination;
  account_id: string | null;
  amounts: IncomeDraft[];
  active: boolean;
}

const accountsFor = (accounts: Account[], destination: Destination) =>
  accounts.filter((a) => a.type === BENEFIT_ACCOUNT_TYPE[destination]);

export function checkBenefit(d: BenefitDraft): string | null {
  if (!d.name.trim()) return "Nome: obrigatório";
  if (!d.user_id) return "Pessoa: obrigatória";
  if (!d.account_id)
    return d.destination === "card"
      ? "Escolha o cartão de benefício"
      : "Escolha a conta";
  if (d.amounts.length === 0)
    return "Valor mensal: adicione ao menos uma vigência";
  return checkIncome(d.amounts, "Valor mensal");
}

function BenefitForm({ draft, set }: FormProps<BenefitDraft>) {
  const users = useList("users").data ?? [];
  const accounts = useList("accounts").data ?? [];
  const options = accountsFor(accounts, draft.destination);
  const isCard = draft.destination === "card";
  const chosen = options.find((a) => a.id === draft.account_id);
  return (
    <>
      <TextInput
        label="Nome"
        placeholder="Ex.: VR, Auxílio home office"
        required
        value={draft.name}
        onChange={(e) => set({ name: e.currentTarget.value })}
      />
      <IdSelect
        label="Pessoa"
        value={draft.user_id}
        onChange={(v) => set({ user_id: v })}
        options={users}
        required
      />
      <Stack gap={4}>
        <Text size="sm" fw={500} id="benefit-destination-label">
          Onde cai
        </Text>
        <SegmentedControl
          aria-labelledby="benefit-destination-label"
          radius="xl"
          data={(Object.keys(DESTINATION_LABELS) as Destination[]).map(
            (value) => ({ value, label: DESTINATION_LABELS[value] }),
          )}
          value={draft.destination}
          onChange={(value) => {
            const destination = value as Destination;
            // The account must match the new destination: pick the first allowed one.
            set({
              destination,
              account_id: accountsFor(accounts, destination)[0]?.id ?? null,
            });
          }}
        />
        <Text size="xs" c="dimmed">
          {isCard
            ? "VR/VA: o saldo cai num cartão de benefício (conta do tipo Benefício), usado como meio de pagamento “Benefício” no lançamento rápido. Conta como renda em benefício."
            : "Ex.: auxílio home office: cai na conta corrente e soma na renda do mês."}
        </Text>
      </Stack>
      {options.length === 0 ? (
        <Alert color="yellow" variant="light" role="status">
          {isCard
            ? "Nenhum cartão de benefício cadastrado: crie a conta do cartão de benefício em Contas (tipo Benefício)."
            : "Nenhuma conta corrente cadastrada: crie a conta corrente em Contas."}
        </Alert>
      ) : (
        <>
          <IdSelect
            label={isCard ? "Cartão de benefício" : "Conta corrente"}
            value={draft.account_id}
            onChange={(v) => set({ account_id: v })}
            options={options}
            required
          />
          {isCard && chosen && (
            <Text size="xs" c="dimmed">
              {chosen.renewal_day != null
                ? `Renova dia ${chosen.renewal_day}: o crédito do benefício cai nesse dia.`
                : "Dia de renovação não informado: configure em Contas."}
            </Text>
          )}
        </>
      )}
      <Text size="xs" c="dimmed">
        Cada mudança de valor entra como nova vigência; meses anteriores não
        mudam.
      </Text>
      <EntryList
        label="Valor mensal"
        items={draft.amounts}
        onChange={(amounts) => set({ amounts })}
        make={() => ({ from_month: "", amount: "" })}
        row={(r, update, i) => (
          <>
            <MonthField
              label={`A partir de (vigência ${i + 1})`}
              clearable={false}
              value={r.from_month}
              onChange={(from_month) => update({ from_month })}
            />
            <TextInput
              label={`Valor mensal (vigência ${i + 1})`}
              placeholder="0,00"
              inputMode="decimal"
              value={r.amount}
              onChange={(e) => update({ amount: e.currentTarget.value })}
            />
          </>
        )}
      />
      <Switch
        label="Ativo"
        checked={draft.active}
        onChange={(e) => set({ active: e.currentTarget.checked })}
      />
    </>
  );
}

export function BenefitsTab() {
  const names = useNames();
  const { current } = useMonth();
  const users = useList("users").data ?? [];
  const accounts = useList("accounts").data ?? [];
  return (
    <CrudTab<"benefits", BenefitDraft>
      resource="benefits"
      title="Benefícios"
      noun="benefício"
      emptyText="Nenhum benefício cadastrado."
      intro={
        <Text size="sm" c="dimmed">
          VR/VA ficam num cartão de benefício; auxílios pagos em dinheiro (ex.:
          home office) caem na conta corrente e somam na renda.
        </Text>
      }
      rowName={(b) => b.name}
      columns={[
        { header: "Nome", cell: (b: Benefit) => b.name },
        {
          header: "Pessoa",
          cell: (b: Benefit) => names.users[b.user_id] ?? b.user_id,
        },
        {
          header: "Onde cai",
          cell: (b: Benefit) => DESTINATION_LABELS[b.destination],
        },
        {
          header: "Conta",
          cell: (b: Benefit) => {
            const name = names.accounts[b.account_id] ?? b.account_id;
            const day =
              b.destination === "card"
                ? accounts.find((a) => a.id === b.account_id)?.renewal_day
                : null;
            return day != null ? `${name} · renova dia ${day}` : name;
          },
        },
        {
          header: "Valor atual",
          cell: (b: Benefit) => currentIncome(b.amount_history),
        },
        { header: "Ativo", cell: (b: Benefit) => (b.active ? "Sim" : "Não") },
      ]}
      blank={() => ({
        name: "",
        user_id: users[0]?.id ?? null,
        destination: "card",
        account_id: accountsFor(accounts, "card")[0]?.id ?? null,
        amounts: [{ from_month: current, amount: "" }],
        active: true,
      })}
      fromItem={(b) => ({
        name: b.name,
        user_id: b.user_id,
        destination: b.destination,
        account_id: b.account_id,
        amounts: toIncomeDraft(b.amount_history),
        active: b.active,
      })}
      validate={checkBenefit}
      toBody={(d) => ({
        name: d.name.trim(),
        user_id: d.user_id ?? "",
        destination: d.destination,
        account_id: d.account_id ?? "",
        amount_history: toIncome(d.amounts),
        active: d.active,
      })}
      form={BenefitForm}
    />
  );
}

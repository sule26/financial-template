/** Modals for the Investments page: new investment, balance snapshot, movement, close (R9.1–R9.3). */
import {
  Alert,
  Button,
  Group,
  Modal,
  NativeSelect,
  Radio,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { DateField } from "../../components/ui/DateField";
import { useState, type ReactNode } from "react";
import { useList, useOwnerLabels, useSave } from "../../api/hooks";
import type { Allocation, Investment } from "../../api/types";
import {
  checkInstitution,
  InstitutionFields,
  type InstitutionDraft,
} from "../Catalog/InstitutionsTab";
import {
  AllocationPicker,
  allocationValid,
} from "../../components/AllocationPicker";
import { ErrorMessage } from "../../components/QueryState";
import { parseMoneyInput } from "../../lib/format";

export const TYPE_LABELS: Record<Investment["type"], string> = {
  emergency_reserve: "Reserva de emergência",
  fixed_income: "Renda fixa",
  stocks: "Ações",
  funds: "Fundos",
  pension: "Previdência",
  crypto: "Cripto",
  other: "Outro",
};

const DATE_RE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** Re-exported: local "YYYY-MM-DD" for today (default date of the forms). */
export { todayIso } from "../../lib/dates";
import { todayIso } from "../../lib/dates";

function FormModal({
  title,
  opened,
  onClose,
  onSubmit,
  problem,
  error,
  pending,
  children,
}: {
  title: string;
  opened: boolean;
  onClose: () => void;
  onSubmit: () => void;
  problem: string | null;
  error: unknown;
  pending: boolean;
  children: ReactNode;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={title} size="lg">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <Stack gap="sm">
          {children}
          {problem && (
            <Alert color="red" role="alert" title="Verifique os campos">
              {problem}
            </Alert>
          )}
          {error ? <ErrorMessage error={error} /> : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" loading={pending}>
              Salvar
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

/** Select value that opens the inline "new institution" form instead of choosing one. */
export const NEW_INSTITUTION = "__new__";

/**
 * R13.15: institution picker grouped into registered accounts and catalog institutions, with
 * "+ nova instituição" creating one inline (POST /api/institutions) and selecting it.
 */
export function InstitutionSelect({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const accounts = useList("accounts").data ?? [];
  const ownerLabel = useOwnerLabels();
  const institutions = useList("institutions").data ?? [];
  const create = useSave("institutions");
  const [draft, setDraft] = useState<InstitutionDraft | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const closeDraft = () => {
    setDraft(null);
    setProblem(null);
    create.reset();
  };
  const submit = () => {
    if (!draft) return;
    const p = checkInstitution(draft);
    setProblem(p);
    if (p) return;
    create.mutate(
      { name: draft.name.trim(), type: draft.type },
      {
        onSuccess: (created) => {
          onChange(created.id);
          closeDraft();
        },
      },
    );
  };

  const data = [
    { value: "", label: "(nenhuma)" },
    ...(accounts.length > 0
      ? [
          {
            group: "Contas",
            items: accounts.map((a) => ({
              value: a.id,
              label: ownerLabel[a.id] ?? a.name,
            })),
          },
        ]
      : []),
    ...(institutions.length > 0
      ? [
          {
            group: "Instituições",
            items: institutions.map((i) => ({ value: i.id, label: i.name })),
          },
        ]
      : []),
    { value: NEW_INSTITUTION, label: "+ nova instituição" },
  ];
  return (
    <Stack gap="xs">
      <NativeSelect
        label="Instituição"
        description="Conta cadastrada ou corretora/exchange/previdência."
        data={data}
        value={draft ? NEW_INSTITUTION : (value ?? "")}
        onChange={(e) => {
          const v = e.currentTarget.value;
          if (v === NEW_INSTITUTION) {
            setDraft({ name: "", type: "broker" });
            return;
          }
          closeDraft();
          onChange(v || null);
        }}
      />
      {/* Not a nested <form> (invalid HTML): Enter creates the institution, not the investment. */}
      {draft && (
        <Stack
          gap="xs"
          p="sm"
          role="group"
          aria-label="Nova instituição"
          className="et-fade-in"
          style={{
            border: "1px solid var(--mantine-color-default-border)",
            borderRadius: "var(--mantine-radius-md)",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && e.target instanceof HTMLInputElement) {
              e.preventDefault();
              submit();
            }
          }}
        >
          <InstitutionFields
            draft={draft}
            set={(patch) => setDraft({ ...draft, ...patch })}
            labelSuffix=" da instituição"
          />
          {problem && (
            <Text size="sm" c="red" role="alert">
              {problem}
            </Text>
          )}
          {create.error ? <ErrorMessage error={create.error} /> : null}
          <Group justify="flex-end" gap="xs">
            <Button variant="default" size="xs" onClick={closeDraft}>
              Cancelar
            </Button>
            <Button size="xs" onClick={submit} loading={create.isPending}>
              Criar instituição
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}

/** Create a new investment (name, institution, type, owners, goal, account). */
export function NewInvestmentModal({
  opened,
  onClose,
}: {
  opened: boolean;
  onClose: () => void;
}) {
  const users = useList("users").data ?? [];
  const goals = useList("savings-goals").data ?? [];
  const accounts = useList("accounts").data ?? [];
  const ownerLabel = useOwnerLabels();
  const save = useSave("investments");
  const [name, setName] = useState("");
  const [institutionId, setInstitutionId] = useState<string | null>(null);
  const [type, setType] = useState<Investment["type"]>("fixed_income");
  const [owners, setOwners] = useState<Allocation | null>(null);
  const [goalId, setGoalId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const first = users[0]?.id;
  const effectiveOwners =
    owners ?? (first ? [{ user_id: first, pct: "100.00" }] : null);

  const close = () => {
    setName("");
    setInstitutionId(null);
    setOwners(null);
    setGoalId("");
    setAccountId("");
    setProblem(null);
    save.reset();
    onClose();
  };
  const submit = () => {
    const p = !name.trim()
      ? "Nome: obrigatório"
      : effectiveOwners === null || !allocationValid(effectiveOwners)
        ? "Donos: a soma precisa ser 100%"
        : null;
    setProblem(p);
    if (p || effectiveOwners === null) return;
    save.mutate(
      {
        name: name.trim(),
        institution_id: institutionId,
        type,
        owners: effectiveOwners,
        goal_id: goalId || null,
        account_id: accountId || null,
      },
      { onSuccess: close },
    );
  };
  return (
    <FormModal
      title="Novo investimento"
      opened={opened}
      onClose={close}
      onSubmit={submit}
      problem={problem}
      error={save.error}
      pending={save.isPending}
    >
      <TextInput
        label="Nome"
        required
        value={name}
        onChange={(e) => setName(e.currentTarget.value)}
      />
      <InstitutionSelect value={institutionId} onChange={setInstitutionId} />
      <NativeSelect
        label="Tipo"
        data={Object.entries(TYPE_LABELS).map(([value, label]) => ({
          value,
          label,
        }))}
        value={type}
        onChange={(e) => setType(e.currentTarget.value as Investment["type"])}
      />
      <AllocationPicker
        label="Donos"
        allowEmpty={false}
        value={effectiveOwners}
        onChange={setOwners}
      />
      <NativeSelect
        label="Meta de poupança"
        data={[
          { value: "", label: "(nenhuma)" },
          ...goals.map((g) => ({ value: g.id, label: g.name })),
        ]}
        value={goalId}
        onChange={(e) => setGoalId(e.currentTarget.value)}
      />
      <NativeSelect
        label="Conta de origem"
        data={[
          { value: "", label: "(nenhuma)" },
          ...accounts.map((a) => ({
            value: a.id,
            label: ownerLabel[a.id] ?? a.name,
          })),
        ]}
        value={accountId}
        onChange={(e) => setAccountId(e.currentTarget.value)}
      />
    </FormModal>
  );
}

export type InvestmentAction = "snapshot" | "movement" | "close";

/**
 * Snapshot / movement / close for one investment. The backend has no sub-resources, so each
 * action PUTs the full object with the new entry appended (R9.2: earlier snapshots are kept).
 */
export function InvestmentActionModal({
  investment,
  action,
  onClose,
}: {
  investment: Investment | null;
  action: InvestmentAction | null;
  onClose: () => void;
}) {
  const save = useSave("investments");
  const [date, setDate] = useState(todayIso());
  const [amount, setAmount] = useState("");
  const [movement, setMovement] = useState<"contribution" | "withdrawal">(
    "contribution",
  );
  const [problem, setProblem] = useState<string | null>(null);
  const opened = investment !== null && action !== null;

  const close = () => {
    setDate(todayIso());
    setAmount("");
    setMovement("contribution");
    setProblem(null);
    save.reset();
    onClose();
  };
  const submit = () => {
    if (!investment || !action) return;
    let p: string | null = DATE_RE.test(date.trim())
      ? null
      : "Data: escolha a data";
    const value = parseMoneyInput(amount);
    if (!p && action !== "close") {
      if (value === null) p = "Valor inválido";
      else if (action === "movement" && Number(value) <= 0)
        p = "O valor deve ser positivo";
      else if (action === "snapshot" && Number(value) < 0)
        p = "O saldo não pode ser negativo";
    }
    setProblem(p);
    if (p) return;
    const d = date.trim();
    const next: Investment =
      action === "snapshot"
        ? {
            ...investment,
            snapshots: [
              ...investment.snapshots,
              { date: d, balance: value ?? "" },
            ],
          }
        : action === "movement"
          ? {
              ...investment,
              movements: [
                ...investment.movements,
                { date: d, type: movement, amount: value ?? "", warnings: [] },
              ],
            }
          : { ...investment, closed_at: d };
    save.mutate(next, { onSuccess: close });
  };
  const titles: Record<InvestmentAction, string> = {
    snapshot: "Registrar saldo",
    movement: "Registrar aporte/resgate",
    close: "Encerrar investimento",
  };
  return (
    <FormModal
      title={action ? `${titles[action]} — ${investment?.name ?? ""}` : ""}
      opened={opened}
      onClose={close}
      onSubmit={submit}
      problem={problem}
      error={save.error}
      pending={save.isPending}
    >
      {action === "close" && (
        <Text size="sm">
          O investimento sai do total atual, mas continua no histórico e no
          gráfico de evolução.
        </Text>
      )}
      <DateField label="Data" required value={date} onChange={setDate} />
      {action === "movement" && (
        <Radio.Group
          label="Tipo de movimentação"
          value={movement}
          onChange={(v) => setMovement(v as "contribution" | "withdrawal")}
        >
          <Group mt={4}>
            <Radio value="contribution" label="Aporte" />
            <Radio value="withdrawal" label="Resgate" />
          </Group>
        </Radio.Group>
      )}
      {action !== "close" && (
        <TextInput
          label={action === "snapshot" ? "Saldo na data" : "Valor"}
          required
          placeholder="0,00"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.currentTarget.value)}
        />
      )}
    </FormModal>
  );
}

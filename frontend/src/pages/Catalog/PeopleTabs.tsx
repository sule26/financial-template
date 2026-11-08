/** Catalog tabs about people: users (income history) and split profiles (versions). */
import {
  Alert,
  Button,
  Checkbox,
  Group,
  SegmentedControl,
  Select,
  Stack,
  TagsInput,
  Text,
  TextInput,
} from "@mantine/core";
import { MonthField } from "../../components/ui/MonthField";
import { useList, useNames } from "../../api/hooks";
import type {
  IncomeEntry,
  IncomeSource,
  OneOffIncome,
  SplitMode,
  SplitProfile,
  SplitVersion,
  User,
} from "../../api/types";
import { formatMoney, parseMoneyInput, sumMoney } from "../../lib/format";
import { formatMonth } from "../../hooks/month";
import {
  checkMoney,
  CrudTab,
  EntryList,
  MONTH_RE,
  moneyToInput,
  type FormProps,
} from "./shared";

// ---------------------------------------------------------------- users (R1.5, R6.1)

export interface IncomeDraft {
  from_month: string;
  amount: string;
}
/** R14.4: one named income (a job, a freelance…) and its history. */
export interface SourceDraft {
  name: string;
  history: IncomeDraft[];
}
/** R14.4: income of a single month. */
export interface OneOffDraft {
  description: string;
  month: string;
  amount: string;
}
interface UserDraft {
  /** Id of the user being edited (null when new): excluded from "Repassar para". */
  id: string | null;
  name: string;
  aliases: string[];
  collector: string | null;
  sources: SourceDraft[];
  oneOff: OneOffDraft[];
  benefit: IncomeDraft[];
}

/** Legacy `income_history` becomes a source called "Renda"; saving moves it to `incomes`. */
export function toSourceDrafts(u: {
  income_history: IncomeEntry[];
  incomes?: IncomeSource[];
}): SourceDraft[] {
  const legacy: SourceDraft[] =
    u.income_history.length > 0
      ? [{ name: "Renda", history: toIncomeDraft(u.income_history) }]
      : [];
  return [
    ...legacy,
    ...(u.incomes ?? []).map((s) => ({
      name: s.name,
      history: toIncomeDraft(s.history),
    })),
  ];
}

export const toOneOffDrafts = (
  rows: OneOffIncome[] | undefined,
): OneOffDraft[] =>
  (rows ?? []).map((r) => ({
    description: r.description,
    month: r.month,
    amount: moneyToInput(r.amount),
  }));

export function checkSources(
  sources: SourceDraft[],
  oneOff: OneOffDraft[],
): string | null {
  for (const [i, s] of sources.entries()) {
    const label = s.name.trim() || `Renda ${i + 1}`;
    if (!s.name.trim())
      return `Renda ${i + 1}: dê um nome (ex.: Emprego, Freela)`;
    if (s.history.length === 0)
      return `${label}: informe o valor e o mês de início`;
    const bad = checkIncome(s.history, label);
    if (bad) return bad;
  }
  for (const [i, o] of oneOff.entries()) {
    const label = o.description.trim() || `Renda pontual ${i + 1}`;
    if (!MONTH_RE.test(o.month.trim())) return `${label}: escolha o mês`;
    const bad = checkMoney(o.amount, label, true);
    if (bad) return bad;
    if (!(Number(parseMoneyInput(o.amount)) > 0))
      return `${label}: valor precisa ser maior que zero`;
  }
  return null;
}

/** Table cell: latest amount of every income summed, plus how many incomes. */
export function currentIncomes(u: User): string {
  const sources = toSourceDrafts(u);
  if (sources.length === 1) return currentIncome(toIncome(sources[0]!.history));
  const latest = sources
    .map((s) =>
      [...s.history]
        .sort((a, b) => a.from_month.localeCompare(b.from_month))
        .pop(),
    )
    .filter((e): e is IncomeDraft => e !== undefined)
    .map((e) => parseMoneyInput(e.amount) ?? "0");
  if (latest.length === 0) return "—";
  const total = formatMoney(sumMoney(latest));
  return sources.length > 1 ? `${total} (${sources.length} rendas)` : total;
}

export const toIncomeDraft = (rows: IncomeEntry[]): IncomeDraft[] =>
  rows.map((r) => ({
    from_month: r.from_month,
    amount: moneyToInput(r.amount),
  }));
export const toIncome = (rows: IncomeDraft[]): IncomeEntry[] =>
  rows.map((r) => ({
    from_month: r.from_month.trim(),
    amount: parseMoneyInput(r.amount) ?? "",
  }));

export function checkIncome(rows: IncomeDraft[], label: string): string | null {
  for (const r of rows) {
    if (!MONTH_RE.test(r.from_month.trim())) return `${label}: escolha o mês`;
    const bad = checkMoney(r.amount, label, true);
    if (bad) return bad;
  }
  const months = rows.map((r) => r.from_month.trim());
  return new Set(months).size === months.length
    ? null
    : `${label}: meses repetidos`;
}

/** Latest income entry, for the table ("—" when the user has no income). */
export function currentIncome(rows: IncomeEntry[]): string {
  const last = [...rows]
    .sort((a, b) => a.from_month.localeCompare(b.from_month))
    .pop();
  return last
    ? `${formatMoney(last.amount)} desde ${formatMonth(last.from_month)}`
    : "—";
}

function IncomeEditor({
  label,
  rows,
  onChange,
}: {
  label: string;
  rows: IncomeDraft[];
  onChange: (rows: IncomeDraft[]) => void;
}) {
  return (
    <EntryList
      label={label}
      items={rows}
      onChange={onChange}
      make={() => ({ from_month: "", amount: "" })}
      row={(r, update, i) => (
        <>
          <MonthField
            label={`A partir de (${label} ${i + 1})`}
            clearable={false}
            value={r.from_month}
            onChange={(from_month) => update({ from_month })}
          />
          <TextInput
            label={`Valor (${label} ${i + 1})`}
            placeholder="0,00"
            inputMode="decimal"
            value={r.amount}
            onChange={(e) => update({ amount: e.currentTarget.value })}
          />
        </>
      )}
    />
  );
}

function SourcesEditor({
  sources,
  onChange,
}: {
  sources: SourceDraft[];
  onChange: (sources: SourceDraft[]) => void;
}) {
  const update = (i: number, patch: Partial<SourceDraft>) =>
    onChange(sources.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  return (
    <Stack gap="sm" role="group" aria-label="Rendas">
      <Text fw={600} size="sm">
        Rendas
      </Text>
      <Text size="xs" c="dimmed">
        Uma por fonte (ex.: dois empregos). Cada mudança de valor entra como
        nova vigência; meses anteriores não mudam. Para parar uma renda, crie
        uma vigência com valor 0.
      </Text>
      {sources.map((s, i) => (
        <Stack key={i} gap={6} className="et-subcard">
          <Group align="flex-end" wrap="nowrap">
            <TextInput
              label={`Nome da renda ${i + 1}`}
              placeholder="Ex.: Emprego, Freela, Aluguel recebido"
              value={s.name}
              onChange={(e) => update(i, { name: e.currentTarget.value })}
              style={{ flex: 1 }}
            />
            <Button
              variant="subtle"
              color="red"
              size="xs"
              onClick={() => onChange(sources.filter((_, j) => j !== i))}
            >
              Remover renda
            </Button>
          </Group>
          <IncomeEditor
            label={s.name.trim() || `Renda ${i + 1}`}
            rows={s.history}
            onChange={(history) => update(i, { history })}
          />
        </Stack>
      ))}
      <Button
        variant="light"
        size="xs"
        w="fit-content"
        onClick={() =>
          onChange([
            ...sources,
            { name: "", history: [{ from_month: "", amount: "" }] },
          ])
        }
      >
        + renda
      </Button>
    </Stack>
  );
}

function OneOffEditor({
  rows,
  onChange,
}: {
  rows: OneOffDraft[];
  onChange: (rows: OneOffDraft[]) => void;
}) {
  return (
    <Stack gap={6}>
      <Text fw={600} size="sm">
        Rendas pontuais (só um mês)
      </Text>
      <Text size="xs" c="dimmed">
        Dinheiro extra de um mês só (bônus, 13º, venda). Entra na renda e na
        sobra daquele mês, mas não muda a divisão proporcional à renda.
      </Text>
      <EntryList
        label="Renda pontual"
        items={rows}
        onChange={onChange}
        make={() => ({ description: "", month: "", amount: "" })}
        row={(r, update, i) => (
          <>
            <TextInput
              label={`Descrição (pontual ${i + 1})`}
              placeholder="Ex.: Bônus"
              value={r.description}
              onChange={(e) => update({ description: e.currentTarget.value })}
            />
            <MonthField
              label={`Mês (pontual ${i + 1})`}
              clearable={false}
              value={r.month}
              onChange={(month) => update({ month })}
            />
            <TextInput
              label={`Valor (pontual ${i + 1})`}
              placeholder="0,00"
              inputMode="decimal"
              value={r.amount}
              onChange={(e) => update({ amount: e.currentTarget.value })}
            />
          </>
        )}
      />
    </Stack>
  );
}

function UserForm({ draft, set }: FormProps<UserDraft>) {
  const users = useList("users").data ?? [];
  const others = users
    .filter((u) => u.id !== draft.id)
    .map((u) => ({ value: u.id, label: u.name }));
  return (
    <>
      <TextInput
        label="Nome"
        required
        value={draft.name}
        onChange={(e) => set({ name: e.currentTarget.value })}
      />
      <TagsInput
        label="Apelidos"
        description="Nomes que aparecem em faturas/extratos (Enter para adicionar)"
        value={draft.aliases}
        onChange={(aliases) => set({ aliases })}
      />
      <Select
        label="Repassar o que deve para"
        description="Opcional. Tudo o que esta pessoa deve passa a ser devido a quem você escolher (ex.: um filho cujos gastos a mãe paga)."
        placeholder="Ninguém (deve a quem pagou)"
        data={others}
        value={draft.collector}
        onChange={(collector) => set({ collector })}
        clearable
        searchable
      />
      <Text size="xs" c="dimmed">
        Renda é opcional.
      </Text>
      <SourcesEditor
        sources={draft.sources}
        onChange={(sources) => set({ sources })}
      />
      <OneOffEditor
        rows={draft.oneOff}
        onChange={(oneOff) => set({ oneOff })}
      />
      <Text size="xs" c="dimmed">
        VR/VA e auxílios (ex.: home office) ficam na aba Benefícios.
      </Text>
    </>
  );
}

export function UsersTab() {
  const names = useNames();
  return (
    <CrudTab<"users", UserDraft>
      resource="users"
      title="Usuários"
      noun="usuário"
      rowName={(u) => u.name}
      columns={[
        { header: "Nome", cell: (u: User) => u.name },
        { header: "Apelidos", cell: (u: User) => u.aliases.join(", ") || "—" },
        {
          header: "Renda atual",
          cell: (u: User) => currentIncomes(u),
        },
        {
          header: "Repassa para",
          cell: (u: User) =>
            u.collector_user_id
              ? (names.users[u.collector_user_id] ?? u.collector_user_id)
              : "—",
        },
      ]}
      blank={() => ({
        id: null,
        name: "",
        aliases: [],
        collector: null,
        sources: [],
        oneOff: [],
        benefit: [],
      })}
      fromItem={(u) => ({
        id: u.id,
        name: u.name,
        aliases: u.aliases,
        collector: u.collector_user_id ?? null,
        sources: toSourceDrafts(u),
        oneOff: toOneOffDrafts(u.one_off_incomes),
        benefit: toIncomeDraft(u.benefit_income_history),
      })}
      validate={(d) =>
        (!d.name.trim() ? "Nome: obrigatório" : null) ??
        checkSources(d.sources, d.oneOff)
      }
      toBody={(d) => ({
        name: d.name.trim(),
        aliases: d.aliases,
        collector_user_id: d.collector,
        // R14.4: every income is a named source; the legacy single history is moved there.
        income_history: [],
        incomes: d.sources.map((s) => ({
          name: s.name.trim(),
          history: toIncome(s.history),
        })),
        one_off_incomes: d.oneOff.map((o) => ({
          description: o.description.trim() || "Renda extra",
          month: o.month.trim(),
          amount: parseMoneyInput(o.amount) ?? "",
        })),
        // Legacy data, no longer edited here (replaced by Benefícios): kept as is.
        benefit_income_history: toIncome(d.benefit),
      })}
      form={UserForm}
    />
  );
}

// ---------------------------------------------------------------- split profiles (R6.10–R6.12, R13.12)

export const PROPORTIONAL_HINT =
  "calculado pela renda de cada membro no mês (usa a última versão em percentual se faltar renda)";

interface VersionDraft {
  from_month: string;
  mode: SplitMode;
  pcts: Record<string, string>;
}
interface SplitDraft {
  name: string;
  members: string[];
  versions: VersionDraft[];
}

/** Sum of a version's percentages over the members, as a decimal string ("100.00"). */
export function versionSum(v: VersionDraft, members: string[]): string {
  return sumMoney(members.map((m) => parseMoneyInput(v.pcts[m] ?? "") ?? "0"));
}

/** Mode of a stored version: its own, else the (legacy) profile mode. */
export const versionMode = (
  v: SplitVersion,
  profile: SplitProfile,
): SplitMode => v.mode ?? profile.mode ?? "fixed";

const byMonth = (a: { from_month: string }, b: { from_month: string }) =>
  a.from_month.localeCompare(b.from_month);

export function checkSplit(d: SplitDraft): string | null {
  if (!d.name.trim()) return "Nome: obrigatório";
  if (d.members.length === 0) return "Escolha ao menos um membro";
  if (d.versions.length === 0) return "Adicione ao menos uma versão";
  const months = new Set<string>();
  for (const v of d.versions) {
    if (!MONTH_RE.test(v.from_month.trim())) return "Versão: escolha o mês";
    if (months.has(v.from_month.trim())) return "Versões com o mesmo mês";
    months.add(v.from_month.trim());
    // Proportional versions have no percentages: they come from income.
    if (v.mode === "income_proportional") continue;
    for (const m of d.members)
      if (parseMoneyInput(v.pcts[m] || "0") === null)
        return "Percentual inválido";
    if (versionSum(v, d.members) !== "100.00")
      return `Versão ${v.from_month}: a soma precisa ser 100% (está ${versionSum(v, d.members)}%)`;
  }
  return null;
}

/** Request body for a split profile: mode per version, no shares on proportional versions. */
export function splitBody(d: SplitDraft): Partial<SplitProfile> {
  const history: SplitVersion[] = [...d.versions].sort(byMonth).map((v) => ({
    from_month: v.from_month.trim(),
    mode: v.mode,
    // A share must be > 0 (backend invariant): members at 0% are left out of this version.
    shares:
      v.mode === "income_proportional"
        ? []
        : d.members
            .map((m) => ({
              user_id: m,
              pct: parseMoneyInput(v.pcts[m] || "0") ?? "0.00",
            }))
            .filter((s) => s.pct !== "0.00"),
  }));
  return {
    name: d.name.trim(),
    members: d.members,
    // Legacy profile-level mode: mirrors the latest version for older readers.
    mode: history[history.length - 1]?.mode ?? "fixed",
    history,
  };
}

const MODE_OPTIONS = [
  { value: "fixed", label: "Percentual" },
  { value: "income_proportional", label: "Proporcional à renda" },
];

function SplitForm({ draft, set }: FormProps<SplitDraft>) {
  const users = useList("users").data ?? [];
  const names = useNames();
  return (
    <>
      <TextInput
        label="Nome"
        required
        value={draft.name}
        onChange={(e) => set({ name: e.currentTarget.value })}
      />
      <Checkbox.Group
        label="Membros"
        value={draft.members}
        onChange={(members) => set({ members })}
      >
        <Group mt={4}>
          {users.map((u) => (
            <Checkbox key={u.id} value={u.id} label={u.name} />
          ))}
        </Group>
      </Checkbox.Group>
      <Text size="xs" c="dimmed">
        Cada versão vale a partir de um mês e escolhe seu modo: percentual livre
        ou proporcional à renda. Meses anteriores não mudam.
      </Text>
      {draft.versions.some((v) => v.mode === "income_proportional") &&
        !draft.versions.some((v) => v.mode === "fixed") && (
          <Alert color="yellow" variant="light">
            Nenhuma versão em percentual: num mês em que faltar a renda de algum
            membro, não há percentuais para usar. Considere adicionar uma versão
            em percentual.
          </Alert>
        )}
      <EntryList
        label="Versões"
        addLabel="+ versão"
        items={draft.versions}
        onChange={(versions) => set({ versions })}
        make={(): VersionDraft => ({ from_month: "", mode: "fixed", pcts: {} })}
        row={(v, update, i) => {
          const sum = versionSum(v, draft.members);
          const proportional = v.mode === "income_proportional";
          return (
            <Stack gap={6} style={{ flex: 1 }}>
              <Group gap="xs" align="flex-end">
                <MonthField
                  label={`A partir de (versão ${i + 1})`}
                  clearable={false}
                  value={v.from_month}
                  onChange={(from_month) => update({ from_month })}
                />
                <Stack gap={4}>
                  <Text size="sm" fw={500} id={`split-mode-${i}`}>
                    Modo (versão {i + 1})
                  </Text>
                  <SegmentedControl
                    aria-labelledby={`split-mode-${i}`}
                    size="xs"
                    data={MODE_OPTIONS}
                    value={v.mode}
                    onChange={(mode) => update({ mode: mode as SplitMode })}
                  />
                </Stack>
              </Group>
              {proportional ? (
                <Text size="xs" c="dimmed">
                  Percentuais {PROPORTIONAL_HINT}.
                </Text>
              ) : (
                <>
                  <Group gap="xs" align="flex-end">
                    {draft.members.map((m) => (
                      <TextInput
                        key={m}
                        w={110}
                        label={`${names.users[m] ?? m} % (versão ${i + 1})`}
                        inputMode="decimal"
                        value={v.pcts[m] ?? ""}
                        onChange={(e) =>
                          update({
                            pcts: { ...v.pcts, [m]: e.currentTarget.value },
                          })
                        }
                      />
                    ))}
                  </Group>
                  <Text
                    size="xs"
                    c={sum === "100.00" ? "dimmed" : "red"}
                    role="status"
                  >
                    soma: {sum}%{sum === "100.00" ? "" : " (precisa ser 100%)"}
                  </Text>
                </>
              )}
            </Stack>
          );
        }}
      />
    </>
  );
}

/** "jan/2026: Eu 60% · Ana 40%" or "jan/2026: proporcional à renda". */
export function versionLabel(
  v: SplitVersion,
  profile: SplitProfile,
  userName: (id: string) => string,
): string {
  const body =
    versionMode(v, profile) === "income_proportional"
      ? "proporcional à renda"
      : v.shares
          .map((sh) => `${userName(sh.user_id)} ${Number(sh.pct)}%`)
          .join(" · ");
  return `${formatMonth(v.from_month)}: ${body}`;
}

export function SplitsTab() {
  const names = useNames();
  const firstUsers = useList("users").data ?? [];
  const userName = (id: string) => names.users[id] ?? id;
  const latest = (s: SplitProfile) => [...s.history].sort(byMonth).pop();
  return (
    <CrudTab<"split-profiles", SplitDraft>
      resource="split-profiles"
      title="Padrões de divisão"
      noun="padrão de divisão"
      rowName={(s) => s.name}
      columns={[
        { header: "Nome", cell: (s: SplitProfile) => s.name },
        {
          header: "Membros",
          cell: (s: SplitProfile) => s.members.map(userName).join(", "),
        },
        {
          header: "Modo atual",
          cell: (s: SplitProfile) => {
            const last = latest(s);
            const mode = last ? versionMode(last, s) : s.mode;
            return mode === "income_proportional"
              ? "Proporcional à renda"
              : "Percentual";
          },
        },
        {
          header: "Versão vigente",
          cell: (s: SplitProfile) => {
            const last = latest(s);
            return last ? versionLabel(last, s, userName) : "—";
          },
        },
      ]}
      blank={() => ({
        name: "",
        members: firstUsers.slice(0, 2).map((u) => u.id),
        versions: [{ from_month: "", mode: "fixed", pcts: {} }],
      })}
      fromItem={(s) => ({
        name: s.name,
        members: s.members,
        versions: s.history.map((v) => ({
          from_month: v.from_month,
          // Legacy data: a proportional profile without per-version mode loads as proportional.
          mode: versionMode(v, s),
          pcts: Object.fromEntries(
            v.shares.map((sh) => [sh.user_id, moneyToInput(sh.pct)]),
          ),
        })),
      })}
      validate={checkSplit}
      toBody={splitBody}
      form={SplitForm}
    />
  );
}

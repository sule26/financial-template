/**
 * Building blocks of the guided card/account forms (R14.5) and the several-responsibles field
 * (R14.1): sections with help text, the bank picker, the inbox folder hint and the live summary.
 */
import { Alert, Code, NativeSelect, Stack, Switch, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { useGet, useNames } from "../../api/hooks";
import { isSplitRef, type Allocation } from "../../api/types";
import { AllocationPicker } from "../../components/AllocationPicker";
import { supportedBanks } from "../Profiles/banks";
import type { ProfilesList } from "../Profiles/types";
import { describeAllocation } from "./shared";

/** A titled block of a form with a one-line explanation. */
export function FormSection({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Stack gap="xs" className="et-subcard" role="group" aria-label={title}>
      <Text fw={650} size="sm">
        {title}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
      {children}
    </Stack>
  );
}

/** Same rule as the backend folder_name(): the name, all lowercase (R13.2). */
export function folderName(name: string): string {
  const cleaned = name
    .replace(/[/\\\0]/g, " ")
    .trim()
    .toLocaleLowerCase("pt-BR");
  return cleaned.replace(/\s+/g, " ") || "sem-nome";
}

/** Where the operator drops the PDFs of this card/account. */
export function FolderHint({
  kind,
  name,
}: {
  kind: "faturas" | "extratos";
  name: string;
}) {
  return (
    <Text size="xs" c="dimmed">
      Coloque os {kind === "faturas" ? "PDFs das faturas" : "extratos"} em{" "}
      <Code>{`inbox/${kind}/${folderName(name)}/`}</Code>. A pasta é criada ao
      salvar; arquivos nela são deste {kind === "faturas" ? "cartão" : "conta"}{" "}
      automaticamente.
    </Text>
  );
}

/** Bank (profile) picker from the supported banks, instead of a free-text id (R14.5). */
export function BankSelect({
  kind,
  value,
  onChange,
}: {
  kind: "fatura" | "extrato";
  value: string;
  onChange: (value: string) => void;
}) {
  const list = useGet<ProfilesList>(["profiles"], "/api/profiles");
  const banks = list.data
    ? supportedBanks(list.data).filter(
        (b) => b.kind === null || b.kind === kind,
      )
    : [];
  const known = banks.some((b) => b.id === value);
  const data = [
    { value: "", label: "Detectar automaticamente" },
    ...banks.map((b) => ({ value: b.id, label: b.name })),
    ...(value && !known
      ? [{ value, label: `${value} (não encontrado em Perfis)` }]
      : []),
  ];
  return (
    <NativeSelect
      label="Banco (leitura do PDF)"
      description="Qual leitor usar para o PDF. Na dúvida, deixe em detectar automaticamente; bancos novos se cadastram em Perfis de banco."
      data={data}
      value={value}
      onChange={(e) => onChange(e.currentTarget.value)}
    />
  );
}

/** Main responsible implied by a fixed list: largest share (ties: first). */
export function mainOf(list: Allocation): string | null {
  if (isSplitRef(list) || list.length === 0) return null;
  let best = list[0]!;
  for (const s of list) if (Number(s.pct) > Number(best.pct)) best = s;
  return best.user_id;
}

/**
 * R14.1: "Mais de uma pessoa paga o banco". Off: only the responsible pays (null). On: the
 * percentages of each payer; the main responsible follows the largest share of a fixed list.
 */
export function ResponsiblesField({
  value,
  principal,
  onChange,
}: {
  value: Allocation | null;
  principal: string | null;
  onChange: (value: Allocation | null, principal: string | null) => void;
}) {
  const names = useNames();
  const others = Object.keys(names.users).filter((u) => u !== principal);
  const on = value !== null;
  const start = (): Allocation =>
    principal && others[0]
      ? [
          { user_id: principal, pct: "50.00" },
          { user_id: others[0], pct: "50.00" },
        ]
      : [
          {
            user_id: principal ?? Object.keys(names.users)[0] ?? "",
            pct: "100.00",
          },
        ];
  const change = (next: Allocation | null) => {
    if (next === null) return onChange(null, principal);
    const main = mainOf(next);
    onChange(next, main ?? principal);
  };
  return (
    <Stack gap={6}>
      <Switch
        label="Mais de uma pessoa paga o banco"
        description="Ex.: vocês dividem o pagamento da fatura 60/40. Quem consumiu cada compra continua vindo de “Quem usa”; aqui é só quem paga o banco."
        checked={on}
        onChange={(e) => change(e.currentTarget.checked ? start() : null)}
      />
      {on && (
        <>
          <AllocationPicker
            label="Quem paga o banco (%)"
            allowEmpty={false}
            value={value}
            onChange={change}
          />
          <Text size="xs" c="dimmed">
            O responsável principal (quem recebe os centavos de arredondamento e
            as sugestões de acerto) é{" "}
            <b>{principal ? (names.users[principal] ?? principal) : "—"}</b>
            {isSplitRef(value)
              ? "; escolha-o em “Responsável”."
              : ", o de maior percentual."}
          </Text>
        </>
      )}
    </Stack>
  );
}

/** Live "who uses / who pays" of what is being edited, with where it comes from. */
export function OwnershipSummary({
  owners,
  ownersFrom,
  responsible,
  responsibles,
  responsibleFrom,
}: {
  owners: Allocation | null;
  ownersFrom: string | null;
  responsible: string | null;
  responsibles: Allocation | null;
  responsibleFrom: string | null;
}) {
  const names = useNames();
  const pays = responsibles
    ? describeAllocation(responsibles, names)
    : responsible
      ? (names.users[responsible] ?? responsible)
      : null;
  const missing = !owners || !pays;
  return (
    <Alert
      color={missing ? "red" : "blue"}
      variant="light"
      title="Resumo"
      aria-label="Resumo de quem usa e quem paga"
    >
      <Text size="sm">
        Quem usa:{" "}
        <b>{owners ? describeAllocation(owners, names) : "não definido"}</b>
        {ownersFrom && ` (${ownersFrom})`}
      </Text>
      <Text size="sm">
        Paga o banco: <b>{pays ?? "não definido"}</b>
        {responsibleFrom && ` (${responsibleFrom})`}
      </Text>
      {missing && (
        <Text size="xs" mt={4}>
          Defina aqui ou vincule a uma conta que já tenha donos e responsável.
        </Text>
      )}
    </Alert>
  );
}

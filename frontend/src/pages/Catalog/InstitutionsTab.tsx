/** Catalog tab for investment institutions that are not registered accounts (R13.15). */
import { NativeSelect, Text, TextInput } from "@mantine/core";
import type { Institution, InstitutionType } from "../../api/types";
import { CrudTab, type FormProps } from "./shared";

export const INSTITUTION_TYPE_LABELS: Record<InstitutionType, string> = {
  broker: "Corretora",
  exchange: "Exchange",
  pension: "Previdência",
  bank: "Banco",
  other: "Outra",
};

export const INSTITUTION_TYPE_OPTIONS = (
  Object.keys(INSTITUTION_TYPE_LABELS) as InstitutionType[]
).map((value) => ({ value, label: INSTITUTION_TYPE_LABELS[value] }));

export interface InstitutionDraft {
  name: string;
  type: InstitutionType;
}

export function checkInstitution(d: InstitutionDraft): string | null {
  return d.name.trim() ? null : "Nome: obrigatório";
}

/** Name + type fields, shared by the catalog modal and the inline form in Investimentos. */
export function InstitutionFields({
  draft,
  set,
  labelSuffix = "",
}: FormProps<InstitutionDraft> & { labelSuffix?: string }) {
  return (
    <>
      <TextInput
        label={`Nome${labelSuffix}`}
        placeholder="Ex.: XP, Binance, Brasilprev"
        required
        value={draft.name}
        onChange={(e) => set({ name: e.currentTarget.value })}
      />
      <NativeSelect
        label={`Tipo${labelSuffix}`}
        data={INSTITUTION_TYPE_OPTIONS}
        value={draft.type}
        onChange={(e) =>
          set({ type: e.currentTarget.value as InstitutionType })
        }
      />
    </>
  );
}

function InstitutionForm(props: FormProps<InstitutionDraft>) {
  return <InstitutionFields {...props} />;
}

export function InstitutionsTab() {
  return (
    <CrudTab<"institutions", InstitutionDraft>
      resource="institutions"
      title="Instituições"
      noun="instituição"
      emptyText="Nenhuma instituição cadastrada."
      intro={
        <Text size="sm" c="dimmed">
          Onde ficam investimentos que não estão numa conta cadastrada:
          corretoras, exchanges, previdência. Contas cadastradas já aparecem
          como opção em Investimentos.
        </Text>
      }
      rowName={(i) => i.name}
      columns={[
        { header: "Nome", cell: (i: Institution) => i.name },
        {
          header: "Tipo",
          cell: (i: Institution) => INSTITUTION_TYPE_LABELS[i.type] ?? i.type,
        },
      ]}
      blank={() => ({ name: "", type: "broker" })}
      fromItem={(i) => ({ name: i.name, type: i.type })}
      validate={checkInstitution}
      toBody={(d) => ({ name: d.name.trim(), type: d.type })}
      form={InstitutionForm}
    />
  );
}

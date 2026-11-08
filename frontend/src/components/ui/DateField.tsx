import { DatePickerInput, type DatePickerInputProps } from "@mantine/dates";
import { IconCalendar } from "@tabler/icons-react";
import { dateToIso, isoToDate } from "../../lib/dates";
import { PICKER_ARIA_LABELS } from "./pickerLabels";

export interface DateFieldProps
  extends Omit<
    DatePickerInputProps<"default">,
    "value" | "onChange" | "label" | "type" | "defaultValue"
  > {
  /** Visible label (required: every field is labelled, docs/12). */
  label: string;
  /** "YYYY-MM-DD" or "" when empty. */
  value: string;
  onChange: (date: string) => void;
}

/**
 * Date picker (R13.13): shows "05/10/2026", reads and writes the API's "YYYY-MM-DD" string. Optional
 * fields get a clear button.
 */
export function DateField({
  label,
  value,
  onChange,
  required,
  clearable,
  ...rest
}: DateFieldProps) {
  return (
    <DatePickerInput
      label={label}
      required={required}
      clearable={clearable ?? !required}
      clearButtonProps={{ "aria-label": `Limpar ${label}` }}
      valueFormat="DD/MM/YYYY"
      placeholder="Escolha a data"
      leftSection={<IconCalendar size={16} aria-hidden="true" />}
      leftSectionPointerEvents="none"
      ariaLabels={PICKER_ARIA_LABELS}
      popoverProps={{ withinPortal: true }}
      {...rest}
      value={isoToDate(value)}
      onChange={(d) => onChange(dateToIso(d))}
    />
  );
}

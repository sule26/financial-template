import { MonthPickerInput, type MonthPickerInputProps } from "@mantine/dates";
import { IconCalendarMonth } from "@tabler/icons-react";
import { dateToMonth, monthToDate } from "../../lib/dates";
import { PICKER_ARIA_LABELS } from "./pickerLabels";

export interface MonthFieldProps
  extends Omit<
    MonthPickerInputProps,
    "value" | "onChange" | "label" | "type" | "defaultValue"
  > {
  /** Visible label (required: every field is labelled, docs/12). */
  label: string;
  /** "YYYY-MM" or "" when empty. */
  value: string;
  onChange: (month: string) => void;
}

/**
 * Month picker (R13.13): shows "out/2026", reads and writes the API's "YYYY-MM" string. Optional
 * fields get a clear button.
 */
export function MonthField({
  label,
  value,
  onChange,
  required,
  clearable,
  ...rest
}: MonthFieldProps) {
  return (
    <MonthPickerInput
      label={label}
      required={required}
      clearable={clearable ?? !required}
      clearButtonProps={{ "aria-label": `Limpar ${label}` }}
      valueFormat="MMM/YYYY"
      placeholder="Escolha o mês"
      leftSection={<IconCalendarMonth size={16} aria-hidden="true" />}
      leftSectionPointerEvents="none"
      ariaLabels={PICKER_ARIA_LABELS}
      popoverProps={{ withinPortal: true }}
      {...rest}
      value={monthToDate(value)}
      onChange={(d) => onChange(dateToMonth(d))}
    />
  );
}

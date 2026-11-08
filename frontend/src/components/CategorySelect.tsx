import { Select, Stack, Text, type SelectProps } from "@mantine/core";
import { useList } from "../api/hooks";

/**
 * Category picker: only categories from categories.json; required by default (R1.11).
 * R14.24: each option and the chosen one show what goes in the category.
 */
export function CategorySelect(
  props: Omit<SelectProps, "data"> & { required?: boolean },
) {
  const { data } = useList("categories");
  const hints = Object.fromEntries(
    (data ?? []).map((c) => [c.id, c.description ?? ""]),
  );
  const options = (data ?? []).map((c) => ({ value: c.id, label: c.name }));
  const chosen = typeof props.value === "string" ? hints[props.value] : "";
  return (
    <Select
      label="Categoria"
      placeholder="Escolha uma categoria"
      searchable
      required={props.required ?? true}
      description={props.description ?? (chosen || undefined)}
      renderOption={({ option }) => (
        <Stack gap={0}>
          <Text size="sm">{option.label}</Text>
          {hints[option.value] && (
            <Text size="xs" c="dimmed">
              {hints[option.value]}
            </Text>
          )}
        </Stack>
      )}
      {...props}
      data={options}
    />
  );
}

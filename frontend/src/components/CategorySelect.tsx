import { Select, type SelectProps } from "@mantine/core";
import { useList } from "../api/hooks";

/** Category picker: only categories from categories.json; required by default (R1.11). */
export function CategorySelect(
  props: Omit<SelectProps, "data"> & { required?: boolean },
) {
  const { data } = useList("categories");
  const options = (data ?? []).map((c) => ({ value: c.id, label: c.name }));
  return (
    <Select
      label="Categoria"
      placeholder="Escolha uma categoria"
      searchable
      required={props.required ?? true}
      {...props}
      data={options}
    />
  );
}

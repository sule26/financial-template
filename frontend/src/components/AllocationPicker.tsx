import { useId } from "react";
import {
  Button,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Text,
} from "@mantine/core";
import { useNames } from "../api/hooks";
import { isSplitRef, type Allocation, type Share } from "../api/types";

interface AllocationPickerProps {
  value: Allocation | null;
  onChange: (value: Allocation | null) => void;
  label?: string;
  allowEmpty?: boolean; // "padrão" = no explicit allocation (precedence decides)
}

/** Reusable allocation selector: split profile, "só eu", "100% para…", custom (docs/08). */
export function AllocationPicker({
  value,
  onChange,
  label = "Divisão",
  allowEmpty = true,
}: AllocationPickerProps) {
  const names = useNames();
  const labelId = useId();
  const userOptions = Object.entries(names.users).map(([id, name]) => ({
    value: id,
    label: name,
  }));
  const splitOptions = Object.entries(names.splits).map(([id, name]) => ({
    value: id,
    label: name,
  }));
  const mode =
    value === null
      ? "default"
      : isSplitRef(value)
        ? "split"
        : value.length === 1
          ? "single"
          : "custom";

  const setMode = (m: string) => {
    if (m === "default") onChange(null);
    else if (m === "split")
      onChange({ split_id: splitOptions[0]?.value ?? "" });
    else if (m === "single")
      onChange([{ user_id: userOptions[0]?.value ?? "", pct: "100.00" }]);
    else {
      const [a, b] = userOptions;
      onChange(
        a && b
          ? [
              { user_id: a.value, pct: "50.00" },
              { user_id: b.value, pct: "50.00" },
            ]
          : [{ user_id: a?.value ?? "", pct: "100.00" }],
      );
    }
  };

  const shares = Array.isArray(value) ? value : [];
  const total = shares.reduce(
    (acc, s) => acc + Math.round(Number(s.pct) * 100),
    0,
  );
  const setShare = (i: number, patch: Partial<Share>) =>
    onChange(shares.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  const modes = [
    ...(allowEmpty ? [{ value: "default", label: "Padrão" }] : []),
    { value: "split", label: "Padrão de divisão" },
    { value: "single", label: "100% para…" },
    { value: "custom", label: "Personalizada" },
  ];

  return (
    <Stack gap={6}>
      <Text size="sm" fw={500} id={labelId}>
        {label}
      </Text>
      <SegmentedControl
        size="xs"
        data={modes}
        value={mode}
        onChange={setMode}
        aria-labelledby={labelId}
      />
      {mode === "split" && isSplitRef(value) && (
        <Select
          aria-label="Padrão de divisão"
          data={splitOptions}
          value={value.split_id}
          onChange={(v) => v && onChange({ split_id: v })}
        />
      )}
      {mode === "single" && shares[0] && (
        <Select
          aria-label="Pessoa"
          data={userOptions}
          value={shares[0].user_id}
          onChange={(v) => v && onChange([{ user_id: v, pct: "100.00" }])}
        />
      )}
      {mode === "custom" && (
        <Stack gap={4}>
          {shares.map((s, i) => (
            <Group key={i} gap="xs" wrap="nowrap">
              <Select
                aria-label={`Pessoa ${i + 1}`}
                data={userOptions}
                value={s.user_id}
                onChange={(v) => v && setShare(i, { user_id: v })}
                style={{ flex: 1 }}
              />
              <NumberInput
                aria-label={`Percentual ${i + 1}`}
                value={Number(s.pct)}
                onChange={(v) =>
                  setShare(i, { pct: Number(v || 0).toFixed(2) })
                }
                min={0}
                max={100}
                decimalScale={2}
                suffix="%"
                w={110}
              />
              <Button
                variant="subtle"
                color="red"
                size="xs"
                aria-label={`Remover pessoa ${i + 1}`}
                onClick={() => onChange(shares.filter((_, j) => j !== i))}
                disabled={shares.length <= 1}
              >
                ✕
              </Button>
            </Group>
          ))}
          <Group justify="space-between">
            <Button
              variant="light"
              size="xs"
              onClick={() =>
                onChange([
                  ...shares,
                  { user_id: userOptions[0]?.value ?? "", pct: "0.00" },
                ])
              }
            >
              + pessoa
            </Button>
            <Text
              size="xs"
              c={total === 10000 ? "dimmed" : "red"}
              role="status"
            >
              soma: {(total / 100).toFixed(2)}%{" "}
              {total === 10000 ? "" : "(precisa ser 100%)"}
            </Text>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}

/** True when the allocation is valid to submit (fixed shares must sum exactly 100). */
export function allocationValid(value: Allocation | null): boolean {
  if (value === null || isSplitRef(value))
    return value === null || value.split_id !== "";
  const total = value.reduce(
    (acc, s) => acc + Math.round(Number(s.pct) * 100),
    0,
  );
  const users = new Set(value.map((s) => s.user_id));
  return (
    total === 10000 &&
    users.size === value.length &&
    value.every((s) => s.user_id)
  );
}

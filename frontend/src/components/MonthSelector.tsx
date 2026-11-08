import {
  ActionIcon,
  Button,
  Group,
  Popover,
  SimpleGrid,
  Text,
  UnstyledButton,
} from "@mantine/core";
import {
  IconCalendarMonth,
  IconChevronLeft,
  IconChevronRight,
} from "@tabler/icons-react";
import { useState, type KeyboardEvent } from "react";
import { formatMonth, MONTH_NAMES, useMonth, type Month } from "../hooks/month";

const MONTH_FULL_NAMES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

const yearOf = (month: Month): number => Number(month.slice(0, 4));
const monthKey = (year: number, index: number): Month =>
  `${year}-${String(index + 1).padStart(2, "0")}`;

/**
 * Global month selector (R1.13): always opens on the current month. Arrows step one month,
 * clicking the month opens a year/month grid to jump directly; ←/→ and Home work while the
 * selector has focus.
 */
export function MonthSelector() {
  const { selected, current, setSelected, shift, reset, isCurrent } =
    useMonth();
  const [opened, setOpened] = useState(false);
  const [year, setYear] = useState(() => yearOf(selected));

  const toggle = () => {
    if (!opened) setYear(yearOf(selected));
    setOpened((o) => !o);
  };

  const choose = (month: Month) => {
    setSelected(month);
    setOpened(false);
  };

  // Only keys typed on the inline control (not inside the portaled grid) move the month.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.target as Node)) return;
    if (e.key === "ArrowLeft") shift(-1);
    else if (e.key === "ArrowRight") shift(1);
    else if (e.key === "Home") reset();
    else return;
    e.preventDefault();
  };

  return (
    <Group gap={6} wrap="nowrap">
      <Popover
        opened={opened}
        onChange={setOpened}
        position="bottom"
        shadow="md"
        radius="lg"
        withArrow
        trapFocus
        returnFocus
      >
        <Group
          gap={2}
          wrap="nowrap"
          className="et-month"
          role="group"
          aria-label="Mês"
          onKeyDown={onKeyDown}
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            radius="xl"
            aria-label="Mês anterior"
            onClick={() => shift(-1)}
          >
            <IconChevronLeft size={18} stroke={2} aria-hidden="true" />
          </ActionIcon>
          <Popover.Target>
            <UnstyledButton
              className="et-month__label et-month__trigger"
              aria-label={`Escolher mês (${formatMonth(selected)})`}
              aria-haspopup="dialog"
              aria-expanded={opened}
              onClick={toggle}
            >
              <Group gap={6} wrap="nowrap" aria-live="polite">
                <IconCalendarMonth
                  size={16}
                  stroke={1.8}
                  aria-hidden="true"
                  className="et-month__icon"
                />
                <Text
                  key={selected}
                  fw={700}
                  data-testid="selected-month"
                  className="et-num et-fade-in"
                  component="span"
                >
                  {formatMonth(selected)}
                </Text>
              </Group>
            </UnstyledButton>
          </Popover.Target>
          <ActionIcon
            variant="subtle"
            color="gray"
            radius="xl"
            aria-label="Próximo mês"
            onClick={() => shift(1)}
          >
            <IconChevronRight size={18} stroke={2} aria-hidden="true" />
          </ActionIcon>
        </Group>
        <Popover.Dropdown className="et-month-picker">
          <Group justify="space-between" mb="xs" wrap="nowrap">
            <ActionIcon
              variant="subtle"
              color="gray"
              radius="xl"
              aria-label="Ano anterior"
              onClick={() => setYear((y) => y - 1)}
            >
              <IconChevronLeft size={16} stroke={2} aria-hidden="true" />
            </ActionIcon>
            <Text
              fw={700}
              className="et-num et-month-picker__year"
              data-testid="picker-year"
            >
              {year}
            </Text>
            <ActionIcon
              variant="subtle"
              color="gray"
              radius="xl"
              aria-label="Próximo ano"
              onClick={() => setYear((y) => y + 1)}
            >
              <IconChevronRight size={16} stroke={2} aria-hidden="true" />
            </ActionIcon>
          </Group>
          <SimpleGrid
            cols={4}
            spacing={6}
            verticalSpacing={6}
            role="group"
            aria-label={`Meses de ${year}`}
          >
            {MONTH_NAMES.map((short, i) => {
              const key = monthKey(year, i);
              const isSelected = key === selected;
              const isToday = key === current;
              return (
                <UnstyledButton
                  key={key}
                  className="et-month-picker__cell"
                  data-selected={isSelected || undefined}
                  data-current={isToday || undefined}
                  aria-pressed={isSelected}
                  aria-current={isToday ? "date" : undefined}
                  aria-label={`${MONTH_FULL_NAMES[i]} de ${year}`}
                  onClick={() => choose(key)}
                >
                  {short}
                </UnstyledButton>
              );
            })}
          </SimpleGrid>
          {!isCurrent && (
            <Button
              mt="xs"
              fullWidth
              size="compact-xs"
              variant="subtle"
              onClick={() => choose(current)}
            >
              ir para {formatMonth(current)}
            </Button>
          )}
        </Popover.Dropdown>
      </Popover>
      {!isCurrent && (
        <Button
          size="compact-xs"
          variant="light"
          radius="xl"
          onClick={reset}
          className="et-pop-in"
        >
          voltar ao mês atual
        </Button>
      )}
    </Group>
  );
}

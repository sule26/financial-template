import {
  Center,
  SegmentedControl,
  useMantineColorScheme,
  type MantineColorScheme,
} from "@mantine/core";
import { IconDeviceDesktop, IconMoon, IconSun } from "@tabler/icons-react";
import type { ReactNode } from "react";

function option(value: MantineColorScheme, label: string, icon: ReactNode) {
  return {
    value,
    label: (
      <Center style={{ gap: 6 }} className="et-theme__option">
        {icon}
        <span className="et-theme__text">{label}</span>
      </Center>
    ),
  };
}

/** Light / dark / system theme (R1.14). Mantine persists the choice in localStorage. */
export function ThemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  return (
    <SegmentedControl
      size="xs"
      aria-label="Tema"
      className="et-theme"
      value={colorScheme}
      onChange={(v) => setColorScheme(v as MantineColorScheme)}
      data={[
        option(
          "light",
          "Claro",
          <IconSun size={14} stroke={2} aria-hidden="true" />,
        ),
        option(
          "dark",
          "Escuro",
          <IconMoon size={14} stroke={2} aria-hidden="true" />,
        ),
        option(
          "auto",
          "Sistema",
          <IconDeviceDesktop size={14} stroke={2} aria-hidden="true" />,
        ),
      ]}
    />
  );
}

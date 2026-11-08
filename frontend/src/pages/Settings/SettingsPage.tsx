/** Configurações (R13.10): theme and accent colour, both remembered in this browser. */
import { Group, Radio, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconPalette, IconSettings, IconSunMoon } from "@tabler/icons-react";
import { ThemeToggle } from "../../components/ThemeToggle";
import { PageHeader, Panel } from "../../components/ui";
import { useAccent } from "../../hooks/accent";
import {
  ACCENTS,
  DEFAULT_ACCENT,
  isAccentId,
  type Accent,
} from "../../lib/accents";

function Swatch({ accent }: { accent: Accent }) {
  const p = accent.palette;
  // Light and dark accent side by side: what the colour looks like in each theme.
  return (
    <span className="et-swatch" aria-hidden="true">
      <span style={{ background: p[7] }} />
      <span style={{ background: p[4] }} />
    </span>
  );
}

export function SettingsPage() {
  const { accent, setAccent } = useAccent();
  return (
    <Stack gap="lg">
      <PageHeader
        eyebrow="Configuração"
        title="Configurações"
        icon={<IconSettings size={22} stroke={1.7} />}
        subtitle="Aparência da app. As escolhas ficam guardadas neste navegador."
      />
      <Panel
        title="Tema"
        icon={<IconSunMoon size={18} stroke={1.8} />}
        description="Claro, escuro ou o mesmo do sistema operacional."
        interactive={false}
      >
        <ThemeToggle />
      </Panel>
      <Panel
        title="Cor de destaque"
        icon={<IconPalette size={18} stroke={1.8} />}
        description="Cor dos botões, do menu e dos realces. Todas mantêm o texto legível nos dois temas."
        interactive={false}
      >
        <Radio.Group
          value={accent}
          onChange={(v) => {
            if (isAccentId(v)) setAccent(v);
          }}
          aria-label="Cor de destaque"
        >
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="sm">
            {ACCENTS.map((a) => (
              <Radio.Card
                key={a.id}
                value={a.id}
                radius="md"
                p="sm"
                className="et-accent-card"
              >
                <Group gap="sm" wrap="nowrap">
                  <Radio.Indicator />
                  <Swatch accent={a} />
                  <div>
                    <Text fw={600} size="sm">
                      {a.name}
                    </Text>
                    {a.id === DEFAULT_ACCENT && (
                      <Text size="xs" c="dimmed">
                        padrão
                      </Text>
                    )}
                  </div>
                </Group>
              </Radio.Card>
            ))}
          </SimpleGrid>
        </Radio.Group>
      </Panel>
    </Stack>
  );
}

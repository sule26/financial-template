/** Configurações (R13.10): theme and accent colour, both remembered in this browser. */
import {
  Group,
  MultiSelect,
  Radio,
  SimpleGrid,
  Stack,
  Text,
} from "@mantine/core";
import { LANGS, useLang, type Lang } from "../../i18n/i18n";
import {
  IconLanguage,
  IconPalette,
  IconSettings,
  IconSunMoon,
  IconUser,
} from "@tabler/icons-react";
import { useState } from "react";
import { useList } from "../../api/hooks";
import {
  knownPeople,
  readDefaultPeople,
  saveDefaultPeople,
} from "../../hooks/defaultPeople";
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

/** R14.25: who Resumo, Projeção and A receber show by default. */
function DefaultPeople() {
  const users = useList("users");
  const [value, setValue] = useState<string[]>(readDefaultPeople);
  return (
    <MultiSelect
      label="Mostrar por padrão"
      description="Resumo e Projeção abrem com a parte dessas pessoas (e a renda delas); A receber abre como a primeira. Vazio = todos (a casa)."
      placeholder={value.length ? undefined : "Todos"}
      data={(users.data ?? []).map((u) => ({ value: u.id, label: u.name }))}
      value={knownPeople(value, users.data)}
      onChange={(ids) => {
        setValue(ids);
        saveDefaultPeople(ids);
      }}
      clearable
      maw={420}
    />
  );
}

/** R14.13: pt-BR / en, remembered in this browser. */
function LanguageChoice() {
  const { lang, setLang } = useLang();
  return (
    <Radio.Group
      value={lang}
      onChange={(v) => setLang(v as Lang)}
      aria-label="Idioma"
    >
      <Group mt={4}>
        {LANGS.map((l) => (
          <Radio key={l.id} value={l.id} label={l.name} />
        ))}
      </Group>
    </Radio.Group>
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
        title="Idioma"
        icon={<IconLanguage size={18} stroke={1.8} />}
        description="Escolha o idioma da interface. Valores continuam em reais (R$)."
        interactive={false}
      >
        <LanguageChoice />
      </Panel>
      <Panel
        title="Pessoa padrão"
        icon={<IconUser size={18} stroke={1.8} />}
        description="Para cada tela já abrir voltada para você (ou para você e sua esposa)."
        interactive={false}
      >
        <DefaultPeople />
      </Panel>
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

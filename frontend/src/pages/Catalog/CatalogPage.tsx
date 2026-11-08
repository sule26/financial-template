/** Cadastros: one tab per catalog resource; the active tab lives in ?tab= (shareable). */
import { Stack, Tabs } from "@mantine/core";
import {
  IconArrowsSplit,
  IconBuildingBank,
  IconBuildingCommunity,
  IconCalendarRepeat,
  IconCategory,
  IconCreditCard,
  IconGift,
  IconRepeat,
  IconRoute,
  IconTargetArrow,
  IconUsers,
  type Icon,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { PageHeader } from "../../components/ui";
import { useSearchParams } from "react-router-dom";
import { BenefitsTab } from "./BenefitsTab";
import { InstitutionsTab } from "./InstitutionsTab";
import { AccountsTab, CardsTab } from "./MoneyTabs";
import { SplitsTab, UsersTab } from "./PeopleTabs";
import {
  CategoriesTab,
  GoalsTab,
  RecurringTab,
  RulesTab,
  SubscriptionsTab,
} from "./SpendingTabs";

export const CATALOG_TABS: {
  value: string;
  label: string;
  icon: Icon;
  panel: ComponentType;
}[] = [
  { value: "usuarios", label: "Usuários", icon: IconUsers, panel: UsersTab },
  {
    value: "divisoes",
    label: "Padrões de divisão",
    icon: IconArrowsSplit,
    panel: SplitsTab,
  },
  {
    value: "contas",
    label: "Contas",
    icon: IconBuildingBank,
    panel: AccountsTab,
  },
  { value: "cartoes", label: "Cartões", icon: IconCreditCard, panel: CardsTab },
  {
    value: "beneficios",
    label: "Benefícios",
    icon: IconGift,
    panel: BenefitsTab,
  },
  {
    value: "instituicoes",
    label: "Instituições",
    icon: IconBuildingCommunity,
    panel: InstitutionsTab,
  },
  {
    value: "categorias",
    label: "Categorias",
    icon: IconCategory,
    panel: CategoriesTab,
  },
  {
    value: "metas",
    label: "Metas de poupança",
    icon: IconTargetArrow,
    panel: GoalsTab,
  },
  {
    value: "assinaturas",
    label: "Assinaturas",
    icon: IconRepeat,
    panel: SubscriptionsTab,
  },
  {
    value: "recorrentes",
    label: "Gastos recorrentes",
    icon: IconCalendarRepeat,
    panel: RecurringTab,
  },
  { value: "regras", label: "Regras", icon: IconRoute, panel: RulesTab },
];

export function CatalogPage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab = CATALOG_TABS.some((t) => t.value === requested)
    ? (requested as string)
    : "usuarios";
  return (
    <Stack gap="lg">
      <PageHeader
        title="Cadastros"
        eyebrow="Configuração"
        icon={<IconBuildingBank size={22} stroke={1.7} />}
        subtitle="Pessoas, contas, cartões, benefícios, categorias e as regras que classificam tudo automaticamente."
      />
      <Tabs
        value={tab}
        keepMounted={false}
        variant="pills"
        radius="xl"
        onChange={(v) => v && setParams({ tab: v }, { replace: true })}
      >
        {/* R14.6: tabs wrap onto a second line instead of hiding off-screen. */}
        <Tabs.List className="et-tabs-wrap">
          {CATALOG_TABS.map((t) => (
            <Tabs.Tab
              key={t.value}
              value={t.value}
              leftSection={<t.icon size={16} stroke={1.8} aria-hidden="true" />}
            >
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {CATALOG_TABS.map(({ value, panel: Panel }) => (
          <Tabs.Panel key={value} value={value} pt="lg" className="et-fade-in">
            <Panel />
          </Tabs.Panel>
        ))}
      </Tabs>
    </Stack>
  );
}

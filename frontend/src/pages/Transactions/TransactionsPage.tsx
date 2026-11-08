import { Stack, Tabs } from "@mantine/core";
import {
  IconCalendarRepeat,
  IconListDetails,
  IconReceipt,
  IconStack2,
} from "@tabler/icons-react";
import { PageHeader } from "../../components/ui";
import { useSearchParams } from "react-router-dom";
import { EntriesTab } from "./EntriesTab";
import { PlansTab } from "./PlansTab";
import { RecurringTab } from "./RecurringTab";

const TABS = ["lancamentos", "parcelamentos", "recorrentes"] as const;
type Tab = (typeof TABS)[number];

/** Transactions, installment plans and recurring purchases (R1.3, R1.12, R7, R12.4). */
export function TransactionsPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = TABS.includes(raw as Tab) ? (raw as Tab) : "lancamentos";
  const changeTab = (value: string | null) => {
    if (!value) return;
    const next = new URLSearchParams(params);
    next.set("tab", value);
    if (value !== "lancamentos") next.delete("uncategorized");
    setParams(next);
  };
  return (
    <Stack gap="lg">
      <PageHeader
        title="Lançamentos"
        eyebrow="Movimento"
        icon={<IconListDetails size={22} stroke={1.7} />}
        subtitle="Tudo o que entrou no mês: importado das faturas e extratos ou lançado à mão."
      />
      <Tabs
        value={tab}
        onChange={changeTab}
        keepMounted={false}
        variant="pills"
        radius="xl"
      >
        <Tabs.List mb="lg" className="et-tabs-wrap">
          <Tabs.Tab
            value="lancamentos"
            leftSection={
              <IconReceipt size={16} stroke={1.8} aria-hidden="true" />
            }
          >
            Lançamentos
          </Tabs.Tab>
          <Tabs.Tab
            value="parcelamentos"
            leftSection={
              <IconStack2 size={16} stroke={1.8} aria-hidden="true" />
            }
          >
            Parcelamentos
          </Tabs.Tab>
          <Tabs.Tab
            value="recorrentes"
            leftSection={
              <IconCalendarRepeat size={16} stroke={1.8} aria-hidden="true" />
            }
          >
            Recorrentes
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="lancamentos">
          <EntriesTab />
        </Tabs.Panel>
        <Tabs.Panel value="parcelamentos">
          <PlansTab />
        </Tabs.Panel>
        <Tabs.Panel value="recorrentes">
          <RecurringTab />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

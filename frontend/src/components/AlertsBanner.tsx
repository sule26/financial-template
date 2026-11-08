import { Alert, Anchor, Stack, type MantineColor } from "@mantine/core";
import {
  IconCalendarRepeat,
  IconFileAlert,
  IconFileOff,
  IconReceiptOff,
  IconTagOff,
  type Icon,
} from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAlerts, useNames } from "../api/hooks";
import { formatDate } from "../lib/format";

function Notice({
  color,
  icon: NoticeIcon,
  title,
  children,
}: {
  color: MantineColor;
  icon: Icon;
  title: string;
  children: ReactNode;
}) {
  return (
    <Alert
      color={color}
      variant="light"
      radius="lg"
      title={title}
      icon={<NoticeIcon size={18} stroke={1.8} aria-hidden="true" />}
      className="et-notice"
      data-color={color}
    >
      {children}
    </Alert>
  );
}

/** Global banner (docs/03): uncategorized items, overdue recurring, missing invoices, files. */
export function AlertsBanner() {
  const { data } = useAlerts();
  const names = useNames();
  if (!data || data.length === 0) return null;
  return (
    <Stack
      gap={8}
      mb="lg"
      aria-label="Alertas"
      className="et-notices et-stagger"
    >
      {data.map((a, i) => {
        if (a.type === "uncategorized")
          return (
            <Notice
              key={i}
              color="orange"
              icon={IconTagOff}
              title={`${a.count} itens sem categoria`}
            >
              Uma categoria foi removida.{" "}
              <Anchor component={Link} to="/lancamentos?uncategorized=1">
                Recategorizar agora
              </Anchor>
            </Notice>
          );
        if (a.type === "recurring_overdue")
          return (
            <Notice
              key={i}
              color="yellow"
              icon={IconCalendarRepeat}
              title="Compra recorrente não apareceu"
            >
              {a.description} prevista em {formatDate(a.planned_date)}.{" "}
              <Anchor component={Link} to="/lancamentos?tab=recorrentes">
                Adiar, pular ou encerrar
              </Anchor>
            </Notice>
          );
        if (a.type === "missing_invoice")
          return (
            <Notice
              key={i}
              color="gray"
              icon={IconReceiptOff}
              title="Fatura faltando"
            >
              {names.owner(a.card_id)}: fatura de {a.month} não importada.
            </Notice>
          );
        if (a.type === "inconsistent_files")
          return (
            <Notice
              key={i}
              color="red"
              icon={IconFileOff}
              title="Arquivo sem lançamentos"
            >
              {a.paths?.join(", ")}: está ativo mas sem lançamentos.{" "}
              <Anchor component={Link} to="/status">
                Reprocessar na tela Status
              </Anchor>
            </Notice>
          );
        return (
          <Notice
            key={i}
            color="red"
            icon={IconFileAlert}
            title={`${a.count} arquivo(s) precisam de atenção`}
          >
            <Anchor component={Link} to="/status">
              Ver na tela Status
            </Anchor>
          </Notice>
        );
      })}
    </Stack>
  );
}

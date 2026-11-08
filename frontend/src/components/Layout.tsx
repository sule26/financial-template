import {
  AppShell,
  Burger,
  Drawer,
  Group,
  ScrollArea,
  Text,
  UnstyledButton,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconBuildingBank,
  IconChartAreaLine,
  IconChecklist,
  IconCoins,
  IconFileStack,
  IconHeartbeat,
  IconHelpCircle,
  IconLayoutDashboard,
  IconListDetails,
  IconSettings,
  IconUsersGroup,
  type Icon,
} from "@tabler/icons-react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { NavLink as RouterLink, useLocation } from "react-router-dom";
import { BrandMark } from "./ui/Guilloche";

export interface NavItem {
  to: string;
  label: string;
  icon: Icon;
  group: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/", label: "Resumo", icon: IconLayoutDashboard, group: "Visão geral" },
  {
    to: "/projecao",
    label: "Projeção",
    icon: IconChartAreaLine,
    group: "Visão geral",
  },
  {
    to: "/lancamentos",
    label: "Lançamentos",
    icon: IconListDetails,
    group: "Movimento",
  },
  { to: "/revisao", label: "Revisão", icon: IconChecklist, group: "Movimento" },
  {
    to: "/a-receber",
    label: "A receber",
    icon: IconUsersGroup,
    group: "Movimento",
  },
  {
    to: "/investimentos",
    label: "Investimentos",
    icon: IconCoins,
    group: "Movimento",
  },
  {
    to: "/cadastros",
    label: "Cadastros",
    icon: IconBuildingBank,
    group: "Configuração",
  },
  {
    to: "/perfis",
    label: "Perfis de banco",
    icon: IconFileStack,
    group: "Configuração",
  },
  {
    to: "/status",
    label: "Status",
    icon: IconHeartbeat,
    group: "Configuração",
  },
  {
    to: "/configuracoes",
    label: "Configurações",
    icon: IconSettings,
    group: "Configuração",
  },
  { to: "/ajuda", label: "Ajuda", icon: IconHelpCircle, group: "Configuração" },
];

export function isActive(to: string, pathname: string): boolean {
  return to === "/" ? pathname === "/" : pathname.startsWith(to);
}

function Wordmark() {
  return (
    <Group gap={10} wrap="nowrap" className="et-wordmark">
      <BrandMark size={30} />
      <div>
        <Text className="et-wordmark__name" component="span">
          Gastos
        </Text>
        <Text className="et-wordmark__tag" component="span">
          finanças da casa
        </Text>
      </div>
    </Group>
  );
}

/** Grouped navigation with a marker that slides to the active item. */
function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation();
  const listRef = useRef<HTMLDivElement>(null);
  const [marker, setMarker] = useState<{ top: number; height: number } | null>(
    null,
  );
  const groups = [...new Set(NAV_ITEMS.map((i) => i.group))];

  useLayoutEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>(
      '[data-active="true"]',
    );
    setMarker(
      active ? { top: active.offsetTop, height: active.offsetHeight } : null,
    );
  }, [pathname]);

  return (
    <div className="et-nav" ref={listRef}>
      {marker && (
        <span
          className="et-nav__marker"
          aria-hidden="true"
          style={{
            transform: `translateY(${marker.top}px)`,
            height: marker.height || undefined,
          }}
        />
      )}
      {groups.map((group) => (
        <div key={group} className="et-nav__group">
          <Text className="et-nav__heading" component="div" aria-hidden="true">
            {group}
          </Text>
          {NAV_ITEMS.filter((i) => i.group === group).map((item) => {
            const active = isActive(item.to, pathname);
            const ItemIcon = item.icon;
            return (
              <UnstyledButton
                key={item.to}
                component={RouterLink}
                to={item.to}
                end={item.to === "/"}
                className="et-nav__item"
                data-active={active || undefined}
                aria-current={active ? "page" : undefined}
                onClick={onNavigate}
              >
                <ItemIcon
                  size={19}
                  stroke={1.7}
                  aria-hidden="true"
                  className="et-nav__icon"
                />
                <span>{item.label}</span>
              </UnstyledButton>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function SidebarFooter() {
  return (
    <Text className="et-sidebar__footer" size="xs">
      <span className="et-dot-live" aria-hidden="true" /> Offline · dados só
      nesta máquina
    </Text>
  );
}

interface LayoutProps {
  header?: ReactNode;
  /** Extra controls shown at the bottom of the mobile drawer (e.g. the theme toggle). */
  drawerFooter?: ReactNode;
  banner?: ReactNode;
  children: ReactNode;
}

export function Layout({
  header,
  drawerFooter,
  banner,
  children,
}: LayoutProps) {
  const [opened, { toggle, close }] = useDisclosure();
  const { pathname } = useLocation();
  return (
    <AppShell
      header={{ height: 64 }}
      navbar={{ width: 248, breakpoint: "sm", collapsed: { mobile: true } }}
      padding={0}
      className="et-shell"
    >
      <AppShell.Header className="et-header" withBorder={false}>
        <Group
          h="100%"
          px={{ base: "sm", sm: "lg" }}
          justify="space-between"
          wrap="nowrap"
          gap="sm"
        >
          <Group wrap="nowrap" gap="xs">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Menu"
            />
            <div className="et-header__brand">
              <Wordmark />
            </div>
          </Group>
          {header}
        </Group>
      </AppShell.Header>
      <AppShell.Navbar
        className="et-sidebar"
        withBorder={false}
        aria-label="Navegação principal"
      >
        <div className="et-sidebar__brand">
          <Wordmark />
        </div>
        <ScrollArea className="et-sidebar__scroll" type="hover">
          <NavList />
        </ScrollArea>
        <SidebarFooter />
      </AppShell.Navbar>
      <Drawer
        opened={opened}
        onClose={close}
        size={280}
        padding="md"
        hiddenFrom="sm"
        title={<Wordmark />}
        classNames={{ content: "et-drawer", header: "et-drawer__header" }}
      >
        <nav aria-label="Navegação (menu)">
          <NavList onNavigate={close} />
        </nav>
        {drawerFooter && <div className="et-drawer__theme">{drawerFooter}</div>}
      </Drawer>
      <AppShell.Main className="et-main">
        <div className="et-content">
          {banner}
          <div key={pathname} className="et-page">
            {children}
          </div>
        </div>
      </AppShell.Main>
    </AppShell>
  );
}

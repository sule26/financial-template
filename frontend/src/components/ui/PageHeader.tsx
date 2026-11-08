import { Group, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

export interface PageHeaderProps {
  /** Page title, rendered as the page's h2 (the app wordmark is the only thing above it). */
  title: string;
  subtitle?: ReactNode;
  /** Small label above the title (e.g. the section of the navigation). */
  eyebrow?: string;
  icon?: ReactNode;
  /** Buttons aligned to the right on wide screens, below the title on small ones. */
  actions?: ReactNode;
  /** Filters/controls row under the title. */
  children?: ReactNode;
}

/** Title + subtitle + actions at the top of every page. */
export function PageHeader({
  title,
  subtitle,
  eyebrow,
  icon,
  actions,
  children,
}: PageHeaderProps) {
  return (
    <Stack gap="md" className="et-page-header" component="header">
      <Group justify="space-between" align="flex-end" gap="md" wrap="wrap">
        <Group gap="md" wrap="nowrap" align="center">
          {icon && (
            <span className="et-page-header__icon" aria-hidden="true">
              {icon}
            </span>
          )}
          <div>
            {eyebrow && (
              <Text className="et-eyebrow" size="xs" fw={700}>
                {eyebrow}
              </Text>
            )}
            <Title order={2}>{title}</Title>
            {subtitle && (
              <Text size="sm" c="dimmed" mt={4} maw={720}>
                {subtitle}
              </Text>
            )}
          </div>
        </Group>
        {actions && (
          <Group gap="sm" wrap="wrap">
            {actions}
          </Group>
        )}
      </Group>
      {children && (
        <Group align="flex-end" gap="md" wrap="wrap" className="et-filters">
          {children}
        </Group>
      )}
    </Stack>
  );
}

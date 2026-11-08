import { Group, Paper, Text, Title } from "@mantine/core";
import { TNode } from "../../i18n/i18n";
import type { ReactNode } from "react";

export interface PanelProps {
  /** Visible h3 and the section's accessible name. */
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  /** Lift on hover; off for panels that hold forms or wide tables. */
  interactive?: boolean;
  className?: string;
  children: ReactNode;
}

/** A titled surface (``<section aria-label={title}>``) — the building block of every page. */
export function Panel({
  title,
  description,
  icon,
  actions,
  interactive = true,
  className,
  children,
}: PanelProps) {
  return (
    <Paper
      p="lg"
      component="section"
      aria-label={title}
      className={["et-panel", interactive ? "et-lift" : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      <Group justify="space-between" mb="md" wrap="nowrap" align="flex-start">
        <Group gap="sm" wrap="nowrap" align="center">
          {icon && (
            <span className="et-icon-chip" aria-hidden="true">
              {icon}
            </span>
          )}
          <div>
            <Title order={3} size="h4">
              <TNode>{title}</TNode>
            </Title>
            {description && (
              <Text size="xs" c="dimmed" mt={2}>
                <TNode>{description}</TNode>
              </Text>
            )}
          </div>
        </Group>
        {actions}
      </Group>
      {children}
    </Paper>
  );
}

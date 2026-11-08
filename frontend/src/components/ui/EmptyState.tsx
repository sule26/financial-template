import { Stack, Text } from "@mantine/core";
import { IconInbox } from "@tabler/icons-react";
import type { ReactNode } from "react";

export interface EmptyStateProps {
  /** Main sentence, e.g. "Nada por aqui ainda." — always text, never only an image. */
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  /** A next step (button or link): an empty state is an invitation, not a dead end. */
  action?: ReactNode;
  compact?: boolean;
}

/** Illustrated empty state: an icon inside a guilloché ring, a sentence and an optional action. */
export function EmptyState({
  title,
  description,
  icon,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <Stack
      align="center"
      gap={compact ? 6 : "xs"}
      py={compact ? "md" : "xl"}
      px="md"
      className="et-empty et-fade-in"
      data-compact={compact || undefined}
    >
      <span className="et-empty__art" aria-hidden="true">
        <svg viewBox="0 0 96 96" className="et-empty__ring">
          {Array.from({ length: 12 }, (_, i) => (
            <ellipse
              key={i}
              cx="48"
              cy="48"
              rx="44"
              ry="18"
              transform={`rotate(${i * 15} 48 48)`}
              fill="none"
              stroke="currentColor"
              strokeWidth="0.6"
            />
          ))}
        </svg>
        <span className="et-empty__icon">
          {icon ?? <IconInbox size={26} stroke={1.6} />}
        </span>
      </span>
      <Text fw={600} ta="center" size={compact ? "sm" : "md"}>
        {title}
      </Text>
      {description && (
        <Text size="sm" c="dimmed" ta="center" maw={420}>
          {description}
        </Text>
      )}
      {action}
    </Stack>
  );
}

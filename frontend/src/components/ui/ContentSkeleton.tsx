import { SimpleGrid, Skeleton, Stack } from "@mantine/core";

/** Placeholder shaped like the content it replaces (cards over a table), instead of a spinner. */
export function ContentSkeleton({
  label = "Carregando",
  cards = 0,
  rows = 4,
}: {
  label?: string;
  cards?: number;
  rows?: number;
}) {
  return (
    <Stack
      gap="md"
      role="status"
      aria-label={label}
      aria-busy="true"
      className="et-skeleton"
    >
      {cards > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: Math.min(cards, 4) }}>
          {Array.from({ length: cards }, (_, i) => (
            <Skeleton key={i} height={112} radius="lg" />
          ))}
        </SimpleGrid>
      )}
      <Stack gap={10}>
        <Skeleton height={14} width="32%" />
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} height={34} width={i % 3 === 2 ? "78%" : "100%"} />
        ))}
      </Stack>
    </Stack>
  );
}

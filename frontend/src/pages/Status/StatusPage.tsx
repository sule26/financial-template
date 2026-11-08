import {
  Alert,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { MonthField } from "../../components/ui/MonthField";
import { notifications } from "@mantine/notifications";
import {
  IconFolderOpen,
  IconHeartbeat,
  IconListCheck,
  IconRadar2,
} from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import {
  useAction,
  useGet,
  useList,
  useNames,
  useOwnerLabels,
} from "../../api/hooks";
import type { ManifestEntry } from "../../api/types";
import { QueryState, errorText } from "../../components/QueryState";
import { formatMonth } from "../../hooks/month";
import { warningText } from "../Review/labels";
import {
  EmptyState,
  MoneyText,
  PageHeader,
  StatusBadge,
  toneFromColor,
} from "../../components/ui";

export interface SyncJob {
  id: string;
  kind: string;
  status: string;
  created_at: string | null;
  finished_at: string | null;
  result: unknown;
  error: string | null;
}

export interface SyncStatus {
  files: (ManifestEntry & { label: string })[];
  last_scan: string | null;
  last_report: Record<string, unknown[]> | null;
  jobs: SyncJob[];
}

/** Badge colors per file status (R3.10, codes in docs/05). */
export const STATUS_COLORS: Record<string, string> = {
  pending_review: "blue",
  partially_confirmed: "cyan",
  confirmed: "green",
  awaiting_card: "orange",
  superseded: "gray",
  unknown_profile: "yellow",
  error: "red",
  duplicate: "gray",
};

const REPORT_LABELS: Record<string, string> = {
  new: "novos",
  changed: "alterados",
  moved: "movidos",
  duplicate: "duplicados",
  removed: "removidos",
  unstable: "ainda copiando",
  errors: "erros",
};

export function formatDateTime(iso: string | null): string {
  if (!iso) return "nunca";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function notifyError(e: unknown) {
  notifications.show({ title: "Erro", message: errorText(e), color: "red" });
}

/** Sync status of the inbox: files, last scan, jobs (R3.10, R4.8). */
export function StatusPage() {
  // scans run in the background queue: poll so new files/statuses show up by themselves
  const status = useGet<SyncStatus>(["sync-status"], "/api/sync/status", 3000);
  const names = useNames();
  const [choosing, setChoosing] = useState<ManifestEntry | null>(null);
  const scan = useAction<void>(
    "post",
    () => "/api/sync/scan",
    () => undefined,
  );
  const reprocess = useAction<string>(
    "post",
    () => "/api/sync/reprocess",
    (path) => ({ path }),
  );
  const data = status.data;
  const files = data?.files ?? [];
  const report = Object.entries(data?.last_report ?? {}).filter(
    ([, v]) => Array.isArray(v) && v.length > 0,
  );

  return (
    <Stack gap="lg">
      <PageHeader
        title="Status"
        eyebrow="Configuração"
        icon={<IconHeartbeat size={22} stroke={1.7} />}
        subtitle="Arquivos da pasta de entrada, o que foi lido de cada um e as tarefas em andamento."
        actions={
          <Button
            leftSection={<IconRadar2 size={16} stroke={2} aria-hidden="true" />}
            loading={scan.isPending}
            onClick={() =>
              scan.mutate(undefined, {
                onSuccess: () =>
                  notifications.show({
                    message: "Varredura iniciada.",
                    color: "green",
                  }),
                onError: notifyError,
              })
            }
          >
            Varrer agora
          </Button>
        }
      />
      <QueryState isLoading={status.isLoading} error={status.error}>
        <Text size="sm">
          Última varredura: <b>{formatDateTime(data?.last_scan ?? null)}</b>
          {report.length > 0 &&
            ` — ${report.map(([k, v]) => `${v.length} ${REPORT_LABELS[k] ?? k}`).join(", ")}`}
        </Text>
        {files.length === 0 ? (
          <EmptyState
            icon={<IconFolderOpen size={26} stroke={1.6} />}
            title="Nenhum arquivo na pasta de entrada."
            description="Coloque PDFs ou CSVs em inbox/faturas ou inbox/extratos e clique em Varrer agora."
          />
        ) : (
          <Table.ScrollContainer minWidth={900} className="et-table-card">
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Arquivo</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Cartão/conta</Table.Th>
                  <Table.Th>Mês</Table.Th>
                  <Table.Th ta="right">Total</Table.Th>
                  <Table.Th>Erro / avisos</Table.Th>
                  <Table.Th className="et-sticky-end">Ações</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {files.map((f) => (
                  <Table.Tr key={f.path}>
                    <Table.Td>
                      <Text size="sm">{f.path}</Text>
                      <Text size="xs" c="dimmed">
                        {f.kind} · {f.format}
                        {f.profile_id && ` · perfil ${f.profile_id}`}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <StatusBadge
                        tone={toneFromColor(STATUS_COLORS[f.status] ?? "gray")}
                      >
                        {f.label ?? f.status}
                      </StatusBadge>
                    </Table.Td>
                    <Table.Td>
                      {names.owner(f.card_id ?? f.account_id) || "—"}
                    </Table.Td>
                    <Table.Td>
                      {f.invoice_month ? formatMonth(f.invoice_month) : "—"}
                    </Table.Td>
                    <Table.Td ta="right">
                      <MoneyText value={f.total} />
                    </Table.Td>
                    <Table.Td>
                      {f.error && (
                        <Text size="sm" c="red">
                          {f.error}
                        </Text>
                      )}
                      {f.warnings.map((w) => (
                        <Text key={w} size="xs" c="orange">
                          {warningText(w)}
                        </Text>
                      ))}
                    </Table.Td>
                    <Table.Td className="et-sticky-end">
                      <Group gap={4} wrap="nowrap">
                        {f.status === "awaiting_card" && (
                          <Button
                            size="xs"
                            onClick={() => setChoosing(f)}
                            aria-label={`${f.kind === "fatura" ? "Escolher cartão" : "Escolher conta"} para ${f.path}`}
                          >
                            {f.kind === "fatura"
                              ? "Escolher cartão"
                              : "Escolher conta"}
                          </Button>
                        )}
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() =>
                            reprocess.mutate(f.path, {
                              onSuccess: () =>
                                notifications.show({
                                  message: `Reprocessado: ${f.path}`,
                                  color: "green",
                                }),
                              onError: notifyError,
                            })
                          }
                          aria-label={`Reprocessar ${f.path}`}
                        >
                          Reprocessar
                        </Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
        <Group gap="sm" mt="sm">
          <span className="et-icon-chip" aria-hidden="true">
            <IconListCheck size={18} stroke={1.7} />
          </span>
          <Title order={3} size="h4">
            Tarefas recentes
          </Title>
        </Group>
        {(data?.jobs ?? []).length === 0 ? (
          <EmptyState
            compact
            icon={<IconListCheck size={22} stroke={1.6} />}
            title="Nenhuma tarefa recente."
          />
        ) : (
          <Table className="et-table-card">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Tarefa</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Início</Table.Th>
                <Table.Th>Fim</Table.Th>
                <Table.Th>Erro</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {[...(data?.jobs ?? [])].reverse().map((j) => (
                <Table.Tr key={j.id}>
                  <Table.Td>{j.kind}</Table.Td>
                  <Table.Td>
                    <StatusBadge
                      tone={toneFromColor(
                        j.status === "error"
                          ? "red"
                          : j.status === "done"
                            ? "green"
                            : "blue",
                      )}
                    >
                      {j.status}
                    </StatusBadge>
                  </Table.Td>
                  <Table.Td>{formatDateTime(j.created_at)}</Table.Td>
                  <Table.Td>
                    {j.finished_at ? formatDateTime(j.finished_at) : "—"}
                  </Table.Td>
                  <Table.Td>{j.error ?? ""}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </QueryState>
      <Modal
        opened={choosing !== null}
        onClose={() => setChoosing(null)}
        title={
          choosing?.kind === "fatura" ? "Escolher cartão" : "Escolher conta"
        }
      >
        {choosing && (
          <ChooseOwnerForm entry={choosing} onDone={() => setChoosing(null)} />
        )}
      </Modal>
    </Stack>
  );
}

/** R4.8: the file waits in "aguardando cartão" until I pick its card (fatura) or account. */
export function ChooseOwnerForm({
  entry,
  onDone,
}: {
  entry: ManifestEntry;
  onDone: () => void;
}) {
  const invoice = entry.kind === "fatura";
  const cards = useList("cards");
  const accounts = useList("accounts");
  const ownerLabel = useOwnerLabels();
  const [owner, setOwner] = useState<string | null>(null);
  const [month, setMonth] = useState(entry.invoice_month ?? "");
  const [error, setError] = useState<string | null>(null);
  const choose = useAction<Record<string, unknown>>(
    "post",
    () => "/api/sync/choose-owner",
  );
  const options = invoice
    ? (cards.data ?? []).map((c) => ({
        value: c.id,
        label: ownerLabel[c.id] ?? c.name,
      }))
    : (accounts.data ?? []).map((a) => ({
        value: a.id,
        label: ownerLabel[a.id] ?? a.name,
      }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!owner)
      return setError(invoice ? "Escolha o cartão" : "Escolha a conta");
    setError(null);
    const body: Record<string, unknown> = { path: entry.path };
    body[invoice ? "card_id" : "account_id"] = owner;
    if (invoice && month) body.invoice_month = month;
    choose.mutate(body, { onSuccess: onDone });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap="sm">
        <Text size="sm">{entry.path}</Text>
        <Select
          label={invoice ? "Cartão" : "Conta"}
          data={options}
          value={owner}
          onChange={setOwner}
          required
          error={error}
        />
        {invoice && (
          <MonthField
            label="Mês da fatura (opcional)"
            value={month}
            onChange={setMonth}
          />
        )}
        {choose.error && (
          <Alert color="red" role="alert">
            {errorText(choose.error)}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button type="submit" loading={choose.isPending}>
            Definir
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

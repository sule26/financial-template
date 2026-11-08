import {
  Alert,
  Button,
  Card,
  Code,
  Group,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileStack } from "@tabler/icons-react";
import { useState } from "react";
import { api } from "../../api/client";
import { useAction, useGet } from "../../api/hooks";
import { QueryState, errorText } from "../../components/QueryState";
import { formatDate, formatMoney, sumMoney } from "../../lib/format";
import type { SyncStatus } from "../Status/StatusPage";
import type { ProfilesList, ProfileTestResult } from "./types";
import { exampleId } from "./banks";
import { EmptyState, StatusBadge, toneFromColor } from "../../components/ui";

const NEW_PROFILE = `id: meu-banco-fatura
name: Meu banco — fatura
kind: fatura
detect:
  all:
    - "MEU BANCO"
`;

const HEADER_LABELS: Record<string, string> = {
  kind: "tipo",
  profile_id: "perfil",
  format: "formato",
  open_invoice: "fatura aberta",
  due_date: "vencimento",
  closing_date: "fechamento",
  total: "total",
  amount_due: "valor a pagar",
  card_hint: "final do cartão",
  account_hint: "conta",
  period_from: "período de",
  period_to: "período até",
  as_of: "posição em",
  invoice_month: "mês da fatura",
  warnings: "avisos",
};

function headerValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (key === "total" || key === "amount_due")
    return formatMoney(String(value));
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value))
    return formatDate(value);
  return String(value);
}

/**
 * Advanced mode of Perfis de banco (R4.3, docs/06): list, edit the YAML, validate, save, test against
 * an inbox file and see the raw text. The simple mode (R13.9) lives in ProfilesPage.
 */
export function ProfileEditor() {
  const list = useGet<ProfilesList>(["profiles"], "/api/profiles");
  const status = useGet<SyncStatus>(["sync-status"], "/api/sync/status");
  const [profileId, setProfileId] = useState("");
  const [yaml, setYaml] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const validate = useAction<
    { yaml: string },
    { valid: boolean; id?: string; error?: string }
  >("post", () => "/api/profiles/validate");
  const test = useAction<{ yaml: string; path: string }, ProfileTestResult>(
    "post",
    () => "/api/profiles/test",
  );
  const raw = useAction<{ path: string }, { pages: string[] }>(
    "post",
    () => "/api/profiles/raw-text",
  );
  const save = useAction<{ id: string; yaml: string }>(
    "put",
    ({ id }) => `/api/profiles/${encodeURIComponent(id)}`,
    ({ yaml: y }) => ({ yaml: y }),
  );

  const load = async (id: string, example = false) => {
    setLoadError(null);
    try {
      const res = await api.get<{ id: string; yaml: string }>(
        example
          ? `/api/profiles/examples/${encodeURIComponent(id)}`
          : `/api/profiles/${encodeURIComponent(id)}`,
      );
      setProfileId(res.id);
      setYaml(res.yaml);
      validate.reset();
      test.reset();
    } catch (e) {
      setLoadError(
        example
          ? `Não foi possível carregar o exemplo "${id}". (${errorText(e)})`
          : errorText(e),
      );
    }
  };

  const data = list.data;
  const paths = (status.data?.files ?? []).map((f) => f.path);
  const result = test.data;
  const lines = result?.lines ?? [];
  const sum = sumMoney(lines.map((l) => l.amount));
  const total = result?.header?.total as string | null | undefined;

  return (
    <Stack gap="lg">
      <QueryState isLoading={list.isLoading} error={list.error}>
        {(data?.profiles ?? []).length === 0 ? (
          <EmptyState
            icon={<IconFileStack size={26} stroke={1.6} />}
            title="Nenhum perfil em profiles/. Parta de um exemplo ou crie um novo."
          />
        ) : (
          <Table.ScrollContainer minWidth={640} className="et-table-card">
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Perfil</Table.Th>
                  <Table.Th>Tipo</Table.Th>
                  <Table.Th>Arquivo</Table.Th>
                  <Table.Th ta="right">Documentos</Table.Th>
                  <Table.Th ta="right">Com erro</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data?.profiles.map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td>
                      {p.name}{" "}
                      <Text span size="xs" c="dimmed">
                        ({p.id})
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {p.kind} · {p.format}
                    </Table.Td>
                    <Table.Td>{p.file ?? "—"}</Table.Td>
                    <Table.Td ta="right">{p.files}</Table.Td>
                    <Table.Td ta="right">
                      {p.errors > 0 ? (
                        <StatusBadge tone="danger">{p.errors}</StatusBadge>
                      ) : (
                        0
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() => void load(p.id)}
                        aria-label={`Editar perfil ${p.id}`}
                      >
                        Editar
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
        {(data?.plugins ?? []).length > 0 && (
          <Text size="sm" c="dimmed">
            Plugins:{" "}
            {data?.plugins.map((p) => `${p.id} (${p.kind})`).join(", ")}
          </Text>
        )}
        <Group gap="xs">
          <Button
            variant="default"
            size="xs"
            onClick={() => {
              setProfileId("meu-banco-fatura");
              setYaml(NEW_PROFILE);
              setLoadError(null);
            }}
          >
            Novo perfil
          </Button>
          {(data?.examples ?? []).map(exampleId).map((ex) => (
            <Button
              key={ex}
              variant="subtle"
              size="xs"
              onClick={() => void load(ex, true)}
            >
              Usar exemplo {ex}
            </Button>
          ))}
        </Group>
      </QueryState>

      <Card padding="lg">
        <Stack gap="sm">
          {loadError && (
            <Alert color="red" role="alert">
              {loadError}
            </Alert>
          )}
          <TextInput
            label="ID do perfil"
            description="Nome do arquivo em profiles/ (a-z, 0-9, -); precisa ser igual ao id do YAML"
            value={profileId}
            onChange={(e) => setProfileId(e.currentTarget.value)}
          />
          <Textarea
            label="YAML do perfil"
            autosize
            minRows={14}
            maxRows={30}
            spellCheck={false}
            styles={{
              input: { fontFamily: "var(--mantine-font-family-monospace)" },
            }}
            value={yaml}
            onChange={(e) => setYaml(e.currentTarget.value)}
          />
          <Group>
            <Button
              variant="light"
              disabled={!yaml.trim()}
              loading={validate.isPending}
              onClick={() => validate.mutate({ yaml })}
            >
              Validar
            </Button>
            <Button
              disabled={!yaml.trim() || !profileId.trim()}
              loading={save.isPending}
              onClick={() =>
                save.mutate(
                  { id: profileId.trim(), yaml },
                  {
                    onSuccess: () =>
                      notifications.show({
                        message: `Perfil ${profileId} salvo; arquivos com erro serão reprocessados.`,
                        color: "green",
                      }),
                  },
                )
              }
            >
              Salvar
            </Button>
          </Group>
          {validate.data &&
            (validate.data.valid ? (
              <Alert color="green">YAML válido (id {validate.data.id}).</Alert>
            ) : (
              <Alert color="red" role="alert">
                YAML inválido: {validate.data.error}
              </Alert>
            ))}
          {(validate.error || save.error) && (
            <Alert color="red" role="alert">
              {errorText(validate.error ?? save.error)}
            </Alert>
          )}
        </Stack>
      </Card>

      <Card padding="lg">
        <Stack gap="sm">
          <Title order={3} size="h4">
            Testar contra um arquivo
          </Title>
          <Group align="flex-end">
            <Select
              label="Arquivo da pasta de entrada"
              data={paths}
              value={path}
              onChange={setPath}
              searchable
              nothingFoundMessage="Nenhum arquivo"
              w={360}
            />
            <Button
              disabled={!path || !yaml.trim()}
              loading={test.isPending}
              onClick={() => path && test.mutate({ yaml, path })}
            >
              Testar
            </Button>
            <Button
              variant="default"
              disabled={!path}
              loading={raw.isPending}
              onClick={() => path && raw.mutate({ path })}
            >
              Ver texto bruto
            </Button>
          </Group>
          {(test.error || raw.error) && (
            <Alert color="red" role="alert">
              {errorText(test.error ?? raw.error)}
            </Alert>
          )}
          {result && !result.valid && (
            <Alert color="red" role="alert">
              YAML inválido: {result.error}
            </Alert>
          )}
          {result?.valid && (
            <Stack gap="sm">
              <Text size="sm">
                Resultado: <b>{result.status}</b>
                {result.error && ` — ${result.error}`}
              </Text>
              {result.header && (
                <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
                  {Object.entries(result.header).map(([k, v]) => (
                    <div key={k}>
                      <Text size="xs" c="dimmed">
                        {HEADER_LABELS[k] ?? k}
                      </Text>
                      <Text size="sm">{headerValue(k, v)}</Text>
                    </div>
                  ))}
                </SimpleGrid>
              )}
              <Text size="sm" component="div">
                Soma das linhas: <b>{formatMoney(sum)}</b> · total do documento:{" "}
                <b>{formatMoney(total)}</b>{" "}
                {total !== null && total !== undefined && (
                  <StatusBadge
                    tone={toneFromColor(
                      Number(total) === Number(sum) ? "green" : "red",
                    )}
                  >
                    {Number(total) === Number(sum) ? "confere" : "não confere"}
                  </StatusBadge>
                )}
              </Text>
              <Title order={4} size="h5">
                Linhas reconhecidas ({lines.length})
              </Title>
              {lines.length > 0 && (
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Data</Table.Th>
                      <Table.Th>Descrição</Table.Th>
                      <Table.Th ta="right">Valor</Table.Th>
                      <Table.Th>Parcela</Table.Th>
                      <Table.Th>Final</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {lines.map((l) => (
                      <Table.Tr key={l.index}>
                        <Table.Td>{formatDate(l.date)}</Table.Td>
                        <Table.Td>{l.description}</Table.Td>
                        <Table.Td ta="right">{formatMoney(l.amount)}</Table.Td>
                        <Table.Td>
                          {l.installment_n
                            ? `${l.installment_n}/${l.installment_of}`
                            : ""}
                        </Table.Td>
                        <Table.Td>{l.card_hint ?? ""}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
              <Alert
                color={(result.unrecognized ?? []).length ? "red" : "green"}
                title={`Linhas NÃO reconhecidas (${(result.unrecognized ?? []).length})`}
              >
                {(result.unrecognized ?? []).map((u, i) => (
                  <Code key={i} block mb={4}>
                    {u}
                  </Code>
                ))}
              </Alert>
              <Text size="sm" fw={500}>
                Linhas ignoradas ({(result.ignored ?? []).length})
              </Text>
              {(result.ignored ?? []).map((u, i) => (
                <Code key={i} block c="dimmed">
                  {u}
                </Code>
              ))}
            </Stack>
          )}
          {raw.data && (
            <Stack gap="xs">
              <Title order={4} size="h5">
                Texto bruto
              </Title>
              {raw.data.pages.map((page, i) => (
                <div key={i}>
                  <Text size="xs" c="dimmed">
                    Página {i + 1}
                  </Text>
                  <ScrollArea.Autosize mah={320}>
                    <Code block aria-label={`Texto bruto da página ${i + 1}`}>
                      {page}
                    </Code>
                  </ScrollArea.Autosize>
                </div>
              ))}
            </Stack>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}

/**
 * Perfis de banco (R4.3, R13.9). Opens in a simple mode — which banks are supported, test a file and
 * read the result in plain language, what to do when a bank is missing — with the YAML editor kept
 * under "Modo avançado".
 */
import {
  Accordion,
  Alert,
  Button,
  Code,
  Group,
  List,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
} from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import {
  IconBuildingBank,
  IconCheck,
  IconFileSearch,
  IconFileStack,
  IconHelpCircle,
  IconTool,
  IconX,
} from "@tabler/icons-react";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { useGet } from "../../api/hooks";
import { errorText, QueryState } from "../../components/QueryState";
import {
  EmptyState,
  MoneyText,
  PageHeader,
  Panel,
  StatusBadge,
} from "../../components/ui";
import type { SyncStatus } from "../Status/StatusPage";
import { KIND_TEXT, summarize, supportedBanks, type Bank } from "./banks";
import { ProfileEditor } from "./ProfileEditor";
import type { ProfilesList, ProfileTestResult } from "./types";

export type {
  ExampleInfo,
  ProfileInfo,
  ProfilesList,
  ProfileTestResult,
} from "./types";

const plural = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`;

function BankCard({ bank }: { bank: Bank }) {
  return (
    <Paper
      p="md"
      withBorder
      component="article"
      aria-label={bank.name}
      className="et-lift"
    >
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Text fw={650}>{bank.name}</Text>
          {bank.builtin && <StatusBadge tone="accent">embutido</StatusBadge>}
        </Group>
        <Text size="sm" c="dimmed">
          {(bank.kind && KIND_TEXT[bank.kind]) ?? "Fatura ou extrato"}
          {bank.format ? ` · ${bank.format.toUpperCase()}` : ""}
        </Text>
        <Group gap="xs">
          <Text size="sm">
            {plural(bank.files, "arquivo lido", "arquivos lidos")}
          </Text>
          {bank.errors > 0 && (
            <StatusBadge tone="danger">
              {plural(bank.errors, "com erro", "com erro")}
            </StatusBadge>
          )}
        </Group>
      </Stack>
    </Paper>
  );
}

/** YAML of a bank: profiles/ first, then the built-in examples (or the other way round). */
async function loadYaml(bank: Bank): Promise<string> {
  const urls = [
    `/api/profiles/${encodeURIComponent(bank.id)}`,
    `/api/profiles/examples/${encodeURIComponent(bank.id)}`,
  ];
  if (bank.source === "example") urls.reverse();
  try {
    return (await api.get<{ yaml: string }>(urls[0] as string)).yaml;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404)
      return (await api.get<{ yaml: string }>(urls[1] as string)).yaml;
    throw e;
  }
}

function TestResult({ result }: { result: ProfileTestResult }) {
  if (!result.valid)
    return (
      <Alert color="red" role="alert" title="O perfil tem um erro">
        {result.error}
      </Alert>
    );
  const s = summarize(result);
  const unrecognized = result.unrecognized ?? [];
  return (
    <Stack gap="sm" aria-live="polite">
      {result.error && (
        <Alert color="orange" variant="light">
          {result.error}
        </Alert>
      )}
      <Alert
        color={s.matches === false ? "red" : "jade"}
        variant="light"
        icon={
          s.matches === false ? (
            <IconX size={18} aria-hidden="true" />
          ) : (
            <IconCheck size={18} aria-hidden="true" />
          )
        }
        title="Resultado do teste"
      >
        <Text size="sm">
          Lemos {plural(s.count, "lançamento", "lançamentos")}, soma{" "}
          <MoneyText value={s.sum} fw={650} />
          {s.total === null ? (
            <>; o documento não informa o total para conferir.</>
          ) : (
            <>
              , total do banco <MoneyText value={s.total} fw={650} />{" "}
              {s.matches ? (
                <b>— bate ✓</b>
              ) : (
                <b>
                  — não bate: diferença <MoneyText value={s.difference} />
                </b>
              )}
            </>
          )}
        </Text>
      </Alert>
      {unrecognized.length > 0 ? (
        <Stack gap={4}>
          <Text size="sm" fw={600}>
            Linhas que não entendemos ({unrecognized.length})
          </Text>
          <Text size="xs" c="dimmed">
            Podem ser lançamentos que faltaram. Ajuste o perfil no modo
            avançado.
          </Text>
          {unrecognized.map((u, i) => (
            <Code key={i} block>
              {u}
            </Code>
          ))}
        </Stack>
      ) : (
        <Text size="sm" c="dimmed">
          Todas as linhas com valor foram entendidas.
        </Text>
      )}
    </Stack>
  );
}

function TestFile({ banks }: { banks: Bank[] }) {
  const status = useGet<SyncStatus>(["sync-status"], "/api/sync/status");
  const [path, setPath] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const files = status.data?.files ?? [];
  const entry = files.find((f) => f.path === path);
  const detected = entry?.profile_id ?? null;
  const profileId = chosen ?? detected;
  const bank = banks.find((b) => b.id === profileId);
  const run = useMutation({
    mutationFn: async ({ bank: b, path: p }: { bank: Bank; path: string }) =>
      api.post<ProfileTestResult>("/api/profiles/test", {
        yaml: await loadYaml(b),
        path: p,
      }),
  });

  return (
    <Panel
      title="Testar um arquivo"
      icon={<IconFileSearch size={18} stroke={1.8} />}
      description="Escolha um arquivo da pasta de entrada: a app usa o perfil que reconheceu o arquivo e mostra se a leitura bate com o total do banco."
      interactive={false}
    >
      <Stack gap="sm">
        <Group align="flex-end" wrap="wrap">
          <Select
            label="Arquivo para testar"
            placeholder={files.length ? "Escolha" : "Nenhum arquivo na pasta"}
            data={files.map((f) => f.path)}
            value={path}
            onChange={(p) => {
              setPath(p);
              setChosen(null);
              run.reset();
            }}
            searchable
            nothingFoundMessage="Nenhum arquivo"
            w={340}
          />
          <Select
            label="Perfil"
            placeholder="Nenhum reconheceu"
            data={banks.map((b) => ({ value: b.id, label: b.name }))}
            value={profileId}
            onChange={(id) => {
              setChosen(id);
              run.reset();
            }}
            disabled={!path}
            w={260}
          />
          <Button
            disabled={!path || !bank}
            loading={run.isPending}
            onClick={() => bank && path && run.mutate({ bank, path })}
          >
            Testar arquivo
          </Button>
        </Group>
        {path && !detected && (
          <Text size="sm" c="dimmed">
            Nenhum perfil reconheceu este arquivo. Escolha um perfil para testar
            ou veja “Meu banco não está na lista”.
          </Text>
        )}
        {path && detected && !chosen && (
          <Text size="sm" c="dimmed">
            Perfil reconhecido: {bank?.name ?? detected}.
          </Text>
        )}
        {run.error && (
          <Alert color="red" role="alert">
            {errorText(run.error)}
          </Alert>
        )}
        {run.data && <TestResult result={run.data} />}
      </Stack>
    </Panel>
  );
}

function NotListed() {
  return (
    <Panel
      title="Meu banco não está na lista"
      icon={<IconHelpCircle size={18} stroke={1.8} />}
      interactive={false}
    >
      <List type="ordered" spacing={6} size="sm">
        <List.Item>
          Coloque um PDF (ou CSV) do banco na pasta <Code>inbox/faturas/</Code>{" "}
          (cartão) ou <Code>inbox/extratos/</Code> (conta).
        </List.Item>
        <List.Item>
          Abra o <b>Modo avançado</b> abaixo e clique em “Usar exemplo” do banco
          mais parecido (ou “Novo perfil”).
        </List.Item>
        <List.Item>
          Ajuste o texto que identifica o banco e o formato das linhas; use “Ver
          texto bruto” para ver o que a app lê do arquivo.
        </List.Item>
        <List.Item>
          Teste contra o arquivo até a soma bater com o total e salve. Os
          arquivos com erro são relidos sozinhos.
        </List.Item>
      </List>
    </Panel>
  );
}

export function ProfilesPage() {
  const list = useGet<ProfilesList>(["profiles"], "/api/profiles");
  const data = list.data;
  const banks = data ? supportedBanks(data) : [];
  const loadErrors = Object.entries(data?.errors ?? {});
  return (
    <Stack gap="lg">
      <PageHeader
        title="Perfis de banco"
        eyebrow="Configuração"
        icon={<IconFileStack size={22} stroke={1.7} />}
        subtitle="Quais bancos a app sabe ler. Teste um arquivo e veja se a leitura confere — sem precisar mexer em YAML."
      />
      <QueryState isLoading={list.isLoading} error={list.error}>
        {loadErrors.length > 0 && (
          <Alert
            color="red"
            title="Perfis com erro de carregamento"
            role="alert"
          >
            {loadErrors.map(([file, msg]) => (
              <Text key={file} size="sm">
                <Code>{file}</Code>: {msg}
              </Text>
            ))}
          </Alert>
        )}
        <Panel
          title="Bancos suportados"
          icon={<IconBuildingBank size={18} stroke={1.8} />}
          description="Perfis em profiles/ e os exemplos embutidos na app."
          interactive={false}
        >
          {banks.length === 0 ? (
            <EmptyState
              icon={<IconFileStack size={26} stroke={1.6} />}
              title="Nenhum banco configurado ainda."
            />
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
              {banks.map((b) => (
                <BankCard key={b.id} bank={b} />
              ))}
            </SimpleGrid>
          )}
        </Panel>
        <TestFile banks={banks} />
        <NotListed />
        <Accordion variant="separated" radius="lg">
          <Accordion.Item value="advanced">
            <Accordion.Control
              icon={<IconTool size={18} stroke={1.8} aria-hidden="true" />}
            >
              Modo avançado
            </Accordion.Control>
            <Accordion.Panel>
              <ProfileEditor />
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </QueryState>
    </Stack>
  );
}

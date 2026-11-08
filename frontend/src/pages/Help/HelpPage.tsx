/** Ajuda (R1.8): "Como usar" and "Como modificar", short static guides based on docs/. */
import {
  Accordion,
  Code,
  List,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { IconBook2, IconHelpCircle, IconTool } from "@tabler/icons-react";
import { PageHeader } from "../../components/ui";
import type { ReactNode } from "react";

interface Topic {
  value: string;
  title: string;
  body: ReactNode;
}

const USE: Topic[] = [
  {
    value: "fluxo",
    title: "Como a app funciona",
    body: (
      <List type="ordered" spacing={4}>
        <List.Item>
          Coloque PDFs (ou CSVs) de fatura em <Code>inbox/faturas/</Code> e de
          extrato em <Code>inbox/extratos/</Code>; subpastas são livres.
        </List.Item>
        <List.Item>
          A app detecta o arquivo, descobre o banco pelo perfil e lê os
          lançamentos.
        </List.Item>
        <List.Item>
          Os lançamentos vão para a <strong>Revisão</strong> já com categoria e
          divisão sugeridas. Nada entra sem você confirmar.
        </List.Item>
        <List.Item>
          Confira, ajuste e confirme. Resumo, Projeção e A receber se atualizam.
        </List.Item>
        <List.Item>
          Apagar o PDF remove os lançamentos dele; recolocar o mesmo arquivo
          traz suas edições de volta.
        </List.Item>
      </List>
    ),
  },
  {
    value: "primeiros-passos",
    title: "Primeiros passos (Cadastros)",
    body: (
      <List spacing={4}>
        <List.Item>
          <strong>Usuários</strong>: as pessoas para quem os gastos são
          atribuídos (não há login). Renda é opcional e tem vigência por mês.
        </List.Item>
        <List.Item>
          <strong>Padrões de divisão</strong>: ex. “Casal” 60/40. Para mudar a
          proporção, adicione uma nova versão a partir de um mês; meses
          anteriores não mudam.
        </List.Item>
        <List.Item>
          <strong>Contas e cartões</strong>: donos (soma 100%) e responsável
          (quem paga o banco). Um cartão ligado a uma conta pode herdar os donos
          dela. Cartão adicional usa a fatura do principal.
        </List.Item>
        <List.Item>
          <strong>Categorias</strong>: todo lançamento precisa de uma. Excluir
          uma categoria em uso deixa os itens sem categoria até você
          recategorizar pelo alerta.
        </List.Item>
      </List>
    ),
  },
  {
    value: "dia-a-dia",
    title: "Dia a dia: lançamento rápido e compras recorrentes",
    body: (
      <List spacing={4}>
        <List.Item>
          Botão “+” (ou tecla <Code>N</Code>): valor, descrição, meio de
          pagamento (crédito, VR, débito, PIX, dinheiro), categoria e divisão.
        </List.Item>
        <List.Item>
          O lançamento fica <em>previsto</em> até a fatura/extrato chegar; aí
          ele casa com a linha importada sem duplicar, e suas edições passam
          para ela. Dinheiro é definitivo na hora.
        </List.Item>
        <List.Item>
          Compras recorrentes (ex.: ração a cada 45 dias) geram a próxima
          ocorrência prevista e entram na projeção.
        </List.Item>
      </List>
    ),
  },
  {
    value: "banco",
    title: "Como adicionar um banco",
    body: (
      <List type="ordered" spacing={4}>
        <List.Item>
          Copie o PDF para <Code>inbox/faturas/&lt;banco&gt;/</Code>. Ele
          aparece como “perfil desconhecido”.
        </List.Item>
        <List.Item>
          Em <strong>Perfis</strong> → “Novo perfil”, parta de um exemplo de{" "}
          <Code>profiles/examples/</Code> (Inter e Nubank).
        </List.Item>
        <List.Item>
          Use “Ver texto bruto” para escrever <Code>detect</Code>,{" "}
          <Code>header</Code> e <Code>line</Code>.
        </List.Item>
        <List.Item>
          “Testar” até ter zero linhas não reconhecidas e soma = total.
        </List.Item>
        <List.Item>
          Salve: o arquivo é reprocessado e vai para a Revisão.
        </List.Item>
        <List.Item>
          PDF com senha: adicione a senha em{" "}
          <Code>secrets/pdf-passwords.yaml</Code>.
        </List.Item>
      </List>
    ),
  },
  {
    value: "investimentos",
    title: "Investimentos",
    body: (
      <Text size="sm">
        Cadastre o investimento, registre o saldo de tempos em tempos e os
        aportes/resgates. Rendimento = saldo − aportes líquidos. Aporte e
        resgate não contam como gasto nem renda. Saldo com mais de 45 dias
        aparece como desatualizado.
      </Text>
    ),
  },
];

const MODIFY: Topic[] = [
  {
    value: "processo",
    title: "Processo de desenvolvimento",
    body: (
      <List spacing={4}>
        <List.Item>
          Uma task por vez, de <Code>specs/expense-tracker-web/tasks.md</Code>,
          seguindo <Code>docs/10-processo-de-desenvolvimento.md</Code>.
        </List.Item>
        <List.Item>
          A documentação é a especificação: mudou comportamento, atualize{" "}
          <Code>docs/</Code> e <Code>specs/</Code> na mesma mudança.
        </List.Item>
        <List.Item>
          Código e comentários em inglês; documentação e interface em português.
        </List.Item>
      </List>
    ),
  },
  {
    value: "testes",
    title: "Testes",
    body: (
      <List spacing={4}>
        <List.Item>Testes primeiro; nada avança com teste vermelho.</List.Item>
        <List.Item>
          Backend com cobertura ≥ 90%; frontend com Vitest + Testing Library.
        </List.Item>
        <List.Item>
          Testes que cobrem um requisito começam com o id dele (ex.:{" "}
          <Code>r1_12 …</Code>).
        </List.Item>
      </List>
    ),
  },
  {
    value: "taskfile",
    title: "Comandos (Taskfile, tudo em Docker)",
    body: (
      <Stack gap={4}>
        <Text size="sm">
          Não é preciso Python nem Node na máquina; só Docker e o Task.
        </Text>
        <List spacing={4}>
          <List.Item>
            <Code>task --list</Code>: todos os comandos
          </List.Item>
          <List.Item>
            <Code>task test</Code>, <Code>task test:frontend</Code>: testes
          </List.Item>
          <List.Item>
            <Code>task coverage</Code>: cobertura com o gate de 90%
          </List.Item>
          <List.Item>
            <Code>task lint</Code>: tipos e lint; <Code>task ci</Code>: tudo
            junto
          </List.Item>
        </List>
      </Stack>
    ),
  },
  {
    value: "dados",
    title: "Dados e segurança",
    body: (
      <Text size="sm">
        Os dados ficam em JSON em <Code>data/</Code>, só na sua máquina. Nunca
        versione <Code>data/</Code>, <Code>inbox/</Code>, <Code>secrets/</Code>{" "}
        nem PDFs reais.
      </Text>
    ),
  },
];

function Section({
  title,
  icon,
  topics,
}: {
  title: string;
  icon: ReactNode;
  topics: Topic[];
}) {
  return (
    <Stack gap="sm">
      <div className="et-help__title">
        <span className="et-icon-chip" aria-hidden="true">
          {icon}
        </span>
        <Title order={3}>{title}</Title>
      </div>
      <Accordion variant="separated" multiple radius="lg">
        {topics.map((t) => (
          <Accordion.Item key={t.value} value={t.value}>
            <Accordion.Control>{t.title}</Accordion.Control>
            <Accordion.Panel>{t.body}</Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}

export function HelpPage() {
  return (
    <Stack gap="xl">
      <PageHeader
        title="Ajuda"
        eyebrow="Configuração"
        icon={<IconHelpCircle size={22} stroke={1.7} />}
        subtitle="Guias curtos para usar o app no dia a dia e para adaptá-lo (bancos, categorias, regras)."
      />
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl" className="et-stagger">
        <Section
          title="Como usar"
          icon={<IconBook2 size={18} stroke={1.7} />}
          topics={USE}
        />
        <Section
          title="Como modificar"
          icon={<IconTool size={18} stroke={1.7} />}
          topics={MODIFY}
        />
      </SimpleGrid>
    </Stack>
  );
}

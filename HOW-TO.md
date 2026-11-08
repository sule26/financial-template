# HOW-TO — usar o Expense Tracker no dia a dia

Guia prático, do zero ao uso mensal. Detalhes técnicos estão em [docs/](docs/README.md).

## 1. Pré-requisitos (uma vez)

- Docker + docker compose
- [Task](https://taskfile.dev) (`task --version`)

Não precisa de Python nem Node na máquina.

## 2. Primeira execução

```bash
task init                               # cria data/, inbox/, profiles/, secrets/
cp profiles/examples/*.yaml profiles/   # perfis prontos: Inter e Nubank
task up                                 # abre em http://127.0.0.1:8080
```

Porta ocupada? `APP_PORT=8090 task up`. Parar: `task down`. Ver logs: `task logs`.

Se algum PDF tiver senha, edite `secrets/pdf-passwords.yaml` (veja o passo 7).

## 3. Cadastros (uma vez) — tela **Cadastros**

Faça nesta ordem, porque um depende do outro:

1. **Usuários**: você, sua esposa, seus pais… Renda é opcional. Se tiver renda, ela entra no indicador
   de renda comprometida. **Repassar o que deve para** (opcional): tudo o que essa pessoa deve passa a
   ser devido a quem você escolher (ex.: os gastos de um filho são cobrados da mãe).
   Meses e datas são escolhidos num calendário (mês/ano ou dia), nunca digitados.
2. **Categorias** (tipos de gasto): Mercado, Casa, Pets, Lazer… Toda compra precisa de uma categoria.
3. **Padrões de divisão** (opcional): ex. "Casal" eu 60% / esposa 40%. Quando a proporção mudar,
   crie uma **nova versão a partir do mês**; os meses anteriores não mudam. Cada versão escolhe o
   modo: **Percentual** ou **Proporcional à renda** (calculado pela renda de cada membro no mês; se
   faltar renda, vale a última versão em percentual). Ex.: 70/30 até abril, proporcional de maio a
   agosto, 50/50 a partir de setembro.
4. **Contas**: conta corrente (débito/PIX), conta de **benefício** (VR/VA) e **dinheiro**. Uma conta
   conjunta tem como donos o padrão "Casal" e um responsável (quem paga o banco). O **cartão de
   benefício** (VR/VA) é cadastrado aqui, como conta do tipo **Benefício**: ele não tem fechamento nem
   vencimento, só o **dia de renovação** (opcional), o dia em que o crédito do benefício cai.
5. **Cartões**: dia de fechamento e de vencimento, **finais do cartão** (físico, virtual, adicionais;
   ajudam a reconhecer o cartão no PDF) e perfil (`inter-fatura`, `nubank-fatura`). Cartão de conta
   conjunta: vincule a conta e deixe os donos como "Padrão", para herdar os da conta. Cartão adicional
   usado pelos pais: crie como adicional do principal, com donos "pais 100%". A lista mostra os donos
   e o responsável efetivos, com a origem ("herdado da conta Inter"); "sem dono (configure)" indica
   cartão sem donos e sem conta vinculada.
   Criar (ou renomear) um cartão principal cria a pasta `inbox/faturas/<nome em minúsculo>/`; uma
   conta (que não seja dinheiro) cria `inbox/extratos/<nome em minúsculo>/`.
6. **Benefícios** (opcional): VR, VA, auxílio home office… com nome, pessoa, onde cai (cartão de
   benefício ou conta corrente) e valor mensal com vigência. Benefício em conta soma na renda;
   em cartão de benefício soma na "renda em benefício" e o cartão vira meio de pagamento.
7. **Instituições** (opcional): onde ficam investimentos que não estão numa conta cadastrada:
   corretora, exchange, previdência, banco ou outra (nome + tipo). Também dá para criar uma direto no
   formulário de investimento (**+ nova instituição**).
8. **Regras** (opcional): ex. descrição contém `MERCADO` → categoria Mercado, divisão Casal. Elas
   preenchem a Revisão sozinhas.
9. **Assinaturas** (streaming, academia) e **Compras recorrentes** (ex.: ração a cada 45 dias no
   cartão X) entram na projeção.

## 4. No dia a dia: botão **+ Lançar** (ou tecla `N`)

Lance cada gasto na hora, com valor, descrição, meio de pagamento, cartão ou conta, **categoria** e
divisão. Parcelado: informe as parcelas, e o parcelamento é criado.

- Crédito, VR, débito e PIX ficam como **previstos** até chegar a fatura ou o extrato.
- Dinheiro é definitivo na hora.
- Quando o PDF chegar, a app **casa** o previsto com a linha do banco e não duplica. Suas edições
  (categoria, divisão, nota) passam para a linha do banco.

## 5. Fim do mês: faturas e extratos

1. Baixe os PDFs (ou o CSV da fatura ainda aberta) e coloque em:
   - `inbox/faturas/<nome do cartão>/…` para faturas de cartão (a pasta é criada com o cartão)
   - `inbox/extratos/<nome da conta>/…` para extratos de conta

   Arquivo dentro da pasta de um cartão/conta é atribuído a ele. Dê ao arquivo o nome do mês da
   fatura, ex. `inbox/faturas/nubank/2026-10.pdf`: quando o documento não informa o vencimento, esse
   `YYYY-MM` vira o mês da fatura (se divergir do documento, aparece um aviso).
2. A app lê sozinha: ao iniciar, a cada 60 s e quando a pasta muda. Também dá para usar
   **Status → Varrer agora**.
3. Abra **Revisão**:
   - confira categoria, divisão e as sugestões (parcela de plano, pagamento de fatura, acerto,
     antecipação…); aceite, rejeite ou escolha;
   - **Confirmar arquivo** para confirmar tudo de uma vez;
   - se aparecer "Substituir a fatura … por esta?", foi um segundo PDF do mesmo cartão e mês (ex.: a
     aberta e depois a fechada). Aprove, e nada duplica.
4. Fatura com "total a pagar R$ 0,00" (paga antes) também importa todas as compras normalmente.

Remover um PDF da pasta remove os lançamentos dele. Recolocar o PDF traz de volta as suas edições.

## 6. Acompanhar

| Tela | Para quê |
|------|----------|
| **Resumo** | Gastos do mês por categoria, cartão e meio de pagamento; gasto x renda; resumo anual; metas; renda comprometida. Filtro por pessoa |
| **Projeção** | Sempre 12 meses a partir de hoje: parcelas, assinaturas, recorrentes. Mostra mês real, projetado ou "faltando" |
| **A receber** | No topo, **Próximos recebimentos**: um item por cartão/conta e mês de fatura, com a data limite (vencimento da fatura onde a compra foi feita), separado em Receber e Pagar, com totais e selo "vencido". Abaixo, quanto cada pessoa te deve (ou você deve), por mês e por lançamento. **Registrar acerto** quando alguém pagar. Em cada item, **Marcar como recebido** (ou **Marcar como pago**) cria o acerto daquele cartão/conta e mês; o item fica com o selo "recebido" e um botão **Desfazer** (apaga esse acerto). Acerto parcial aparece como "R$ x de R$ y". Itens recebidos ficam ocultos; ligue **Mostrar recebidos** para vê-los. Os totais consideram só o que falta |
| **Investimentos** | Registre saldo, aportes e resgates; veja rendimento e evolução. A **Instituição** é escolhida numa lista: suas contas ou as instituições de Cadastros → Instituições |
| **Lançamentos** | Editar e recategorizar em lote; **Parcelamentos → Antecipar** (move as parcelas restantes para a próxima fatura); **Recorrentes** → adiar, pular, encerrar |
| **Configurações** | Tema claro/escuro/sistema e **cor de destaque** (Esmeralda, Oceano, Violeta, Âmbar, Rubi, Grafite). Guardado neste navegador; muda na hora |

O seletor de mês no topo sempre abre no mês atual e permite voltar para corrigir meses anteriores.
Alternar claro/escuro fica no topo também.

**Alertas** no topo de toda tela: itens sem categoria (após remover uma categoria), compra recorrente
que não apareceu, fatura faltando e arquivo com problema. Cada alerta tem atalho para resolver.

## 7. Problemas comuns

| Vejo | Faça |
|------|------|
| Arquivo "aguardando cartão" | Status → escolha o cartão. Ou cadastre os finais do cartão; ele reprocessa sozinho |
| "perfil desconhecido" | Banco novo: veja o passo 8 |
| "erro: senha" | Coloque a senha em `secrets/pdf-passwords.yaml` (`perfil-id: "senha"`) e use **Reprocessar** |
| Aviso "soma ≠ total" | O layout do banco mudou: **Perfis → Testar** mostra as linhas não reconhecidas |
| "Arquivo sem lançamentos" | Status → **Reprocessar** |
| `task up` rodou mas a página não abre | VPN capturando a rede do Docker: veja [docs/14 › Problemas comuns](docs/14-operacao.md#problemas-comuns) |

## 8. Perfis de banco: conferir e adicionar um banco (sem código)

A tela **Perfis de banco** abre no modo simples:

- **Bancos suportados**: cards com cada banco que a app lê (os exemplos embutidos aparecem com o selo
  "embutido"), se é fatura ou extrato, o formato e quantos arquivos já leu / com erro.
- **Testar um arquivo**: escolha um arquivo da inbox; a app usa o perfil que o reconheceu e responde
  em português, ex. "Lemos 32 lançamentos, soma R$ 1.234,56, total do banco R$ 1.234,56 — bate ✓"
  ou "não bate: diferença R$ 10,00", e lista as linhas que não entendeu.

Banco que não está na lista:

1. Coloque um PDF do banco na inbox. Ele aparece como "perfil desconhecido".
2. Abra **Modo avançado** e use **Usar exemplo** (Inter ou Nubank) como ponto de partida.
3. **Ver texto bruto**, ajuste `detect`, `header` e `line` (regex) e use **Testar** até a soma bater e
   não sobrar nenhuma linha não reconhecida.
4. **Salvar**: os arquivos pendentes são reprocessados.

Formato completo: [docs/06-perfis-de-banco.md](docs/06-perfis-de-banco.md).

## 9. Backup

- Automático antes de cada importação, em `data/.backups/`.
- Manual: `task backup` (nunca é apagado).
- Para guardar fora da máquina, copie `data/`, `profiles/` e `secrets/`.
- Nada disso vai para o git: `data/`, `inbox/`, `faturas/`, `secrets/` e os PDFs são ignorados.

## 10. Se for mexer no código

Leia [AGENTS.md](AGENTS.md) e [docs/10](docs/10-processo-de-desenvolvimento.md). Comandos úteis:
`task test`, `task ci` (tudo que o CI roda), `task e2e` e `task dev` (com hot reload em
http://127.0.0.1:5173).

Para retomar a sessão de IA que construiu o projeto: `source .env && kiro-cli chat --resume-id "$KIRO_SESSION_ID"`.

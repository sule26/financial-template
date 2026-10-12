# Design: Expense Tracker Web

Este documento guarda **as decisões e o porquê**. A mecânica detalhada (formatos, algoritmos,
exemplos) vive em [`docs/`](../../docs/README.md) e não é repetida aqui, para não haver duas fontes.

| Assunto | Onde está o detalhe |
|---------|---------------------|
| Componentes, camadas, fluxo | [docs/03-arquitetura.md](../../docs/03-arquitetura.md) |
| Arquivos JSON, fingerprint, invariantes | [docs/04-modelo-de-dados.md](../../docs/04-modelo-de-dados.md) |
| Sincronização com a pasta | [docs/05-sincronizacao.md](../../docs/05-sincronizacao.md) |
| Perfis de banco | [docs/06-perfis-de-banco.md](../../docs/06-perfis-de-banco.md) |
| Meses, parcelas, antecipação, assinaturas, projeção | [docs/07-regras-de-negocio.md](../../docs/07-regras-de-negocio.md) |
| Divisões, padrões de divisão, donos/responsável, saldos | [docs/08-divisoes-e-acertos.md](../../docs/08-divisoes-e-acertos.md) |
| Dia a dia, meios de pagamento, compras recorrentes | [docs/16-dia-a-dia.md](../../docs/16-dia-a-dia.md) |
| Revisão e reconciliação | [docs/09-revisao-e-reconciliacao.md](../../docs/09-revisao-e-reconciliacao.md) |
| Investimentos | [docs/15-investimentos.md](../../docs/15-investimentos.md) |
| Processo e testes | [docs/10](../../docs/10-processo-de-desenvolvimento.md), [docs/11](../../docs/11-estrategia-de-testes.md) |
| Segurança | [docs/13-seguranca.md](../../docs/13-seguranca.md) |

## Arquitetura (resumo)

Um container: FastAPI (Python 3.11, 1 worker) serve a API e o build do React. Dados em JSON em
`data/`; PDFs em `inbox/`; perfis em `profiles/`; senhas em `secrets/`. Porta só em loopback.
Uma fila única serializa todo o processamento de arquivos.

## Rationale

### Decisão 1: JSON com repositório em memória e escrita atômica

**Escolha**: um arquivo JSON por entidade, carregado em memória ao iniciar; cada mutação regrava o
arquivo via `tmp + fsync + os.replace`; lock de arquivo impede duas instâncias.

**Justificativa, em ordem de força**:
1. Requisito explícito (JSON).
2. Volume pessoal (~5k lançamentos/ano) cabe em memória; regravar o arquivo custa milissegundos.
3. `os.replace` é atômico em POSIX: crash nunca deixa arquivo pela metade.

**Trade-offs aceitos**:
| Custo | Realidade |
|-------|-----------|
| Sem transação entre arquivos | Ordem de gravação definida (manifesto por último) + scan de inicialização reconcilia; backup antes de cada importação |
| Sem consultas indexadas | Agregação em memória é trivial nesse volume |
| Um único processo | Uso single-user |

**Quando essa decisão estaria errada**: `transactions.json` > 20 MB, gravação > 200 ms, ou necessidade
de mais de um processo → SQLite atrás da mesma interface `Repository`.

### Decisão 2: perfis de banco declarativos (YAML + regex), plugin Python opcional

**Escolha**: leitor de PDF genérico; cada banco é um perfil YAML testável na UI.

**Justificativa**:
1. "Qualquer banco que eu queira adicionar": banco novo sem código nem rebuild.
2. A tela de teste e a conferência soma x total detectam na hora quando o banco muda o layout.
3. Layouts difíceis têm saída (plugin) sem impor código a todos.

**Trade-offs aceitos**:
| Custo | Realidade |
|-------|-----------|
| Regex é frágil | Conferência soma x total (R4.4) avisa |
| Tabelas complexas | `pdfplumber` preserva layout; plugin cobre o resto |

**Quando estaria errada**: se a maioria dos bancos precisar de plugin → investir num extrator por tabela.

**Alternativas descartadas**: um parser Python por banco (código para cada banco novo); LLM para
extrair (dados financeiros saindo da máquina, ou modelo local pesado e não determinístico).

### Decisão 3: real **ou** projetado por (cartão, mês)

**Escolha**: a fatura importada substitui inteiramente a projeção daquele cartão naquele mês.

**Justificativa**: elimina a classe inteira de bugs de dupla contagem; a reconciliação só precisa
manter o cronograma futuro correto.

**Quando estaria errada**: se algum banco gerar faturas parciais (PDF com só parte dos lançamentos).

### Decisão 4: anotações separadas, por fingerprint

**Escolha**: edições manuais ficam em `annotations.json`, não só no lançamento.

**Justificativa**: R3.4 (remover PDF remove os dados) e R3.5 (recolocar restaura as edições) só
convivem se a edição sobreviver ao lançamento.

**Quando estaria errada**: banco reemitindo PDFs com descrição/valor diferentes com frequência →
fingerprint muda; mitigado pela sugestão de anotação órfã.

### Decisão 5: container único, só loopback, sem login

**Escolha**: FastAPI serve API + frontend; porta `127.0.0.1:8080`; sem autenticação.

**Justificativa**: uso pessoal por uma pessoa; menos peças.

**Trade-off**: qualquer processo local acessa a app; mitigado contra ataques via navegador
(checagem de `Host`, header obrigatório em mutações, sem CORS).

**Quando estaria errada**: acesso de outro dispositivo/rede → autenticação obrigatória antes.

### Decisão 6: divisão guardada como spec, resolvida pelo mês

**Escolha**: lançamentos guardam `{"split_id": …}` ou a lista fixa; percentuais de padrões de divisão
são resolvidos pelo `invoice_month` no momento do cálculo.

**Justificativa**:
1. R6.11: mudar "Casal" de 60/40 para 55/45 a partir de um mês não pode alterar o passado — o
   versionamento por `from_month` garante isso sem regravar lançamentos.
2. Modo proporcional à renda acompanha o `income_history` sem job de recálculo.

**Trade-offs aceitos**:
| Custo | Realidade |
|-------|-----------|
| Editar uma versão antiga do padrão muda meses passados | É explícito na UI (aviso ao editar versão com lançamentos) |
| Cálculo a cada consulta | Barato no volume pessoal |

**Quando estaria errada**: se eu quiser "congelar" meses fechados → snapshot dos percentuais ao fechar o mês.

### Decisão 7: investimentos por snapshot manual

**Escolha**: saldo informado por mim em datas; rendimento = saldo − aporte líquido.

**Justificativa**: app offline, sem cotação; o número que importa é o saldo que o banco/corretora
mostra. Aportes vindos do extrato ligam investimento e fluxo de caixa.

**Quando estaria errada**: muitos ativos de renda variável onde a evolução diária importa →
importar posição de corretora ou cotação (Fase 5).

### Decisão 8: lançamento manual é previsão; o documento manda

**Escolha**: todo lançamento manual com meio que gera documento (crédito, benefício, débito, PIX…)
fica `provisional` e só conta em mês/período sem documento; quando a fatura ou o extrato chega, ele é
casado e absorvido (minhas edições migram para a linha importada).

**Justificativa**:
1. Permite registrar gastos no dia a dia sem esperar a fatura e sem duplicar no fim do mês.
2. O valor e a data corretos são os do banco; minha categoria e divisão são preservadas.
3. Reusa a mesma regra "real x projetado" (Decisão 3) em vez de criar outro mecanismo.

**Trade-offs aceitos**:
| Custo | Realidade |
|-------|-----------|
| Casamento aproximado pode errar | Sempre é sugestão na Revisão; ambiguidade vira escolha |
| Manual sem par precisa de decisão | Aviso `unmatched_manual` com 3 opções |

**Quando estaria errada**: se a maioria dos gastos for em meios sem documento (dinheiro) → nada muda;
se o banco agrupar lançamentos (um débito para várias compras) → casamento N:1, hoje não suportado.

### Decisão 9: compra recorrente por intervalo separada de assinatura

**Escolha**: dois conceitos: assinatura (mensal/anual, valor fixo, por mês de fatura) e compra recorrente
(intervalo em dias/semanas/meses, valor estimado, por data, reancorada pela compra real).

**Justificativa**: "a cada 45 dias" não cabe em mês de fatura (cai 0, 1 ou 2 vezes por fatura), e a
reancoragem pela data real não faz sentido para assinatura.

**Quando estaria errada**: se a maioria das recorrências virar mensal fixa → unificar com assinatura.

### Decisão 10: categoria removida deixa itens sem categoria (não bloqueia)

**Escolha**: remover categoria em uso é permitido; itens ficam `category_id = null` com alerta
persistente, em vez de bloquear (409) ou forçar migração imediata.

**Justificativa**: pedido explícito; mantém a lista de categorias livre para reorganizar.
O alerta global e o filtro "sem categoria" tornam o estado visível até ser resolvido.

**Trade-off**: uma exceção ao invariante de referência (`category_id` pode ser `null`), restrita a esse caso.

## Stack

| Camada | Tecnologia | Licença |
|--------|-----------|---------|
| Backend | Python 3.11, FastAPI, Pydantic v2, uvicorn | MIT / MIT / BSD |
| PDF | pdfplumber (pdfminer.six), pypdf (senha) | MIT / BSD |
| Pasta | watchdog | Apache-2.0 |
| YAML | PyYAML | MIT |
| Testes backend | pytest, pytest-cov, hypothesis, reportlab (PDFs sintéticos) | MIT / MIT / MPL-2.0 / BSD |
| Frontend | React 18, TypeScript, Vite, TanStack Query, React Router, Mantine, Recharts | MIT |
| Testes frontend | Vitest, Testing Library, MSW, Playwright | MIT / MIT / MIT / Apache-2.0 |
| Runtime | Docker, docker compose | — |

Versões exatas pinadas em `backend/pyproject.toml` e `frontend/package-lock.json` (T0.2, T0.3).
`hypothesis` é MPL-2.0 (copyleft fraco por arquivo): aceitável como dependência só de teste, sem
modificar nem redistribuir seu código.

## Layout do repositório

```
AGENTS.md  CLAUDE.md  README.md  docker-compose.yml  Dockerfile  Taskfile.yml
backend/   pyproject.toml  src/expense_tracker/{api,domain,storage,importing,profiles,sync,review}/  tests/
frontend/  package.json  src/{pages,components,api,hooks}/  tests/
profiles/examples/*.yaml
docs/  specs/expense-tracker-web/
data/ inbox/ profiles/*.yaml secrets/     ← gitignored, montados no container
```

## Invariantes

- Toda divisão resolvida soma 100%.
- Todo lançamento importado aponta para um arquivo do manifesto; arquivo fora do manifesto ⇒ zero lançamentos dele.
- Para cada (cartão, mês), o total vem de exatamente uma fonte (real ou projetado).
- Nenhum float em disco ou na API.
- Nenhuma senha de PDF em `data/`, log ou API.
- `domain` não faz I/O.
- `transfer` e `settlement` nunca contam como gasto nem como renda.

## Dependências externas

Nenhuma em runtime. Funciona offline.

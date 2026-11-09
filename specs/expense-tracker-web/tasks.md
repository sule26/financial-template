# Tasks: Expense Tracker Web

Toda task segue [docs/10-processo-de-desenvolvimento.md](../../docs/10-processo-de-desenvolvimento.md)
e só é marcada `[x]` quando o [Definition of Done](../../docs/10-processo-de-desenvolvimento.md#definition-of-done)
está completo. Cada fase termina num [gate](../../docs/10-processo-de-desenvolvimento.md#gates-por-fase).
A próxima task é a primeira `[ ]` cujas dependências estão todas `[x]`.
Desvios e decisões tomadas durante a task vão numa linha `Notas:` logo abaixo dela.

## Fase 0 — Fundação
- [x] T0.2 Backend: `pyproject.toml` com versões pinadas, app FastAPI com `/api/health`, pytest + gate de 90%, `Clock` injetável
- [x] T0.3 Frontend: Vite + React + TS + Mantine + Router + TanStack Query, layout com navegação e banner de alertas globais
- [x] T0.4 `Dockerfile` multi-stage (build do front → imagem Python não-root), `compose.yaml` (dev e uso, porta só em 127.0.0.1, rootfs read-only, `cap_drop: ALL`), `Taskfile.yaml` (`test`, `coverage`, `lint`, `trace`, `docs-check`, `ci`, `up`, `down`, `dev`, `build`, `e2e`, `backup`) — depends on: T0.2, T0.3
- [x] T0.1 Validar a estrutura criada no planejamento (`.gitignore`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `specs/`) com `task docs-check` — depends on: T0.4
- [x] T0.5 CI (GitHub Actions, `.github/workflows/ci.yaml`) rodando `task ci` — depends on: T0.4
- [x] T0.6 Teste de arquitetura (direção das dependências; `domain` sem I/O) e builders de fixtures — depends on: T0.2

## Fase 1 — Armazenamento e domínio
- [x] T1.1 `storage`: repositório JSON (cache, lock fcntl, escrita atômica, ordem de gravação, schema_version, migração, backups rotativos, invariantes) (R2) — depends on: T0.6
  Notas: batch tudo-ou-nada (rollback em memória) e um único backup de migração, achados da revisão. Integridade referencial (invariante 3) fica na camada `services` (T1.13).
- [x] T1.2 `domain`: dinheiro/percentual decimal, `AllocationSpec`, mês de fatura com `billing_history`, `H` por cartão, cartão adicional (R1.1, R1.10) — depends on: T0.6
- [x] T1.3 `domain`: cronograma de parcelamento (resto na 1ª), status, cancelamento (R1.2, R1.3) — depends on: T1.2
- [x] T1.4 `domain`: antecipação, desfazer (R7.1, R7.2, R7.4) — depends on: T1.3
  Notas: revisão mostrou dupla contagem ao antecipar parcela anterior ao mês alvo; regra corrigida em docs/07 (parcela inicial ≥ mês alvo). O desconto (R7.5) é aplicado na reconciliação (T4.3) somando as linhas vinculadas.
- [x] T1.5 `domain`: assinaturas mensais/anuais (R1.4) — depends on: T1.2
- [x] T1.6 `domain`: usuários com renda opcional, renda zero, histórico (R1.5, R6.1) — depends on: T1.2
- [x] T1.7 `domain`: padrões de divisão (fixo com versões, proporcional, fallback), donos/responsável com herança, regras em duas passadas, precedência, arredondamento, saldos, acertos, aviso de mês acertado (R5.3, R6.2–R6.4, R6.7–R6.13) — depends on: T1.6
- [x] T1.8 `domain`: compras recorrentes por intervalo (previsão, reancoragem, adiar/pular/encerrar) (R12) — depends on: T1.2
- [x] T1.9 `domain`: meios de pagamento e tipos de conta (crédito, benefício, débito, PIX, transferência, boleto, dinheiro); renda em benefício (R11.1–R11.3) — depends on: T1.2
- [x] T1.10 `domain`: real x projetado (inclui fatura aberta com `as_of`, manuais previstos, recorrentes, mês faltando), projeção de 12 meses (R1.13), renda comprometida, por meio de pagamento (R8.5, R8.9, R1.9, R11.4, R4.11) — depends on: T1.3–T1.9
- [x] T1.11 `domain`: investimentos — snapshots, movimentações, saldo, rendimento, distribuição, metas (R9.1–R9.3, R9.5, R9.6) — depends on: T1.7
- [x] T1.12 `domain` + `storage`: categorias obrigatórias; remoção em uso → `null` em cascata + contagem para o alerta (R1.11, R1.12) — depends on: T1.1
- [x] T1.13 API CRUD: usuários, padrões de divisão, contas, cartões, categorias (com remoção R1.12), metas, assinaturas, compras recorrentes, parcelamentos, regras, acertos, investimentos (R1.1, R1.4, R1.11, R1.12, R6, R9.1, R12.1) — depends on: T1.1–T1.12
  Notas: camada `services` (catalog/reports/transactions) entre `api` e `domain`/`storage`; integridade referencial e cascata de categoria vivem nela.
- [x] T1.14 API de lançamentos: manual/rápido com categoria obrigatória e meio de pagamento, antecipar/desfazer, cancelar plano, "reaplicar regras" com prévia, alertas globais (sem categoria, recorrente não ocorrida, mês faltando) (R10.1, R10.4, R7, R12.4) — depends on: T1.13
- [x] T1.15 API de segurança: checagem de `Host`, `X-Requested-With` em mutações, sem CORS, logs sem valores (docs/13) — depends on: T0.2

## Fase 2 — Telas e painéis
- [x] T2.1 Cadastros: usuários/renda, padrões de divisão, contas (tipos), cartões (donos/responsável/adicionais/billing_history), categorias, metas, assinaturas, compras recorrentes, regras + seletor de divisão reutilizável (R1.1, R1.11, R6.7–R6.10, R12.1)
- [x] T2.2 Lançamento rápido global (R10.1, R10.2)
- [x] T2.3 Lançamentos: lista com filtros (meio de pagamento, sem categoria, previstos), parcelamento manual, antecipar, recategorizar em lote, avisos de recorrente (R1.12, R7, R12.4)
- [x] T2.4 Resumo: pizza por categoria, gasto x renda, empilhado por cartão, por meio de pagamento, resumo anual, metas, renda comprometida, filtro confirmados/pendentes (R1.6, R1.7, R1.9, R5.5, R11.4)
- [x] T2.5 Projeção 12 meses, com meses reais/projetados/faltando (R1.6, R1.13, R8.5, R8.9)
- [x] T2.6 A receber: saldo por pessoa, detalhe, acertos, meses incompletos (R6.4, R6.5, R6.13)
- [x] T2.7 Investimentos: cadastro, saldo/aporte/resgate, painel (R9)
- [x] T2.8 Ajuda: "Como usar" e "Como modificar" (R1.8)
- [x] T2.9 Modo escuro: alternância claro/escuro/sistema persistida, gráficos legíveis nos dois temas (R1.14)

## Fase 3 — Sincronização e importação
- [x] T3.1 `importing`: texto de PDF (pdfplumber), PDF com senha (pypdf), secrets loader, timeout de parse (R4.5)
- [x] T3.2 `importing`: leitura de CSV (codificação, separador, colunas, `as_of`) (R4.10)
- [x] T3.3 `profiles`: schema YAML (pdf e csv), loader, detecção, header (`total`, `amount_due`), seções por cartão, `classify`/`tag`, inferência de ano, plugin Python (R4.1, R4.2, R4.6, R4.7, R4.9) — depends on: T3.1, T3.2
- [x] T3.4 `profiles`: conferência soma x total, `no_total` (R4.4, R4.9) — depends on: T3.3
- [x] T3.5 Identificação de cartão/conta e `awaiting_card` + `card_choices` (R4.8) — depends on: T3.3
- [x] T3.6 Fingerprint (ocorrência, dedupe de extrato) + annotations (R3.5, R3.12) — depends on: T3.5
- [x] T3.7 `sync`: manifesto, scan (novo/alterado/movido/duplicado/removido), arquivo estável, fila única, watchdog com debounce, scan periódico, recuperação após crash (R3.1–R3.10) — depends on: T3.6
- [x] T3.8 `sync`: substituição de fatura (inclui aberta → fechada), extratos sobrepostos, cascata de remoção com recriação por id determinístico (R3.11–R3.13, R4.11) — depends on: T3.7
  Notas: id de staging é derivado de (fingerprint, documento), para candidatos e extratos sobrepostos não se sobrescreverem; remover o substituto reativa o anterior pelo diff (mantém confirmações).
- [x] T3.9 API de sync/status/jobs e perfis (teste contra arquivo, texto bruto) (R3.10, R4.3) — depends on: T3.8
- [x] T3.10 Telas Perfis e Status (R4.3, R3.10, R4.8)

## Fase 4 — Revisão e reconciliação
- [x] T4.1 `review`: staging, sugestões, confirmação (unitária/lote/arquivo), categoria obrigatória, congelamento da divisão (R5.1–R5.3, R1.11)
- [x] T4.2 Reconciliação: parcelas (1–3), estorno de parcelado (4), parcela esperada ausente (7) (R8.1, R8.2, R8.7, R8.8)
  Notas: "antecipada no banco" (linha 7) usa `status_override = anticipated_at_bank`, sem a restrição de `H`.
- [x] T4.3 Reconciliação: antecipação e desconto (5, 6, 8) (R7.3, R7.5)
- [x] T4.4 Reconciliação: manual previsto × importado (9, 10), compra recorrente (10b), assinatura (11) (R8.3, R8.6, R10.3, R12.3)
- [x] T4.5 Extrato: pagamento de fatura incl. antecipado e "nada a pagar" (12), transferência interna (13), acerto (14), investimento (15) (R4.9, R6.6, R8.4, R8.10, R9.4)
  Notas: pagamento antecipado casa pela soma do período (total − a pagar); transferência interna compara valor absoluto e direção.
- [x] T4.6 Sugestão de regra e anotação órfã (R5.4)
- [x] T4.7 Tela Revisão (incl. substituição de fatura e `needs_choice`) (R5, R3.11)
- [x] T4.8 Testes de cenário de [docs/11](../../docs/11-estrategia-de-testes.md#cenários) e de segurança
- [x] T4.9 E2E (Playwright): soltar arquivo sintético na inbox → revisar → confirmar → remover → recolocar
  Notas: revisão final (code-review + refutador ao vivo) achou 3 P1 (mover+copiar no mesmo scan apagava confirmados; divisão do manual retroativo não chegava à linha; carry-over CSV→PDF duplicava o plano) e P2s (nota do manual, antecipação sem valor, backups rotacionando os manuais, clickjacking, log com valores, mês sem fatura como faltando, falha temporária apagando confirmados, `.dockerignore`); todos corrigidos com teste de regressão.

## Fase 6 — Feedback do operador (R13)
- [x] T6.1 Redesign premium do frontend (tema, ícones, animações, reduced-motion) (R13.1)
- [x] T6.2 Pasta por cartão/conta + identificação pela pasta + mês pelo nome do arquivo + perfis embutidos (R13.2, R13.3)
- [x] T6.3 Projeção/Resumo filtrados por pessoa + total geral (R13.4)
- [x] T6.4 Benefícios (VR, auxílio home office) com destino cartão/conta (R13.5)
- [x] T6.5 Bloquear exclusão de usuário vinculado com mensagem clara (R13.6)
- [x] T6.6 Categorias padrão na primeira execução (R13.7)
- [x] T6.7 Seletor de mês dinâmico (R13.8)
- [x] T6.8 Perfis de banco simplificados (R13.9)
  Notas: modo simples (cards de bancos suportados, testar arquivo com o perfil detectado, passo a passo) + editor atual em "Modo avançado". `examples` aceita só ids (backend atual) ou objetos com nome/tipo; o YAML é buscado em `/api/profiles/{id}` e, se 404, em `/api/profiles/examples/{id}` (ou o inverso para exemplo). Testes `r13_9_*`.
- [x] T6.9 Tela Configurações com cor de destaque (R13.10)
  Notas: 6 cores (Esmeralda, Oceano, Violeta, Âmbar, Rubi, Grafite) em `src/lib/accents.ts`; contraste AA verificado por teste (`r13_10_*`) para botão preenchido, texto de destaque e variante light nos dois temas. Cores semânticas (positivo, sucesso, cédula do Resumo) continuam jade de propósito.
- [x] T6.10 "Repassar para" + recebimentos por cartão e vencimento (R13.11)
  Notas: backend concluído (`users.collector_user_id`, credor = coletor do devedor, `BalanceLine.card_id/account_id/due_date`, `GET /api/reports/receivables`; testes `test_r13_11_*`). UI concluída: campo "Repassar o que deve para" e coluna "Repassa para" em Usuários; seção "Próximos recebimentos" no topo de A receber (testes `r13_11_*`). Repasse não é transitivo. Resolvido em T6.13: quando coletor ≠ responsável, gera-se também a dívida coletor → responsável (R13.14). Acertos sem vínculo não são rateados por item (cada recebimento traz `settled_month_total` do mês/par); acertos vinculados quitam o item (T6.15).
- [x] T6.11 Modo da divisão por versão (percentual ou renda) (R13.12)
  Notas: backend concluído (`SplitVersion.mode`, `shares` vazio em versão proporcional, `SplitProfile.mode` como padrão legado; testes `test_r13_12_*`). UI concluída: SegmentedControl por versão, percentuais escondidos no proporcional, `mode` por versão e `shares: []` ao salvar, `SplitProfile.mode` enviado igual ao da última versão (testes `r13_12_*`). Ao salvar um perfil proporcional antigo, as versões viram `income_proportional` com `shares` vazio e perdem os percentuais de fallback; o formulário avisa quando não sobra nenhuma versão em percentual. Fallback usa "versão com percentuais" (não só `mode=fixed`) para manter perfis proporcionais antigos, cujas versões têm `shares` e `mode` nulo, com o mesmo comportamento.
- [x] T6.12 Seletores de mês/data em todos os formulários (R13.13)
  Notas: `MonthField`/`DateField` (`@mantine/dates` 7.15.2, já instalado, + `DatesProvider` pt-br) em todos os campos de mês/data; conversão em `src/lib/dates.ts` sem fuso. Campos obrigatórios não têm botão limpar, então mensagens de "mês inválido" viraram "escolha o mês". `RecurringTab.nextDate` continua com `toISOString`, mas é aritmética toda em UTC (sem deslocamento).
- [x] T6.13 Repasse coletor → responsável (R13.14)
  Notas: backend: `domain/reports.balances` gera a linha coletor → responsável com o mesmo lançamento, cartão/conta, vencimento e mês (testes `test_r13_14_*`); testes `test_r13_11_*` atualizados (o responsável volta a receber, via coletor). Sem mudança de contrato da API (só valores).
- [x] T6.14 Instituições de investimento (contas + não bancos) (R13.15)
  - Notas (backend concluído): coleção `institutions` (`Institution {id, name, type}`, prefixo `inst`), CRUD em `/api/institutions`; `Investment.institution_id` aceita id de conta ou de instituição (`422 reference_not_found` caso contrário) e protege a exclusão de ambas (`409 in_use`); `institution` texto continua aceito (testes `test_r13_15_*`).
  - Notas (frontend concluído): aba Cadastros → Instituições (CRUD, 409 legível); campo Instituição do investimento é um select agrupado Contas/Instituições com "+ nova instituição" inline; tabela mostra o nome (fallback no texto legado `institution`). Marcar [x] após o backend (`/api/institutions`, `institution_id`) ser integrado.
- [x] T6.15 Marcar recebimento como recebido (R13.16)
  - Notas (backend concluído): `Settlement.card_id/account_id/invoice_month` (card adicional → principal; card ou conta exige `invoice_month`; não ambos); receivables com `settled`, `remaining`, `status`, `overdue` só com `remaining > 0`, totals por `remaining`; `POST /api/reports/receivables/mark-received` (201, devolve o acerto; `404 receivable_not_found`, `409 already_received`). Desvio: o vínculo é dado por `invoice_month` (não só `card_id`), para cobrir recebimentos em conta (testes `test_r13_16_*`).
  - Notas (frontend concluído): botões "Marcar como recebido/pago" (POST mark-received), selo "recebido"/"pago", "Desfazer" (DELETE do acerto com mesmo par/cartão-conta/mês, buscado em GET /api/settlements), parcial "R$ x de R$ y", filtro "Mostrar recebidos". Itens marcados na sessão continuam visíveis para permitir desfazer. Marcar [x] após o backend ser integrado.
- [x] T6.16 Cartão de benefício com dia de renovação + donos herdados visíveis em Cartões (R13.17)
  - Notas: `Account.renewal_day` (1–31, só `type = benefit`, erro claro em outro tipo; testes `test_r13_17_*`). UI: "Dia de renovação" no formulário de Contas (só Benefício; enviado `null` nos outros tipos), selo "renova dia N" na tabela de Contas, aviso em Cartões com link para Contas, dia de renovação da conta escolhida na aba Benefícios. Bug corrigido: a coluna Donos de Cartões mostrava "herda" sem o dono; agora mostra a divisão efetiva e a origem ("herdado da conta Inter" / "herdado do cartão X" / "sem dono (configure)"), e há coluna Responsável com a mesma resolução (`pages/Catalog/cardInheritance.ts`, espelho de `domain/allocation.resolve_card`; testes `r1_10 *`, `r13_17 *`).

## Fase 5 — Features extras (a decidir)
- [ ] Orçamento por categoria com alertas
- [ ] Limite comprometido por cartão (parcelas futuras)
- [ ] Detecção automática de assinaturas e compras recorrentes
- [ ] Economia com antecipações
- [ ] Fluxo de caixa mensal (renda − faturas − assinaturas)
- [ ] Relatório por pessoa (PDF/CSV)
- [ ] Backup versionado de `data/` (git interno por importação confirmada)
- [ ] Contas com caixa compartilhado (`funding: pooled`) — ver pergunta aberta em docs/08
- [x] Pin das imagens base por digest (docs/13 Supply chain)
- [x] Teste de propriedade da sync (sequências aleatórias de mv/cp/rm/edição sem perder confirmados)
- [x] Checagem de consistência na tela Status (arquivo confirmado sem lançamentos)

## Fase 7 — Feedback do operador: visibilidade e cadastro (R14)

Ordem: primeiro o que corrige o que o operador já vê errado (T7.1–T7.3), depois modelo novo (T7.4, T7.5), por fim o cadastro guiado (T7.6). Toda task de UI termina com `task ui-tour` e revisão das capturas (R14.7).

Verificação: testes escritos pelo mesmo agente que implementou (ambiente sem subagent `dev` separado — verificação independente de testes pulada); revisão independente (semantic reviewer) achou 4 P1 + 6 P2, todos corrigidos com teste de regressão.

- [x] T7.0 Tour visual `task ui-tour` (seed sintético, todas as telas/abas, claro e escuro, falha em erro de console/API 5xx) + docs/11 (R14.7)
- [x] T7.1 Renda da casa sem pessoa selecionada; tabelas sem corte; rótulos técnicos traduzidos (R14.6) — depends on: T7.0
  Notas: renda da casa = soma da renda de todos sem pessoa; selos sem corte; coluna Ações fixa à direita; abas quebram linha; `owners:account` traduzido. Testes `test_r14_6_*`, `r14_6_*`.
- [x] T7.2 Rótulo inequívoco de cartão/conta em todas as telas (R14.3) — depends on: T7.0
  Notas: só nomes repetidos ganham sufixo (cartão ••final / adicional / conta / benefício / dinheiro); usado em `useNames().owner`, IdSelect e selects. Testes `r14_3_*`.
- [x] T7.3 Projeção só com cartões; itens do mês filtrados por pessoa (R14.2) — depends on: T7.2
  Notas: `cards_view` no domínio; renda comprometida continua contando contas; `month-items?cards_only&user_id` (parte da pessoa, com `total_amount`). Testes `test_r14_2_*`, `r14_2_*`.
- [x] T7.4 Várias rendas por usuário e renda pontual (R14.4) — depends on: T7.1
  Notas: `incomes` (rendas com nome) + `one_off_incomes`; legado `income_history` vira a renda "Renda" ao salvar; pontual não entra na divisão proporcional (decisão confirmada pelo operador). Testes `test_r14_4_*`, `r14_4_*`.
- [x] T7.5 Vários responsáveis com percentual em conta/cartão (R14.1) — depends on: T7.0
  Notas: `responsibles` (lista ou padrão de divisão) herdado junto com o principal; dívida = parte × % de cada pagador; resíduo ao principal; "repassar para" por pagador. Testes `test_r14_1_*`.
- [x] T7.6 Cadastro de cartão (e conta) guiado (R14.5) — depends on: T7.2, T7.5
  Notas: seções Identificação / Quem usa e quem paga / Fatura / Leitura do PDF, banco numa lista, pasta da inbox, resumo ao vivo; adicional sem fatura própria. Testes `r1_10 *`, `r6_9 *` atualizados.
- [x] T7.7 Revisão de fatura só com gastos (R14.8)
  Notas: linhas não-gasto da fatura não são encenadas; tipo só Gasto/Estorno/Tarifa/Investimento (`422 invalid_kind`). Testes `test_r14_8_*`, `r14_8_*`.
- [x] T7.8 Histórico de preço, divisão visível, desativar/reativar e períodos desativados em assinaturas e recorrentes (R14.9–R14.11)
  Notas: `price_history` e `pauses` em assinaturas e recorrentes; Desativar abre período a partir da 1ª compra não ocorrida, Ativar fecha no mês anterior; editores em Cadastros, Ativar/Desativar em Lançamentos → Recorrentes. Testes `test_r14_9_*`–`test_r14_11_*`, `r14_10_*`, `r14_11_*`.
- [x] T7.9 Cabeçalho sem "livro-caixa pessoal" (R14.12)
  Notas: "controle financeiro" (pedido do operador).
- [x] T7.10 Idioma pt-BR / en (R14.13) — depends on: T7.1–T7.9
  Notas: base i18n (`src/i18n`): cabeçalho, navegação, títulos/descrições de páginas e painéis, selos e formatos (R$ sempre). Textos internos de formulários ainda em português — traduzir acrescentando entradas em `en.ts`. Testes `r14_13_*`.
- [x] T7.11 "A receber" previsto, "Padrão" explicado, ajuda da última compra recorrente (R14.14–R14.16)
  Notas: "Previsto" fora dos totais (janela hoje: este mês + 2, ver T7.18); "Padrão = donos do cartão X — …"; ajuda da última compra. Testes `test_r14_15_*`, `r14_15_*`, `r14_16_*`.
- [x] T7.12 Lançamento em outro mês não some; cor de destaque na cédula, logo e favicon (R14.17, R14.18)
  Notas: lançamento rápido muda o mês da tela e avisa; cédula/logo seguem a cor (p[8]/p[9], AA verificado) e favicon dinâmico. Testes `r14_17_*`, `r14_18_*`.
- [x] T7.13 Parcelamentos: parcela N/M nos lançamentos, quanto falta, terminando, esconder terminados, editar, valor por mês (R14.19–R14.21)
  Notas: `installment` (n/of) nos itens do mês; `GET /api/installment-plans-progress`; `terminando` ≤ 3; terminados escondidos; editar (agenda só em planos manuais, a API recusa nos importados); ações raras em "Mais…". Testes `test_r14_19_*`, `test_r14_20_*`, `test_r14_21_*`.
- [x] T7.14 Data limite do PIX pelo cartão vinculado; trocar meio de pagamento de lançamento manual (R14.22, R14.23)
  Notas: prazo do PIX = vencimento da fatura em que uma compra no cartão no mesmo dia cairia (achado da revisão: antes nascia vencido); trocar meio de pagamento recalcula `provisional`. Testes `test_r14_22_*`, `test_r14_23_*`.
- [x] T7.15 Contas da casa: tipo "Conta da casa" em Assinaturas, vencimento, tela do mês, registrar pagamento, sem dupla contagem (R14.26)
  Notas: assinatura com `group = household` e `due_day`; pagamento vinculado guarda o mês da conta (`links.subscription_month`, achado da revisão: pagar no cartão ou atrasado caía no mês errado); vínculo preservado ao absorver na Revisão; sem dupla contagem. Testes `test_r14_26_*`, `r14_26_*`.
- [x] T7.16 Descrição das categorias; pessoa(s) padrão e Resumo/Projeção por grupo de pessoas (R14.24, R14.25)
  Notas: descrições padrão também preenchidas em instalações existentes (achado da revisão); pessoa(s) padrão em Configurações; `user_id` com vários ids. Testes `test_r14_24_*`, `test_r14_25_*`, `r14_24_*`, `r14_25_*`.
- [x] T7.17 Contas da casa em Gastos recorrentes (renomeado); divisão a partir de um mês (R14.26, R14.27)
  Notas: `RecurringPurchase.group = household` (ocorrência = vencimento; pagar não reancora; `links.recurring_month`); `allocation_history` em assinaturas e gastos recorrentes, editor "Mudanças de divisão". Testes `test_r14_26_*`, `test_r14_27_*`, `r14_27_*`.
- [x] T7.18 A receber por pessoa e período, Previsto por mês e pessoa (3 meses), último reajuste como preço principal (R14.15, R14.28)
  Notas: abas por pessoa (confirmado + previsto, filtra saldos), Vencimento (padrão: próximo mês; vencidos sempre aparecem), totais por pessoa clicáveis; Previsto = este mês + 2; achados da 2ª revisão (conta da casa: pendente/alerta/Desativar pelo mês não pago, linha da Revisão marca o mês sem mover datas, divisão pelo mês da conta). Testes `r14_28_*`, `r14_15_*`, `test_r14_26_*`, `test_r14_27_*`.
- [x] T7.19 Previstos do mês em Lançamentos; próxima data e "todo dia X" em Gastos recorrentes (R14.29, R14.30)
  Notas: painel "Previstos neste mês" (parcelas, assinaturas, recorrentes) a partir de `month-items`; "Próxima" calculada (conta da casa: primeiro vencimento a partir deste mês); "Todo dia X" = a cada 1 mês ancorado no dia X. Testes `r14_29_*`, `r14_30_*`. Achados da 3ª revisão corrigidos: o dia fica guardado (`day_of_month`), compra real em outro dia reancora no dia X mais próximo; "Próxima" pula datas puladas e pausas em todos os tipos; reajustes futuros intermediários contados ("e mais N"). Testes `test_r14_30_*`.
- [x] T7.20 Avisos: fatura apagada não deixa "Fatura faltando"; "sem categoria" diz onde estão os itens (R14.31)
  Notas: um mês passado só fica faltando se o cartão já tinha fatura importada antes dele ou se há lançamento manual nele; aviso de sem categoria com link por tipo de item. Testes `test_r8_9_*` (sync), `r14_31_*`.
- [x] T7.21 Benefício: escolher qual benefício (VR, Home office…) ao pagar com um cartão de benefício, mostrado em Lançamentos (R14.32)
  Notas: seletor "Qual benefício" em lançamento rápido, edição, Assinaturas, Gastos recorrentes e pagamento de Contas da casa; com um benefício já vem escolhido; sem nenhum, a tela explica como ligar; `benefit_id` validado (benefício "cai no cartão" daquele cartão) e em uso não pode ser apagado; trocar cartão/meio limpa. Rótulo "Cartão de benefícios". Testes `test_r14_32_*`, `r14_32_*`.
- [x] T7.22 Resumo: destacar o mês atual no Resumo anual; tirar "Cartões e contas"; renomear "Renda comprometida" e mostrar todas as pessoas (R14.33)
  Notas: "Gasto por pessoa" usa `projection.people` (todas as pessoas; com filtro de pessoa, só as filtradas — a confirmar com o operador); "Cartões e contas" saiu (o banner cobre fatura faltando); mês atual com `aria-current` e cor leve. Testes `test_r14_33_*`, `r14_33_*`.
- [x] T7.23 Gastos recorrentes: coluna Categoria na lista (R14.34)
  Notas: coluna também em Lançamentos → Recorrentes, com "todo dia X". Testes `r14_34_*`.
- [x] T7.25 Resumo anual em duas tabelas (categoria e cartão/conta com benefícios), totais sem e com benefício; validar o grid do Resumo em 1440/1024/768 (R14.36)
  Notas: rodapé mostra só "Total" quando não há gasto em benefício no ano; em tela estreita a tabela abre rolada até o mês atual e o nome da linha fica fixo. Testes `test_r14_36_*`, `r14_36_*`.
- [x] T7.26 Resumo: "Gasto x renda" compacto; painel Histórico por categoria (uma ou várias, valor e % do total por mês, média), clicável a partir de Gastos por categoria (R14.37)
  Notas: sem escolha = todas as categorias empilhadas; clicar numa categoria troca a seleção por ela (grupo: monta no seletor); % do mês na lista de Gastos por categoria. Testes `test_r14_37_*`, `r14_37_*`.
- [x] T7.27 "Padrão" sem divisão gravada resolve pela regra que casa e, sem regra, pelos donos — nunca "ninguém" (R14.16)
  Notas: resolvido na leitura (`Ledger.default_allocation`), então vale para lançamentos manuais, assinaturas e gastos recorrentes, e para regras criadas depois; divisão explícita vence. Testes `test_r14_16_*`.
- [x] T7.24 Renomear `.yml` → `.yaml` (Taskfile.yaml, compose.yaml, .github/workflows/ci.yaml) e documentar a convenção em docs/12 (R14.35)
  Notas: perfis de banco em `.yml` não são mais lidos (erro "renomeie para .yaml" em Status). Testes `test_r14_35_*`.

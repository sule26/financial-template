# Tasks: Expense Tracker Web

Toda task segue [docs/10-processo-de-desenvolvimento.md](../../docs/10-processo-de-desenvolvimento.md)
e só é marcada `[x]` quando o [Definition of Done](../../docs/10-processo-de-desenvolvimento.md#definition-of-done)
está completo. Cada fase termina num [gate](../../docs/10-processo-de-desenvolvimento.md#gates-por-fase).
A próxima task é a primeira `[ ]` cujas dependências estão todas `[x]`.
Desvios e decisões tomadas durante a task vão numa linha `Notas:` logo abaixo dela.

## Fase 0 — Fundação
- [ ] T0.2 Backend: `pyproject.toml` com versões pinadas, app FastAPI com `/api/health`, pytest + gate de 90%, `Clock` injetável
- [ ] T0.3 Frontend: Vite + React + TS + Mantine + Router + TanStack Query, layout com navegação e banner de alertas globais
- [ ] T0.4 `Dockerfile` multi-stage (build do front → imagem Python não-root), `docker-compose.yml` (dev e uso, porta só em 127.0.0.1, rootfs read-only, `cap_drop: ALL`), `Taskfile.yml` (`test`, `coverage`, `lint`, `trace`, `docs-check`, `ci`, `up`, `down`, `dev`, `build`, `e2e`, `backup`) — depends on: T0.2, T0.3
- [ ] T0.1 Validar a estrutura criada no planejamento (`.gitignore`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `specs/`) com `task docs-check` — depends on: T0.4
- [ ] T0.5 CI (plataforma a confirmar com o operador) rodando `task ci` — depends on: T0.4
- [ ] T0.6 Teste de arquitetura (direção das dependências; `domain` sem I/O) e builders de fixtures — depends on: T0.2

## Fase 1 — Armazenamento e domínio
- [ ] T1.1 `storage`: repositório JSON (cache, lock fcntl, escrita atômica, ordem de gravação, schema_version, migração, backups rotativos, invariantes) (R2) — depends on: T0.6
- [ ] T1.2 `domain`: dinheiro/percentual decimal, `AllocationSpec`, mês de fatura com `billing_history`, `H` por cartão, cartão adicional (R1.1, R1.10) — depends on: T0.6
- [ ] T1.3 `domain`: cronograma de parcelamento (resto na 1ª), status, cancelamento (R1.2, R1.3) — depends on: T1.2
- [ ] T1.4 `domain`: antecipação, desfazer, desconto (R7.1, R7.2, R7.4, R7.5) — depends on: T1.3
- [ ] T1.5 `domain`: assinaturas mensais/anuais (R1.4) — depends on: T1.2
- [ ] T1.6 `domain`: usuários com renda opcional, renda zero, histórico (R1.5, R6.1) — depends on: T1.2
- [ ] T1.7 `domain`: padrões de divisão (fixo com versões, proporcional, fallback), donos/responsável com herança, regras em duas passadas, precedência, arredondamento, saldos, acertos, aviso de mês acertado (R5.3, R6.2–R6.4, R6.7–R6.13) — depends on: T1.6
- [ ] T1.8 `domain`: compras recorrentes por intervalo (previsão, reancoragem, adiar/pular/encerrar) (R12) — depends on: T1.2
- [ ] T1.9 `domain`: meios de pagamento e tipos de conta (crédito, benefício, débito, PIX, transferência, boleto, dinheiro); renda em benefício (R11.1–R11.3) — depends on: T1.2
- [ ] T1.10 `domain`: real x projetado (inclui fatura aberta com `as_of`, manuais previstos, recorrentes, mês faltando), projeção de 12 meses (R1.13), renda comprometida, por meio de pagamento (R8.5, R8.9, R1.9, R11.4, R4.11) — depends on: T1.3–T1.9
- [ ] T1.11 `domain`: investimentos — snapshots, movimentações, saldo, rendimento, distribuição, metas (R9.1–R9.3, R9.5, R9.6) — depends on: T1.7
- [ ] T1.12 `domain` + `storage`: categorias obrigatórias; remoção em uso → `null` em cascata + contagem para o alerta (R1.11, R1.12) — depends on: T1.1
- [ ] T1.13 API CRUD: usuários, padrões de divisão, contas, cartões, categorias (com remoção R1.12), metas, assinaturas, compras recorrentes, parcelamentos, regras, acertos, investimentos (R1.1, R1.4, R1.11, R1.12, R6, R9.1, R12.1) — depends on: T1.1–T1.12
- [ ] T1.14 API de lançamentos: manual/rápido com categoria obrigatória e meio de pagamento, antecipar/desfazer, cancelar plano, "reaplicar regras" com prévia, alertas globais (sem categoria, recorrente não ocorrida, mês faltando) (R10.1, R10.4, R7, R12.4) — depends on: T1.13
- [ ] T1.15 API de segurança: checagem de `Host`, `X-Requested-With` em mutações, sem CORS, logs sem valores (docs/13) — depends on: T0.2

## Fase 2 — Telas e painéis
- [ ] T2.1 Cadastros: usuários/renda, padrões de divisão, contas (tipos), cartões (donos/responsável/adicionais/billing_history), categorias, metas, assinaturas, compras recorrentes, regras + seletor de divisão reutilizável (R1.1, R1.11, R6.7–R6.10, R12.1)
- [ ] T2.2 Lançamento rápido global (R10.1, R10.2)
- [ ] T2.3 Lançamentos: lista com filtros (meio de pagamento, sem categoria, previstos), parcelamento manual, antecipar, recategorizar em lote, avisos de recorrente (R1.12, R7, R12.4)
- [ ] T2.4 Resumo: pizza por categoria, gasto x renda, empilhado por cartão, por meio de pagamento, resumo anual, metas, renda comprometida, filtro confirmados/pendentes (R1.6, R1.7, R1.9, R5.5, R11.4)
- [ ] T2.5 Projeção 12 meses, com meses reais/projetados/faltando (R1.6, R1.13, R8.5, R8.9)
- [ ] T2.6 A receber: saldo por pessoa, detalhe, acertos, meses incompletos (R6.4, R6.5, R6.13)
- [ ] T2.7 Investimentos: cadastro, saldo/aporte/resgate, painel (R9)
- [ ] T2.8 Ajuda: "Como usar" e "Como modificar" (R1.8)

## Fase 3 — Sincronização e importação
- [ ] T3.1 `importing`: texto de PDF (pdfplumber), PDF com senha (pypdf), secrets loader, timeout de parse (R4.5)
- [ ] T3.2 `importing`: leitura de CSV (codificação, separador, colunas, `as_of`) (R4.10)
- [ ] T3.3 `profiles`: schema YAML (pdf e csv), loader, detecção, header (`total`, `amount_due`), seções por cartão, `classify`/`tag`, inferência de ano, plugin Python (R4.1, R4.2, R4.6, R4.7, R4.9) — depends on: T3.1, T3.2
- [ ] T3.4 `profiles`: conferência soma x total, `no_total` (R4.4, R4.9) — depends on: T3.3
- [ ] T3.5 Identificação de cartão/conta e `awaiting_card` + `card_choices` (R4.8) — depends on: T3.3
- [ ] T3.6 Fingerprint (ocorrência, dedupe de extrato) + annotations (R3.5, R3.12) — depends on: T3.5
- [ ] T3.7 `sync`: manifesto, scan (novo/alterado/movido/duplicado/removido), arquivo estável, fila única, watchdog com debounce, scan periódico, recuperação após crash (R3.1–R3.10) — depends on: T3.6
- [ ] T3.8 `sync`: substituição de fatura (inclui aberta → fechada), extratos sobrepostos, cascata de remoção com recriação por id determinístico (R3.11–R3.13, R4.11) — depends on: T3.7
- [ ] T3.9 API de sync/status/jobs e perfis (teste contra arquivo, texto bruto) (R3.10, R4.3) — depends on: T3.8
- [ ] T3.10 Telas Perfis e Status (R4.3, R3.10, R4.8)

## Fase 4 — Revisão e reconciliação
- [ ] T4.1 `review`: staging, sugestões, confirmação (unitária/lote/arquivo), categoria obrigatória, congelamento da divisão (R5.1–R5.3, R1.11)
- [ ] T4.2 Reconciliação: parcelas (1–3), estorno de parcelado (4), parcela esperada ausente (7) (R8.1, R8.2, R8.7, R8.8)
- [ ] T4.3 Reconciliação: antecipação e desconto (5, 6, 8) (R7.3, R7.5)
- [ ] T4.4 Reconciliação: manual previsto × importado (9, 10), compra recorrente (10b), assinatura (11) (R8.3, R8.6, R10.3, R12.3)
- [ ] T4.5 Extrato: pagamento de fatura incl. antecipado e "nada a pagar" (12), transferência interna (13), acerto (14), investimento (15) (R4.9, R6.6, R8.4, R8.10, R9.4)
- [ ] T4.6 Sugestão de regra e anotação órfã (R5.4)
- [ ] T4.7 Tela Revisão (incl. substituição de fatura e `needs_choice`) (R5, R3.11)
- [ ] T4.8 Testes de cenário de [docs/11](../../docs/11-estrategia-de-testes.md#cenários) e de segurança
- [ ] T4.9 E2E (Playwright): soltar arquivo sintético (PDF e CSV) na inbox → revisar → confirmar → remover → recolocar

## Fase 5 — Features extras (a decidir)
- [ ] Orçamento por categoria com alertas
- [ ] Limite comprometido por cartão (parcelas futuras)
- [ ] Detecção automática de assinaturas e compras recorrentes
- [ ] Economia com antecipações
- [ ] Fluxo de caixa mensal (renda − faturas − assinaturas)
- [ ] Relatório por pessoa (PDF/CSV)
- [ ] Backup versionado de `data/` (git interno por importação confirmada)
- [ ] Compras internacionais (IOF/câmbio)
- [ ] Contas com caixa compartilhado (`funding: pooled`) — ver pergunta aberta em docs/08
- [ ] Importar posição de corretora / OFX

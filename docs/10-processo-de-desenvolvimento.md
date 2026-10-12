# 10 — Processo de desenvolvimento (obrigatório)

[← Índice](README.md)

Este projeto é construído **inteiramente por agentes de IA**. Este processo existe para que cada
parte seja pequena, verificável e testada antes da próxima começar. **Nenhuma etapa é opcional.**

## Regras de ouro

1. **Uma task por vez.** Só trabalhe na task indicada (ou na próxima `[ ]` do
   [tasks.md](../specs/expense-tracker-web/tasks.md) cujas dependências estão `[x]`).
2. **Testado parte por parte.** Cada função/módulo é testado isoladamente **antes** de ser usado por
   outro. Não se integra código não testado.
3. **Nada avança com teste vermelho.** Se qualquer teste falha (inclusive de outra task), pare e conserte
   antes de seguir.
4. **Cobertura ≥ 90%** no backend, medida em cada task. Abaixo disso a task não está pronta.
5. **A doc é a especificação.** Implemente o que está em `docs/` e `specs/`. Se precisar mudar o
   comportamento, mude a doc **na mesma mudança** e diga por quê.
6. **Nada de suposição.** Se a doc não responde, pergunte ao operador; não invente regra de negócio.
7. **Tudo roda em Docker.** Não há Python/Node instalados na máquina ([14](14-operacao.md)).
8. **Sem commit/push sem aprovação** do operador.

## Ciclo de uma task

```
 ┌─ 1. Ler ───────────────────────────────────────────────────────────┐
 │  task em tasks.md → requisitos R* citados → páginas de docs/ citadas │
 └──────────────────────────────────────────────────────────────────────┘
          ▼
 ┌─ 2. Planejar ──────────────────────────────────────────────────────┐
 │  listar: arquivos a criar/alterar, funções públicas, casos de teste │
 │  (a partir dos exemplos e tabelas da doc)                            │
 └──────────────────────────────────────────────────────────────────────┘
          ▼
 ┌─ 3. Testes primeiro (contrato) ────────────────────────────────────┐
 │  escrever os testes a partir da DOC, não do código                   │
 │  criar só stubs (assinaturas que levantam NotImplementedError) para │
 │  os imports resolverem; rodar → devem falhar por NotImplementedError│
 │  ou assert (nunca por ImportError/SyntaxError)                       │
 └──────────────────────────────────────────────────────────────────────┘
          ▼
 ┌─ 4. Implementar ───────────────────────────────────────────────────┐
 │  o mínimo para os testes passarem; respeitar camadas (docs/03)       │
 └──────────────────────────────────────────────────────────────────────┘
          ▼
 ┌─ 5. Verificar ─────────────────────────────────────────────────────┐
 │  task test       (suíte inteira, não só a nova)                      │
 │  task coverage   (backend ≥ 90% total e por pacote tocado)           │
 │  task lint       (ruff + mypy + eslint + tsc)                        │
 │  task trace      (todo R* da task tem teste test_r<x>_<y>_*)         │
 └──────────────────────────────────────────────────────────────────────┘
          ▼
 ┌─ 6. Revisar (independente) ────────────────────────────────────────┐
 │  revisor: diff contra a doc → VERDICT: APPROVED | NEEDS_CHANGES      │
 │  refutador: usa a feature como o operador →                          │
 │             REFUTER: BLOCKING | NON-BLOCKING                         │
 │  qualquer P0/P1 (de um ou de outro) → volta ao passo 4               │
 └──────────────────────────────────────────────────────────────────────┘
          ▼
 ┌─ 7. Documentar ────────────────────────────────────────────────────┐
 │  atualizar docs/ se algo mudou; marcar [x] em tasks.md;              │
 │  registrar desvios na seção "Notas" da task                          │
 └──────────────────────────────────────────────────────────────────────┘
```

### Separação de papéis

Quando houver mais de um agente disponível, os passos 3, 4 e 6 são feitos por **sessões diferentes**:

| Papel | Faz | Não faz |
|-------|-----|---------|
| Autor dos testes | Testes a partir da doc e da API pública | Ler a implementação para "testar o que está escrito" |
| Implementador | Código que passa nos testes | Alterar testes para passarem (só com justificativa explícita na doc) |
| Revisor | Revisa diff contra doc, camadas, convenções, segurança | Aprovar sem rodar os testes |
| Refutador | Sobe a app limpa e usa a feature como o operador usaria | Só reler o diff |

Com um único agente: faça os papéis em passadas separadas, nessa ordem, e declare no resumo da task
que a revisão independente ficou pendente.

### Severidade dos achados

| Nível | Significado | Efeito |
|-------|-------------|--------|
| P0 | Comportamento errado, perda/duplicação de dado, regra da doc violada, segurança | Bloqueia |
| P1 | Caso descrito na doc sem teste, bug provável em borda, contradição doc × código | Bloqueia |
| P2 | Melhoria, legibilidade, teste extra desejável | Registrar em `Notas:` da task; não bloqueia |

## Definition of Done

Uma task só é marcada `[x]` quando **todos** os itens são verdadeiros:

- [ ] Todo requisito `R*` citado pela task tem ao menos um teste cujo nome começa com `test_r<x>_<y>_` (ex.: `test_r3_4_removed_file_deletes_transactions`); `task trace` passa.
- [ ] Todo exemplo/tabela das páginas de `docs/` citadas pela task tem teste; o teste cita a seção num comentário (`# docs/07#antecipação`). O revisor confere essa lista.
- [ ] `task test` verde (suíte inteira).
- [ ] `task coverage`: backend ≥ 90% total **e** em cada pacote tocado (`src/expense_tracker/<pacote>/`).
- [ ] Frontend (se tocado): ≥ 80% de linhas nos arquivos tocados, testes da tela e `task build` ok.
- [ ] `task lint` sem erros.
- [ ] Revisão e refutação sem P0/P1 abertos.
- [ ] Docs atualizadas; `task docs-check` sem links quebrados.
- [ ] `tasks.md` atualizado (marcação + `Notas:`).

## Gates por fase

Além do DoD de cada task, uma fase só termina quando passa no gate:

| Fase | Gate |
|------|------|
| 0 | `docker compose up` sobe; `GET /api/health` = 200; `task test`, `task lint`, `task docs-check`, `task trace` rodam; `task ci` (o mesmo conjunto que o CI executa) verde localmente |
| 1 | Todos os exemplos de [07](07-regras-de-negocio.md) e [08](08-divisoes-e-acertos.md) passam; teste de crash do storage passa |
| 2 | Com um conjunto de dados de exemplo (`backend/tests/fixtures/sample_data/`), cada painel bate com valores calculados à mão no próprio teste |
| 3 | Todos os eventos e falhas de [05](05-sincronizacao.md) testados com PDFs sintéticos; perfil de exemplo lê o PDF sintético sem linhas não reconhecidas |
| 4 | Todos os cenários da tabela "Por que não há dupla contagem" ([09](09-revisao-e-reconciliacao.md#por-que-não-há-dupla-contagem)) passam ponta a ponta; testes de segurança ([11](11-estrategia-de-testes.md#segurança)) verdes; e2e Playwright verde |
| 5 | Por feature, conforme o requisito criado |

## Como pedir trabalho ao agente

Modelo de pedido (o operador cola isto):

```
Execute a task T1.3 do specs/expense-tracker-web/tasks.md seguindo docs/10-processo-de-desenvolvimento.md.
```

O agente deve responder no final com:

```
Task: T1.3 — <título>
Requisitos cobertos: R1.2, R1.3 (task trace: ok)
Testes: N novos (arquivo(s)), suíte: X passed
Cobertura: total XX% · pacote(s) tocado(s) XX%
Docs alteradas: <lista ou "nenhuma">
Desvios / decisões: <lista ou "nenhum">
Revisão: VERDICT … · Refutação: REFUTER … (ou "pendente: <motivo>")
```

## Bugs

1. Escreva primeiro um teste que reproduz o bug (vermelho).
2. Corrija.
3. Se o bug era uma regra mal descrita, corrija a doc também.
4. Nunca corrija bug sem teste de regressão.

## Mudança de requisito

1. Edite `requirements.md` (novo `R*` ou alteração com nota).
2. Se for decisão arquitetural, adicione a seção na Rationale do `design.md`.
3. Atualize a(s) página(s) de `docs/`.
4. Crie/ajuste a task em `tasks.md`.
5. Só então implemente, pelo ciclo acima.

## Anti-patterns (proibidos)

- Implementar várias tasks numa mudança só.
- Escrever teste depois do código "para cobrir".
- Ajustar o teste até passar sem entender por que falhava.
- Pular o teste de integração porque "os unitários passam".
- Mock de algo que o projeto controla e que é barato usar de verdade (ex.: storage com `tmp_path`).
- Deixar `TODO` sem task correspondente.
- Doc dizendo uma coisa e código fazendo outra.

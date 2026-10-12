# AGENTS.md

Guia canônico para agentes de IA (Claude Code, Kiro, Cursor, Codex, etc.). Arquivos específicos de
ferramenta (ex.: `CLAUDE.md`) só apontam para cá.

## O projeto

Aplicação web pessoal de controle de gastos (single-user, local, offline). Backend Python 3.11 +
FastAPI; frontend React + TypeScript; dados em JSON. Visão geral: [docs/00-visao-geral.md](docs/00-visao-geral.md).

## Regras obrigatórias

1. **Siga o processo**: [docs/10-processo-de-desenvolvimento.md](docs/10-processo-de-desenvolvimento.md).
   Uma task por vez, testes primeiro, Definition of Done completo antes de marcar `[x]`.
2. **Teste parte por parte**: [docs/11-estrategia-de-testes.md](docs/11-estrategia-de-testes.md).
   Cobertura ≥ 90% no backend. Nada avança com teste vermelho.
3. **A doc é a especificação.** Mudou comportamento → atualize `docs/` e `specs/` na mesma mudança.
   A doc não responde → pergunte ao operador; não invente regra de negócio.
4. **Tudo em Docker, via Taskfile.** Não há Python/Node na máquina e **não há Makefile**. Use `task test`,
   `task coverage`, `task lint`, `task ci` (lista: `task --list`).
5. **Autonomia**: dentro deste repositório o agente pode criar/editar qualquer arquivo e usar Docker
   livremente, sem pedir permissão; nada de Kubernetes/cloud. Detalhe em
   [`.kiro/steering/autonomy.md`](.kiro/steering/autonomy.md) (versionado); resumo: código, testes e Docker sim; infra externa, commit e push não.
6. **Respeite as camadas**: [docs/03-arquitetura.md](docs/03-arquitetura.md#camadas-e-dependências-permitidas).
7. **Convenções**: [docs/12-convencoes.md](docs/12-convencoes.md). Código e comentários em inglês; docs em português.
8. **Segurança**: [docs/13-seguranca.md](docs/13-seguranca.md). Nunca commitar `data/`, `inbox/`, `secrets/`, PDFs reais.
9. **Sem commit ou push sem aprovação** do operador.

## Onde está cada coisa

| Preciso de | Arquivo |
|-----------|---------|
| Próxima task | [specs/expense-tracker-web/tasks.md](specs/expense-tracker-web/tasks.md) |
| Requisitos (R*) | [specs/expense-tracker-web/requirements.md](specs/expense-tracker-web/requirements.md) |
| Decisões e porquês | [specs/expense-tracker-web/design.md](specs/expense-tracker-web/design.md) |
| Índice da documentação | [docs/README.md](docs/README.md) |
| Termos de domínio | [docs/01-glossario.md](docs/01-glossario.md) |

## Como pedir trabalho

```
Execute a task T<n> do specs/expense-tracker-web/tasks.md seguindo docs/10-processo-de-desenvolvimento.md.
```

Responda ao final no formato de relatório de task definido em
[docs/10](docs/10-processo-de-desenvolvimento.md#como-pedir-trabalho-ao-agente).

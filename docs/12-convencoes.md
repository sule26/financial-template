# 12 — Convenções de código

[← Índice](README.md)

## Idioma

| Onde | Idioma |
|------|--------|
| Código, identificadores, comentários, docstrings, mensagens de log/erro, commits | **Inglês** |
| `docs/`, `specs/`, textos da UI | Português |

Termos de domínio no código, em inglês: lançamento = `transaction`, fatura = `invoice`, extrato =
`statement`, parcelamento = `installment plan`, antecipação = `anticipation`, divisão = `allocation`,
padrão de divisão = `split profile`, acerto = `settlement`, responsável = `responsible`,
dono = `owner`, revisão = `review`/`staging`, perfil de banco = `bank profile`.

## Backend (Python 3.11)

- Python **3.11** exato (não 3.12+), em container.
- Layout `src/`: `backend/src/expense_tracker/<módulo>/`. Testes espelham: `backend/tests/<módulo>/`.
- Pydantic v2 para todos os modelos de domínio e da API. Sem `dict` solto atravessando camadas.
- `decimal.Decimal` para dinheiro e percentuais; serializado como string. Proibido `float` para valores.
- Funções do `domain` são puras: recebem tudo por parâmetro (inclusive "hoje" via `Clock`).
- Erros de domínio: exceções próprias (`DomainError` e filhas) mapeadas para HTTP na `api`.
- Tipagem completa; `mypy --strict` no `domain` e no `storage`.
- Lint/format: `ruff` (inclui isort). Linha 100.
- Dependências pinadas com versão exata em `pyproject.toml`; nova dependência exige licença
  permissiva (MIT/BSD/Apache) declarada no PR e registrada em [design.md › Stack](../specs/expense-tracker-web/design.md#stack).

## Frontend (TypeScript)

- `strict: true`. Sem `any`.
- Dados do servidor só via TanStack Query; cliente gerado do OpenAPI em `src/api/`.
- Dinheiro: string vinda da API, formatado com `Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'})`; contas em centavos inteiros quando precisar somar no cliente (evitar ao máximo; o backend calcula).
- Componentes por tela em `src/pages/<Tela>/`; compartilhados em `src/components/`.
- Acessibilidade: todo campo com label, navegação por teclado na tabela de Revisão, contraste AA.
- Lint: eslint + prettier.

## API

- Prefixo `/api`. Recursos no plural (`/api/cards`, `/api/cards/{id}`).
- Erros: `{"error": {"code": "allocation_sum_invalid", "message": "...", "details": {...}}}`.
- Datas ISO; meses `YYYY-MM`; dinheiro string.
- OpenAPI gerado pelo FastAPI é o contrato do frontend.

## Git

- Conventional Commits (`feat(sync): detect moved files by hash`).
- Uma task = um commit (ou poucos), referenciando a task: `feat(domain): installment schedule (T1.3)`.
- Commit e push só com aprovação do operador.

## Arquivos que nunca entram no git

`data/`, `inbox/`, `secrets/`, `profiles/*.yaml` (exceto `profiles/examples/`), PDFs reais,
`.env`, `.claude/`, `.cursor/` e similares. Ver `.gitignore`.

`.kiro/` **é versionado** (steering do projeto, ex.: `.kiro/steering/autonomy.md`): não colocar nele
dados pessoais, segredos nem caminhos absolutos da máquina.

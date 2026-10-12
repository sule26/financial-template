# 03 — Arquitetura

[← Índice](README.md) · Decisões e trade-offs: [design.md](../specs/expense-tracker-web/design.md)

## Visão de componentes

```
 host (Linux)
 ├── ./inbox/{faturas,extratos}/**.pdf   ← eu copio/removo PDFs aqui
 ├── ./profiles/*.yaml                    ← perfis de banco
 ├── ./secrets/pdf-passwords.yaml (0400)  ← senhas de PDF
 └── ./data/*.json                        ← "banco de dados"
          │ bind mounts
          ▼
 ┌──────────────── container único: app ───────────────────────┐
 │ uvicorn (1 worker) · FastAPI                                 │
 │                                                              │
 │  api/        REST /api/*  +  serve o build estático do React │
 │  sync/       watcher (watchdog) + varredura periódica        │
 │  importing/  pdf → texto → perfil → lançamentos brutos        │
 │  profiles/   loader/validador YAML + plugins Python opcionais │
 │  review/     staging, regras padrão, reconciliação            │
 │  domain/     regras puras (sem I/O)                           │
 │  storage/    repositório JSON                                 │
 └──────────────────────────────────────────────────────────────┘
          ▲ http://127.0.0.1:8080 (somente loopback)
       navegador
```

## Camadas e dependências permitidas

```
api ──► review ──► domain
 │        │          ▲
 │        ▼          │
 ├──► sync ──► importing ──► profiles
 │        │
 └────────┴──► storage ──► domain (só modelos)
```

| Módulo | Responsabilidade | Pode importar | Não pode importar |
|--------|------------------|---------------|-------------------|
| `domain` | Modelos Pydantic e regras puras: dinheiro, mês de fatura, parcelas, antecipação, assinaturas, divisões, saldos, projeção | stdlib, pydantic | qualquer outro módulo do projeto; I/O |
| `storage` | Ler/gravar JSON, lock, atomicidade, migração, backup | `domain` | `api`, `sync`, `review`, `importing` |
| `profiles` | Schema e loader de perfis; registry de plugins | `domain` | `storage`, `api` |
| `importing` | PDF → texto → `ParseResult` usando um perfil | `profiles`, `domain` | `storage`, `api` |
| `review` | Staging, regras, reconciliação, confirmação | `domain`, `storage` | `api` |
| `sync` | Manifesto, scan, fila de processamento | `importing`, `review`, `storage`, `domain` | `api` |
| `api` | HTTP, validação, servir frontend | todos | — |

A direção das dependências é verificada em teste (ver [11](11-estrategia-de-testes.md#testes-de-arquitetura)).

## Fluxo de uma importação

```
watchdog/scan ──► fila única ──► sync.process(path)
                                   ├─ sha256, consulta manifesto
                                   ├─ importing.parse(pdf, perfil) → ParseResult
                                   ├─ review.stage(ParseResult)
                                   │     ├─ fingerprint + anotações
                                   │     ├─ regras → divisão/categoria sugeridas
                                   │     └─ reconciliação (planos, assinaturas, faturas)
                                   └─ storage: staging.json + import_manifest.json
eu confirmo na UI ──► api ──► review.confirm() ──► transactions.json
```

Detalhes: [05 — Sincronização](05-sincronizacao.md), [06 — Perfis](06-perfis-de-banco.md),
[09 — Revisão e reconciliação](09-revisao-e-reconciliacao.md).

## Concorrência

- Um processo, um worker uvicorn. Um lock de arquivo (`data/.lock`) impede uma segunda instância.
- Toda importação/remoção passa por uma **fila única** (`asyncio.Queue` com um consumidor).
- Mutações vindas da API usam o mesmo lock de escrita do repositório; leituras usam o cache em memória.

## Frontend

React 18 + TypeScript + Vite. TanStack Query para dados do servidor, React Router, Mantine
(componentes), Recharts (gráficos).

| Página | Função |
|--------|--------|
| (global) | Seletor de mês (abre no mês atual), botão "+" de lançamento rápido, banner de alertas (sem categoria, recorrente não ocorrida, mês faltando, arquivos com erro) |
| Resumo | Pizza por categoria, gasto x renda, empilhado por cartão, por meio de pagamento, resumo anual, renda comprometida |
| Projeção | 12 meses a partir do mês atual (data real), por cartão e total |
| Lançamentos | Lista com filtros; manual; parcelamento; antecipar; recategorizar em lote |
| Revisão | Lançamentos importados pendentes; substituição de fatura |
| A receber | Saldos por pessoa; acertos |
| Investimentos | Saldos, aportes, rendimento |
| Cadastros | Usuários/renda, padrões de divisão, contas, cartões, categorias, metas, assinaturas, compras recorrentes, regras |
| Perfis | Editar e testar perfis de banco |
| Status | Estado de cada arquivo da inbox, último scan, erros |
| Ajuda | Como usar / Como modificar |

Estrutura: `frontend/src/{pages,components,api,hooks}`. O cliente HTTP fica em `src/api/`,
tipado a partir do OpenAPI do backend (gerado, não escrito à mão).

## Ambientes

| Modo | Como | Para quê |
|------|------|----------|
| Dev | `task dev`: backend com reload + Vite dev server com proxy `/api` | desenvolver |
| Uso | `task up`: um container com o build do React servido pelo FastAPI | usar no dia a dia |
| Testes | `task test`: containers descartáveis | CI e validação local |

Comandos: [14 — Operação](14-operacao.md).

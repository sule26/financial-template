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
| (global) | Seletor de mês (abre no mês atual), botão "+" de lançamento rápido, alternância de tema claro/escuro/sistema (R1.14, guardada em `localStorage`), banner de alertas (sem categoria, recorrente não ocorrida, mês faltando, arquivos com erro) |
| Resumo | Pizza por categoria, gasto x renda, empilhado por cartão, por meio de pagamento, resumo anual, renda comprometida |
| Projeção | 12 meses a partir do mês atual (data real), por cartão e total |
| Lançamentos | Lista com filtros; manual; parcelamento; antecipar; recategorizar em lote |
| Revisão | Lançamentos importados pendentes; substituição de fatura |
| A receber | No topo, **Próximos recebimentos** (`/api/reports/receivables`, R13.11): um item por cartão/conta e mês de fatura, ordenado pela data limite (vencimento), separado em Receber e Pagar, com totais e selo "vencido"; abaixo, saldos por pessoa e acertos |
| Investimentos | Saldos, aportes, rendimento |
| Cadastros | Usuários/renda e "Repassar o que deve para" (R13.11), padrões de divisão (modo por versão: percentual ou proporcional à renda, R13.12), contas, cartões, categorias, metas, assinaturas, compras recorrentes, regras |
| Perfis | Modo simples (R13.9): bancos suportados em cards (perfis + exemplos embutidos), testar um arquivo da inbox com o perfil detectado e ler o resultado em linguagem clara (soma x total do banco, linhas não entendidas), passo a passo para banco novo. Editor YAML, validar, salvar e texto bruto ficam em "Modo avançado" |
| Configurações | Tema claro/escuro/sistema e cor de destaque (R13.10), guardados no navegador |
| Status | Estado de cada arquivo da inbox, último scan, erros |
| Ajuda | Como usar / Como modificar |

Estrutura: `frontend/src/{pages,components,api,hooks}`. O cliente HTTP fica em `src/api/`,
tipado a partir do OpenAPI do backend (gerado, não escrito à mão).

### Sistema visual ("Cédula")

O mês é tratado como uma cédula: verde-jade profundo (tinta de cédula, não o "mint" de fintech),
latão só no elemento-assinatura e cinzas grafite levemente esverdeados. Escolhas, rascunho e checagem
de contraste (WCAG AA) ficam em `frontend/src/styles/design-tokens.json`.

| Peça | Onde | O quê |
|------|------|-------|
| Tema Mantine | `src/theme.ts` | Paleta `jade` (primária), `gray`/`dark` próprios (o escuro é um preto-esverdeado, não o claro invertido), `red` carmim, `brass`; radius, sombras em camadas, `autoContrast`, `respectReducedMotion` |
| Tokens CSS | `src/styles/tokens.css` | Variáveis por esquema (`:root[data-mantine-color-scheme=…]`): fundo, superfícies, tinta, positivo/negativo, vidro do header, cédula; fundo com dois brilhos e grão (SVG inline em `data:`, permitido pela CSP) |
| Cor de destaque | `src/lib/accents.ts`, `src/hooks/accent.tsx` | 6 paletas (Esmeralda padrão, Oceano, Violeta, Âmbar, Rubi, Grafite) com a mesma estrutura do jade (7 = preenchido/texto no claro, 4 = texto no escuro). A escolhida vira `primaryColor` do Mantine e sobrescreve `--et-jade`, `--et-jade-tint` e o brilho do fundo por esquema via `<style id="et-accent-vars">` + `data-accent` no `<html>`; guardada em `localStorage` (`expense-tracker-accent`), aplica sem recarregar. AA verificado em `accents.test.ts` |
| Movimento | `src/styles/motion.css` | Keyframes, entrada de página, *stagger*, *press* dos botões e o bloco `prefers-reduced-motion` |
| Shell e componentes | `src/styles/app.css` | CSS global com prefixo `et-` (sem CSS Modules: o jsdom dos testes vê o mesmo DOM) |
| Fontes | `@fontsource-variable/bricolage-grotesque` (títulos, valores) e `@fontsource-variable/manrope` (texto) | Empacotadas pelo Vite (sem CDN; CSP `default-src 'self'`). Dinheiro sempre com `font-variant-numeric: tabular-nums` |

Shell (`components/Layout.tsx`): barra lateral com navegação agrupada (Visão geral, Movimento,
Configuração), ícones `@tabler/icons-react` e um marcador que desliza até o item ativo; header de
vidro (blur) com seletor de mês em pílula, "+ Lançar" (atalho N) e tema; no celular a navegação e o
tema vão para um *drawer*. O banner de alertas mostra os avisos lado a lado em telas largas.

Idioma (R14.13): `src/i18n/` — o texto fica em português no código e `t()`/`<T>` procuram a tradução em
`en.ts` (sem tradução = português, nunca uma chave quebrada). O idioma é escolhido em Configurações,
guardado no navegador (`expense-tracker-language`), vai para `<html lang>` e para os formatadores
(dinheiro sempre em R$; datas `MM/DD/YYYY` e meses `Oct 2026` em inglês). Cabeçalho, navegação, títulos e
descrições de páginas e painéis e os selos de situação passam por `t()`; textos internos de formulários
ainda estão só em português (traduzir = acrescentar entradas em `en.ts` e envolver o texto com `t()`).

Componentes compartilhados em `src/components/ui/` (todas as páginas usam):

| Componente | Uso |
|-----------|-----|
| `MonthField`, `DateField` | Únicos campos de mês/data (R13.13): `MonthPickerInput`/`DatePickerInput` do `@mantine/dates` em pt-BR (`DatesProvider` em `providers.tsx`), exibem `out/2026` e `05/10/2026` e trocam com a API `YYYY-MM`/`YYYY-MM-DD` via `src/lib/dates.ts` (partes locais, nunca `toISOString`); botão limpar quando opcional. Testes usam `pickMonth`/`pickDate` de `src/test/utils.tsx` |
| `PageHeader` | Título da página (h2), *eyebrow*, subtítulo, ações e a faixa de filtros |
| `Panel` | Superfície com título (h3) — `<section aria-label>`; leve elevação no hover |
| `StatCard` | KPI com ícone, valor em *count-up* e variação (`StatDelta`, com texto e não só cor); `variant="note"` é a cédula do mês (guilloché em latão + "série" do mês), o elemento-assinatura do Resumo |
| `MoneyText` | Dinheiro com números tabulares; só negativos em carmim por padrão (`tone="signed"` pinta positivos de jade) |
| `StatusBadge` | Selo único de estado (ponto + texto) por *tone*: success/info/warning/danger/neutral/accent |
| `EmptyState` | Vazio ilustrado (ícone num anel guilloché) com frase e ação opcional |
| `ContentSkeleton` | Esqueleto no lugar do *spinner* (usado por `QueryState`), `role="status"` |
| `ChartTooltip`, `useChartTheme` | Tooltip de vidro e paleta de 10 cores por tema (≥ 3:1 sobre a superfície) + animação de entrada dos gráficos |

**Animações e movimento reduzido.** Um momento orquestrado (a página entra subindo 8 px, os cards
em cascata de 45 ms, o total da cédula conta até o valor) e micro-interações (hover/press, marcador da
navegação, *shimmer* do esqueleto). Regra: `usePrefersMotion()` (`components/ui/motion.ts`) só
devolve `true` quando `matchMedia("(prefers-reduced-motion: no-preference)")` casa — com
`reduce`, sem `matchMedia` ou no jsdom dos testes, o *count-up* e os gráficos mostram o valor final
no primeiro render e o CSS zera durações. Assim os testes nunca esperam animação.

## Ambientes

| Modo | Como | Para quê |
|------|------|----------|
| Dev | `task dev`: backend com reload + Vite dev server com proxy `/api` | desenvolver |
| Uso | `task up`: um container com o build do React servido pelo FastAPI | usar no dia a dia |
| Testes | `task test`: containers descartáveis | CI e validação local |

Comandos: [14 — Operação](14-operacao.md).

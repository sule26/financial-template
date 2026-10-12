# 05 — Sincronização com a pasta

[← Índice](README.md) · Requisitos: R3

## Estrutura da inbox

```
inbox/
├── faturas/
│   └── <qualquer subpasta>/arquivo.pdf
└── extratos/
    └── <qualquer subpasta>/arquivo.pdf
```

A pasta de topo (`faturas/` ou `extratos/`) diz o tipo esperado. Subpastas são livres. O perfil é
detectado pelo conteúdo, não pelo nome ([06](06-perfis-de-banco.md#detecção)).

Ignorados: arquivos ocultos (`.*`), temporários (`~*`, `*.part`, `*.crdownload`), extensões fora de
`.pdf` e `.csv` e symlinks que apontem para fora de `inbox/`. O formato é confirmado pelo perfil (R4.10).

## Manifesto

`data/import_manifest.json`, uma entrada por arquivo conhecido:

```json
{"path": "faturas/bancox/2026-10.pdf", "sha256": "9b1c…", "size": 183224,
 "mtime": "2026-10-12T19:30:00-03:00", "kind": "fatura", "format": "pdf",
 "open_invoice": false, "as_of": null,
 "profile_id": "banco-x-fatura", "card_id": "card_x_black",
 "invoice_month": "2026-10", "closing_date": "2026-10-03", "due_date": "2026-10-10",
 "total": "2345.67", "amount_due": "0.00", "period": null,
 "status": "pending_review", "error": null,
 "duplicate_of": null, "superseded_by": null, "supersedes": null,
 "paid_by_fingerprints": [],
 "tx_fingerprints": ["fp_…", "fp_…"]}
```
Extratos têm `account_id` e `period: {"from": "2026-09-01", "to": "2026-09-30"}` em vez de dados de fatura.

| `status` (código) | Rótulo na UI | Ativo? | Significado |
|-------------------|--------------|:------:|-------------|
| `pending_review` | pendente revisão | sim | Lido; nenhum lançamento confirmado ainda |
| `partially_confirmed` | parcialmente confirmado | sim | Parte confirmada, parte em Revisão |
| `confirmed` | confirmado | sim | Todos confirmados |
| `awaiting_card` | aguardando cartão | não | Perfil ok, mas cartão/conta não identificado (R4.8) |
| `superseded` | substituído | não | Outro PDF do mesmo (cartão, mês) o substituiu (R3.11) |
| `unknown_profile` | perfil desconhecido | não | Nenhum perfil reconheceu |
| `error` | erro | não | Senha errada, perfil inválido, PDF corrompido, timeout; ver `error` |
| `duplicate` | duplicado | não | Mesmo hash de outro arquivo (`duplicate_of`) |

"Ativo" = seus lançamentos existem em `staging`/`transactions` e contam nos cálculos.

"Fatura paga": `paid_by_fingerprint` aponta para o débito do extrato vinculado (R8.4).

## Algoritmo de varredura

```
scan():
  atual = {path: (size, mtime)} da inbox, ignorando os excluídos
  para cada path novo ou com (size, mtime) diferente do manifesto:
      aguardar tamanho estável (2 leituras com 2 s de intervalo; timeout 60 s → tenta no próximo scan)
      h = sha256(path)
      caso:
        h existe no manifesto com outro path, e esse path sumiu  → MOVIDO
        h existe no manifesto com outro path, e esse path existe → DUPLICADO
        path está no manifesto e h mudou                         → ALTERADO
        path está no manifesto e h igual (só mtime mudou)        → atualiza mtime
        senão                                                    → NOVO
  para cada path do manifesto ausente em `atual` e não tratado como MOVIDO → REMOVIDO
```

| Evento | Ação |
|--------|------|
| NOVO | Parse → resolve cartão/conta → se fatura: verifica [substituição](#substituição-de-fatura) → staging (`pending_review`) |
| ALTERADO | Reparse; [diff por fingerprint](#diff-por-fingerprint) contra a versão anterior do mesmo path |
| MOVIDO | Atualiza `path` no manifesto e em `source.path`; não reprocessa |
| DUPLICADO | `duplicate`; nada importado. Se o original sair, o duplicado é promovido e importado |
| REMOVIDO | Apaga de `staging` e `transactions` tudo com `source.sha256 = h`, aplica a [cascata](#cascata-de-remoção), remove do manifesto. **Anotações ficam** |

## Substituição de fatura

Invariante: no máximo um documento ativo por (cartão principal, `invoice_month`) (R3.11).

Quando um NOVO de fatura resolve para um (cartão, mês) que já tem documento ativo `A` (hash diferente)
— fatura parcial e depois final, reemissão, ou fatura **aberta** (CSV) seguida de outra aberta mais nova ou da fechada:

1. O novo `B` entra como `pending_review` com o aviso `supersedes_candidate: A`; os lançamentos de `B`
   ficam em staging, mas os cálculos continuam usando `A`.
2. Na Revisão: "Substituir a fatura 2026-10 (A) por B?" mostrando o diff (adicionadas/removidas/mantidas).
3. Confirmar: diff por fingerprint (A → B); `A` vira `superseded` (`superseded_by = B`) e recebe a cascata
   pelos removidos; mantidos continuam confirmados, agora apontando para `B`.
4. Recusar: `B` vira `superseded` (`superseded_by = A`), sem lançamentos.

Se `A` for removido da pasta depois, nada muda (já não era ativo). Se `B` for removido, `A` volta a
ser ativo (reprocessado pelo diff B → A).

## Extratos sobrepostos

Extratos não se substituem: cada lançamento entra uma vez por conta (R3.12). Ao importar um extrato,
cada fingerprint que já existe ativo na mesma conta (vindo de outro arquivo) vai para staging com
`review.status = overlap` e nunca é confirmado. Se o arquivo "dono" do lançamento for removido, o
lançamento é transferido para o arquivo que tinha o overlap (sem perder confirmação nem anotação).

## Diff por fingerprint

```
antigos = fingerprints ativos da versão anterior
novos   = fingerprints do novo ParseResult
removidos   = antigos − novos  → apagados (confirmados ou não) + cascata
adicionados = novos − antigos  → staging
mantidos    = antigos ∩ novos  → ficam como estão (confirmados continuam confirmados)
```

## Cascata de remoção

Quando um lançamento importado deixa de existir (arquivo removido, alterado ou substituído), o que
foi derivado dele (R3.13):

| Derivado | Ação |
|----------|------|
| Plano criado a partir da linha (`origin.fingerprint`) | Apagado se nenhuma outra linha ativa referencia o plano; se o plano tem edição minha (categoria, divisão, antecipação), vira `origin: manual` com aviso |
| Vínculo de parcela a plano existente | Some com o lançamento; o mês volta a ser projetado se o documento inteiro saiu |
| `anticipation.linked_fingerprints` | Fingerprint retirado da lista; com a lista vazia a antecipação volta a ser "prevista" (e pode ser desfeita, R7.4) |
| Fatura paga (`paid_by_fingerprint`) | Limpo na fatura correspondente |
| Acerto com `origin.fingerprint` | **Nunca apagado em silêncio**: vira `origin: manual` com aviso "origem removida" |
| Movimentação de investimento com `origin.fingerprint` | Idem acerto |
| Assinatura vinculada | Só o vínculo some; a assinatura fica |
| Anotação | Fica (reaplicada se o fingerprint voltar, R3.5) |

Ao recolocar o PDF, os derivados com id determinístico ([04](04-modelo-de-dados.md#origem-de-objetos-derivados))
são recriados com o mesmo id; acertos e movimentações que viraram `manual` são revinculados se o
fingerprint casar (sem duplicar).

## Gatilhos

| Gatilho | Quando |
|---------|--------|
| Inicialização | Varredura completa antes de aceitar requisições de escrita |
| Watchdog | Evento do sistema de arquivos → `scan()` com debounce de 3 s |
| Periódico | `scan()` a cada `SCAN_INTERVAL_SECONDS` (60) |
| Manual | Botão "Varrer agora" na tela Status (`POST /api/sync/scan`) |
| Perfil salvo / cartão escolhido | Reprocessa arquivos `unknown_profile`, `error`, `awaiting_card` afetados |

O watchdog é otimização; a varredura periódica garante consistência mesmo com eventos perdidos.

## Fila única

Todo processamento (import, reimport, remoção, mover, substituição) passa por uma fila com **um
consumidor**. A API responde ao scan manual com o id do job; o estado aparece na tela Status
(`GET /api/sync/jobs/{id}`).

## Garantias e falhas

| Situação | Comportamento |
|----------|---------------|
| App cai no meio de uma operação | Manifesto é gravado por último; no início, o scan compara manifesto x disco x lançamentos e refaz a operação (idempotente) |
| Senha errada | `error` "senha inválida para perfil X"; nada importado |
| Perfil quebrado | `error` com a mensagem de validação |
| Soma ≠ total da fatura | Importa com aviso `sum_mismatch` |
| Arquivo removido com lançamentos confirmados | Somem (R3.4) + cascata; anotações guardadas |

## Testes obrigatórios deste módulo

Ver [11](11-estrategia-de-testes.md#sync): cada linha das tabelas de status, eventos, cascata e falhas
acima tem pelo menos um teste.

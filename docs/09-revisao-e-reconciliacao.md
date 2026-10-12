# 09 — Revisão e reconciliação

[← Índice](README.md) · Requisitos: R5, R7.3, R7.5, R8

## Revisão

Todo lançamento importado entra em `staging.json` (`review.status`: `pending`, `needs_choice` ou
`overlap`, [04](04-modelo-de-dados.md#stagingjson)). Nada importado vira confirmado sem ação minha.

Na tela Revisão, por arquivo:

- Cabeçalho: perfil, cartão/conta, mês de fatura, total do PDF x soma, avisos
  (`sum_mismatch`, `supersedes_candidate`, `expected_installment_missing`, `unmatched_manual`).
- Tabela editável: data, descrição, valor, categoria, divisão (com origem), tipo (`kind`), vínculo
  sugerido (plano, antecipação, assinatura, fatura paga, acerto, investimento, manual previsto,
  transferência interna).
- Ações: confirmar linha · confirmar selecionadas · confirmar arquivo · aceitar/recusar sugestão ·
  escolher entre candidatos (`needs_choice`) · aprovar/recusar substituição de fatura.
- Toda edição grava uma **anotação** por fingerprint ([04](04-modelo-de-dados.md#annotationsjson)),
  então sobrevive a reimportações e à remoção do PDF.

Confirmar move a linha para `transactions.json`, grava a divisão resolvida (R5.3) e aplica os
vínculos aceitos. Linhas `overlap` não são confirmáveis. Linhas `needs_choice` exigem a escolha antes.

### Sugestão de regra (R5.4)

Quando eu aplico **a mesma edição** — mesma categoria e/ou mesma divisão, comparada depois de resolvida
para o mês do lançamento — a lançamentos com a mesma descrição normalizada em **2 arquivos diferentes**,
aparece "Criar regra: descrição contém `X` → …?". Aceitar cria a regra com a regex escapada da
descrição e `priority` = maior existente + 10.

### Anotações órfãs

Anotação cujo fingerprint não existe mais, mas parecida com um lançamento novo da Revisão
(similaridade de descrição ≥ 0,9, data ±2 dias, valor ±1%, mesmo cartão/conta), gera "Aplicar edição anterior?".

## Reconciliação

Feita quando o arquivo entra na Revisão. Resultado = **sugestões**; viram efeito ao confirmar.
"Descrição similar" = `difflib.SequenceMatcher` sobre as descrições normalizadas, ratio ≥ 0,8.
Valores comparados em módulo quando a regra diz "±".

| # | Linha importada | Casa com | Critério | Ao confirmar |
|---|-----------------|----------|----------|--------------|
| 1 | Parcela `n/of`, valor > 0 | Plano existente | mesmo cartão · `of` igual · valor ±R$ 0,01 · descrição similar · `n` esperado no mês ±1 | `installment.plan_id`; divisão do plano (nível 2) |
| 2 | Parcela sem candidato | — | nenhum plano casa | Cria plano (`origin.fingerprint`, id determinístico), `first_invoice_month = mês − (n−1)`; projeta as próximas |
| 3 | Parcela com 2+ candidatos | — | — | `needs_choice` |
| 4 | Estorno (valor < 0) com `n/of` ou descrição similar a plano ativo (R8.7) | Plano | mesmo cartão · descrição similar | `refund` vinculado ao plano (divisão do plano); se `|valor| ≥ restante`, sugere cancelar o plano. **Nunca cria plano** |
| 5 | Linhas da antecipação (fatura de `target_month`) | Plano antecipado | parcelas `n ≥ from_n` (valor > 0) **ou** linha com `tag: anticipation` e valor > 0, descrição similar | Fingerprints em `anticipation.linked_fingerprints`; `amount = Σ vinculadas` |
| 6 | Crédito com `tag: anticipation_discount` (R7.5) | Plano antecipado no mesmo mês | descrição similar ou único plano antecipado no mês | Vinculado ao plano, herda divisão do plano; entra em `anticipation.amount` (subtraindo) |
| 7 | Fatura sem a parcela que o plano esperava (R8.8) | Plano | plano tem cobrança prevista em `M` e nenhuma linha casou | Aviso `expected_installment_missing`: "antecipada no banco" (cria antecipação a partir de n) · "cancelada" (`status_override`) · ignorar |
| 7b | Duas ou mais parcelas do **mesmo** plano na mesma fatura (ex.: 09/10 e 10/10) | Plano | `n` consecutivos, mesmo `of`, descrição similar | Sugere "antecipação feita no banco a partir de n_min+1": cria `anticipation` com `target_month = M` e vincula as linhas |
| 8 | Parcela `n ≥ from_n` em mês **posterior** a `target_month` | Plano antecipado | — | Aviso "antecipação não aconteceu?" com opção de desfazer a antecipação |
| 9 | Linha da fatura ou do extrato | Lançamento manual provisório (R8.6, R10.3) | critérios de [16](16-dia-a-dia.md#casamento-previsto--importado-r103) (mesmo cartão/conta · valor ±1% · data ±3 dias · descrição similar) | Manual apagado; a anotação dele passa para o fingerprint importado |
| 10 | Manual provisório do cartão/conta sem par | — | nenhuma linha casou | Aviso `unmatched_manual`: manter previsto · apagar · marcar definitivo |
| 10b | Compra (importada ou manual) | Ocorrência prevista de compra recorrente (R12.3) | `match_description` ou similaridade ≥ 0,6 · valor ±20% · data ±⌈intervalo/3⌉ | `links.recurring_purchase_id`; divisão/categoria da recorrência; reancora `last_date` |
| 11 | Cobrança recorrente | Assinatura | mesmo cartão · valor ±5% · descrição similar | `subscription_id`; divisão da assinatura; diferença de valor → sugestão de reajuste |
| 12 | Débito de pagamento de fatura (extrato) | Documento de fatura ativo | valor = `amount_due` (±R$ 0,01) · data em [vencimento −10, vencimento +7] — **ou** pagamento antecipado: data entre o fechamento anterior e o vencimento, e a soma dos pagamentos do período = `total` − `amount_due` (±R$ 0,01). Fatura com `amount_due ≤ 0` não espera pagamento | `kind = transfer`; `paid_by_fingerprint` na fatura (lista, se houver mais de um pagamento) |
| 13 | Saída numa conta minha + entrada de mesmo valor noutra conta minha (R8.10) | Lançamento do outro extrato | valor igual · ±2 dias | Ambos `kind = transfer`, `internal_transfer_fingerprint` cruzado |
| 14 | Crédito de pessoa (extrato) | Usuário | remetente casa com `aliases` | Sugestão de acerto `from = usuário`, `to = responsável da conta`, `month = mês do crédito` |
| 15 | Linha com `tag: investment_*` (extrato ou fatura) | Investimento | único investimento com `account_id` da conta (extrato) ou escolha | Extrato: `kind = transfer`; fatura: `kind = investment`; movimentação criada no investimento ([15](15-investimentos.md)) |

Ordem de aplicação: 4, 5, 6, 7b, 1, 2/3, 9, 10b, 11, 12, 13, 14, 15; depois os avisos 7, 8, 10 e o de
recorrente não ocorrida (R12.4). Uma linha só recebe a primeira sugestão que casar, exceto 9 + 10b
(um manual previsto vinculado a uma recorrente passa o vínculo para a linha importada).

Categoria é obrigatória para confirmar (R1.11): linhas sem categoria sugerida ficam destacadas e o
"confirmar arquivo" lista quantas faltam.

### Por que não há dupla contagem

| Risco | Proteção |
|-------|----------|
| Parcela prevista + parcela importada | "Real x projetado" por (cartão, mês) ([07](07-regras-de-negocio.md#real-x-projetado)) |
| Antecipação prevista + linhas reais (com ou sem desconto separado) | Idem; vínculo grava o valor real (5, 6) |
| Assinatura prevista + cobrança real | Idem |
| Lançamento manual + mesma linha na fatura/extrato | Manual é provisório e só conta em mês/período projetado; casamento 9 |
| Compra recorrente prevista + compra real | Prevista só conta em mês projetado; casamento 10b reancora |
| Fatura parcial + fatura final do mesmo mês | Um documento ativo por (cartão, mês) — substituição ([05](05-sincronizacao.md#substituição-de-fatura)) |
| Extratos com período sobreposto | Deduplicação por fingerprint na conta (`overlap`) |
| Gasto no cartão + pagamento da fatura no extrato | Pagamento vira `transfer` (12) |
| Transferência entre contas minhas | Ambas viram `transfer` (13) |
| PIX recebido dos pais contado como renda | Vira `settlement` (14) |
| Aplicação em investimento contada como gasto | `transfer`/`investment` (15) |
| Estorno de parcelado criando plano negativo | Estorno nunca cria plano (4) |
| Mesmo PDF em dois caminhos | Hash igual → `duplicate` ([05](05-sincronizacao.md)) |

Cada linha desta tabela tem um teste de cenário ponta a ponta
([11](11-estrategia-de-testes.md#cenários)).

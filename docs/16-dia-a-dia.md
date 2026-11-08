# 16 — Dia a dia: lançamento manual, meios de pagamento e compras recorrentes

[← Índice](README.md) · Requisitos: R10, R11, R12

## O problema

A fatura do cartão só existe depois que fecha; o extrato, depois que eu exporto. Durante o mês eu
quero registrar cada gasto na hora (com categoria e divisão), e no fim do mês importar o PDF **sem
duplicar** o que já lancei e trazendo só o que faltou.

## Fluxo

```
durante o mês                         fim do mês / fechamento
──────────────                        ───────────────────────
lançamento rápido ──► previsto  ─┐
(categoria, meio,    (provisional)│    PDF na inbox ──► Revisão
 divisão)                         ├──► casamento previsto × importado
compra recorrente ──► ocorrência ─┘      ├─ casou     → importado fica; minhas edições vão para ele;
(a cada 45 dias)      prevista            │              previsto é removido
                                          ├─ só no PDF → entra como novo (o que faltou)
                                          └─ só previsto → aviso "não apareceu"
```

Enquanto o documento não chega, os previstos contam nos painéis (o mês está "projetado",
[07](07-regras-de-negocio.md#real-x-projetado)). Depois que chega, conta só o documento.

## Meios de pagamento (R11)

| Meio (`payment_method`) | Onde fica | Documento que confirma | Previsto? |
|-------------------------|-----------|------------------------|:---------:|
| `credit` | Cartão de crédito (`cards`) | Fatura | sim |
| `benefit` | Conta do tipo `benefit` (VR, VA) | Extrato do benefício | sim |
| `debit` | Conta `checking` | Extrato da conta | sim |
| `pix` | Conta `checking` | Extrato da conta | sim |
| `transfer` / `boleto` | Conta `checking` | Extrato da conta | sim |
| `cash` | Conta `cash` (carteira) | — | não (definitivo, R10.4) |

- **Cartão de benefício** é uma **conta** (`accounts.type = benefit`), não um cartão de crédito: tem
  saldo, créditos mensais do empregador e extrato (PDF/CSV, se o emissor fornecer). Sem extrato, os
  lançamentos manuais são o único registro e sempre contam. Com extrato cobrindo o dia, vale o extrato
  (o manual casa ou vira aviso). `confirm_manual_after_days` (opcional, sem padrão) só silencia o aviso
  "não apareceu no extrato" depois de N dias, marcando o manual como definitivo.
- Cartão de benefício **não tem fechamento nem vencimento** (não há fatura): tem só o **dia de
  renovação** (`accounts.renewal_day`, opcional, R13.17), o dia do mês em que o crédito do benefício
  cai. Por isso ele é cadastrado em Contas (tipo Benefício), nunca em Cartões.
- O crédito do empregador no benefício entra como `kind = income` com `income_type = benefit`
  (renda em benefício), separado da renda em dinheiro em gasto x renda e na renda comprometida
  (que mostra os dois separadamente).
- Lançamentos de cartão de crédito têm `payment_method = credit` implícito; nos extratos, o perfil pode
  classificar o meio (`PIX ENVIADO` → `pix`, `COMPRA CARTAO DEBITO` → `debit`) via `classify`.
- Resumo: filtro e série por meio de pagamento (R11.4).

## Lançamento rápido (R10.1, R10.2)

Atalho global (botão "+" e tecla `N`). Campos, em ordem:

| Campo | Padrão |
|-------|--------|
| Valor | — (obrigatório) |
| Descrição | — (obrigatório); autocompleta descrições já usadas |
| Meio de pagamento | o último usado |
| Cartão / conta | o último usado para esse meio |
| Data | hoje |
| Categoria | sugerida por regra (passada 1) ou pela última categoria usada com essa descrição; obrigatória |
| Divisão | sugerida pela precedência (R5.3); seletor com padrões de divisão |
| Parcelas | 1 (só crédito; >1 cria um plano) |
| Recorrente? | não; "sim" abre o cadastro de compra recorrente já preenchido |

Salvar cria o lançamento `source.type = manual`, `provisional = true` (exceto `cash`), com
`invoice_month` calculado ([07](07-regras-de-negocio.md#mês-de-fatura)). Se esse mês não é o que está
na tela (data futura ou compra depois do fechamento), a app vai para ele e avisa (R14.17).

Depois de salvo, o lançamento manual pode mudar descrição, valor, data, categoria, divisão e também
**meio de pagamento, cartão ou conta** (R14.23, mesmas regras de um novo); o `invoice_month` é
recalculado. Lançamentos importados só mudam classificação (categoria, divisão, tipo, nota).

## Casamento previsto × importado (R10.3)

Linha 9 da tabela de [09](09-revisao-e-reconciliacao.md#reconciliação), aplicada a qualquer meio:

| Critério | Valor |
|----------|-------|
| Mesmo cartão (ou cartão principal) / mesma conta | obrigatório |
| Valor | ±1% (estimado de recorrente: ±20%) |
| Data | ±3 dias (recorrente: ±⌈intervalo/3⌉) |
| Mês de fatura | ±1 |
| Descrição | similaridade ≥ 0,6 — ou ≥ 0,3 se valor e data forem exatos |

- Cada previsto casa com no máximo uma linha e vice-versa; empate → `needs_choice`.
- Ao confirmar: previsto apagado; categoria, divisão e nota dele viram **anotação** do fingerprint
  importado (prevalece sobre a sugestão automática). O valor e a data do PDF mandam.
- Linha importada sem previsto → entra normalmente (é "o que faltou").
- Previsto sem linha → aviso `unmatched_manual`: "manter previsto" (ex.: compra no dia do
  fechamento que caiu na próxima fatura), "apagar", ou "marcar como definitivo" (ex.: o banco agrupou).

Parcelado lançado à mão (ex.: 3x no crédito) cria um plano `origin: manual`; as parcelas importadas
casam com o plano pela linha 1 da reconciliação, não pela linha 9.

## Contas da casa (R14.26)

Luz, água, gás, aluguel, condomínio, internet: cadastre em **Cadastros → Gastos recorrentes** com tipo
**Conta da casa**, intervalo (ex.: a cada 1 mês), um vencimento de referência (ex.: 10/09), meio de
pagamento (boleto/PIX/débito numa conta, ou cartão), divisão (ex.: "Casal"), reajustes quando o valor muda
e **mudanças de divisão** (ex.: "a partir de jan/2027, Casal" — R14.27). Cada ocorrência é um vencimento;
pagar não muda as datas. Assinaturas antigas marcadas como conta da casa continuam na tela. A tela **Contas da casa** mostra,
para o mês escolhido:

| Coluna | Significado |
|--------|-------------|
| Vencimento | dia de vencimento no mês (31 em fevereiro → último dia) |
| Previsto | valor vigente no mês (reajustes); 0 se desativada no mês |
| Pago | soma dos lançamentos vinculados a essa conta no mês |
| Situação | `paga` (há pagamento), `atrasada` (venceu sem pagamento), `pendente`, `desativada` |

"Registrar pagamento" cria um lançamento manual com o valor pago, a data, a categoria, a divisão e o
meio de pagamento da conta, vinculado a ela e ao **mês da conta** (`links.recurring_purchase_id` + `links.recurring_month`; nas
assinaturas antigas `links.subscription_id` + `links.subscription_month` — pagar a conta de outubro no cartão, que cai na fatura de novembro, ou com
atraso em novembro, continua quitando outubro). Num mês com lançamento vinculado a previsão da conta
**não** é somada de novo (o real substitui o previsto); os meses seguintes continuam previstos. Se a
linha do extrato/fatura absorver esse lançamento na Revisão, o vínculo passa para ela. Pagamento de conta
não pode ser parcelado. API: `GET /api/reports/household?month=YYYY-MM` →
`{month, items: [{source, id, description, category_id, payment_method, card_id, account_id,
allocations, due_date, expected, paid, status, transaction_ids}], totals: {expected, paid}}`;
`POST /api/transactions` aceita `recurring_purchase_id` + `recurring_month` (e `subscription_id` +
`subscription_month`). A divisão de cada mês é a vigente nele (R14.27).

Parcelamentos: `GET /api/installment-plans-progress` → por plano `{status, remaining, remaining_amount,
next_n, next_month, next_amount, installment_amount}` (R14.19, R14.21). Um parcelamento importado só muda
descrição, categoria e divisão (`422 imported_readonly` para cartão, valor, parcelas e 1ª fatura, R14.20).
Mudar o meio de pagamento de um lançamento manual recalcula `provisional` (só dinheiro é definitivo).

## Compras recorrentes por intervalo (R12)

Na tela o nome é **Gastos recorrentes** (nem tudo é compra). **Repetir** (R14.30): "de tantos em
tantos" (N dias/semanas/meses a partir da última data) ou "todo dia X do mês" (gravado como a cada 1 mês
com a data no dia X; num mês sem dia X vale o último dia, e a âncora vai para o último mês que tem o dia X,
ex.: 31 → 31/08, 30/09, 31/10). A coluna **Próxima** mostra
a próxima data prevista (a adiada, se houver). Os previstos do mês aparecem também em **Lançamentos →
Previstos neste mês** (R14.29), junto com parcelas e assinaturas, até virarem lançamento.

Diferente de **assinatura** (valor fixo, todo mês ou todo ano, [07](07-regras-de-negocio.md#assinaturas)),
a compra recorrente é algo que eu compro de tempos em tempos, com valor aproximado. Ex.: ração dos
gatos a cada 45 dias.

`data/recurring_purchases.json`:

```json
{"id": "rec_racao", "description": "RACAO GATOS", "match_description": "PETZ|COBASI",
 "estimated_amount": "250.00", "every": {"value": 45, "unit": "days"},
 "last_date": "2026-09-20", "payment_method": "credit", "card_id": "card_x_black", "account_id": null,
 "category_id": "cat_pets", "allocations": {"split_id": "split_casal"},
 "active": true, "skipped_dates": []}
```

### Previsão

```
âncora = rec.next_date ?? rec.last_date
ocorrência k = âncora + k × every      # k = 1, 2… (ou 0, 1… quando next_date foi definido)
                                      # mês: mesmo dia da âncora, limitado ao fim do mês
                                      # (31/01 mensal → 28/02, 31/03, 30/04: não “escorrega”)
cada ocorrência: data → invoice_month pela regra do cartão; vira uma cobrança prevista
```

Exemplo (cartão fechamento 3, vencimento 10; última compra 2026-09-20; a cada 45 dias):

| Ocorrência | Data | Mês de fatura |
|------------|------|---------------|
| 1 | 2026-11-04 | 2026-12 |
| 2 | 2026-12-19 | 2027-01 |
| 3 | 2027-02-02 | 2027-02 |
| 4 | 2027-03-19 | 2027-04 |

Faturas: 2026-11 (0), 2026-12 (1), 2027-01 (1), 2027-02 (1), 2027-03 (0), 2027-04 (1) — às vezes
pula um mês, às vezes cai em meses seguidos (R12.2).

### Reancoragem (R12.3)

Quando uma compra real (manual ou importada) casa com uma ocorrência prevista (descrição casa com
`match_description` ou similaridade ≥ 0,6; valor ±20%; data ±⌈intervalo/3⌉ = ±15 dias):

- a linha é vinculada (`links.recurring_purchase_id`), herda categoria e divisão da recorrência
  (nível 2 da precedência, como plano/assinatura);
- `last_date` passa a ser a **data real**, e todas as próximas ocorrências são recalculadas a partir dela.

Se eu comprar a ração em 2026-10-30 (5 dias antes), a próxima vira 2026-12-14.

### Ocorrência que não aconteceu (R12.4)

Hoje > data prevista + tolerância e nenhuma compra casou → aviso na tela Lançamentos e no Resumo:
"Ração prevista em 2026-11-04 não apareceu" com:

| Ação | Efeito |
|------|--------|
| Adiar | Nova data informada vira a **próxima ocorrência** (`next_date`); as seguintes contam a partir dela |
| Pular | Data em `skipped_dates`; próxima = prevista + intervalo |
| Desativar | Abre um período desativado (`pauses`) a partir da primeira compra que não aconteceu (ou do mês atual); some da projeção e dos avisos (R14.10, R14.11) |
| Ativar | Fecha o período desativado no mês anterior à volta; opcionalmente com a data da próxima compra |

`active = false` (chave "Ativa" em Cadastros) continua existindo para desligar de vez. A data da última
compra no cadastro é a última compra que **aconteceu**; a próxima prevista é ela + o intervalo (R14.14).
Preço com reajustes (`price_history`, R14.9) e períodos desativados se editam em Cadastros.

Enquanto o aviso não é tratado, a ocorrência continua na projeção (prefiro superestimar a esquecer um gasto).

### Na projeção

Ocorrências previstas entram em "real x projetado" junto com parcelas, assinaturas e manuais
previstos: só em meses ainda projetados do cartão/conta; num mês com documento ativo, a compra real
(vinculada ou não) é que conta.

## Testes obrigatórios

Tabela de meios (previsto ou não), lançamento rápido (padrões e sugestões), cada critério do casamento
previsto × importado (incluindo `needs_choice` e os três desfechos do não casado), benefício (crédito do
empregador como renda em benefício; confirmação automática após N dias sem extrato), a tabela de
exemplo da compra recorrente (0/1/2 ocorrências por fatura), reancoragem antecipada e atrasada, e as
três ações do aviso ([11](11-estrategia-de-testes.md#cenários)).

# 08 — Divisões, "a receber" e acertos

[← Índice](README.md) · Requisitos: R5.3, R5.4, R6

## Conceitos

- **Divisão**: cada lançamento tem `allocations` (`AllocationSpec`, [04](04-modelo-de-dados.md#formas-de-divisão-allocationspec)) — lista fixa somando exatamente 100,00% ou um padrão de divisão.
  - 100% meu: `[{eu, 100.00}]`
  - Dividido: `[{eu, 50.00}, {ana, 50.00}]` ou `{"split_id": "split_casal"}`
  - Dos meus pais, mesmo no meu cartão: `[{pais, 100.00}]`
- **Donos** de um cartão/conta: quem divide os gastos dele por padrão.
- **Responsável** de um cartão/conta: quem paga o banco. Os outros devem a ele.
- **Padrão de divisão**: divisão nomeada (ex.: "Casal" 60/40), reutilizável e que muda com o tempo.

## Padrões de divisão

Cadastro uma vez o padrão "Casal" e uso `{"split_id": "split_casal"}` em donos, regras, planos,
assinaturas, investimentos e lançamentos ([04](04-modelo-de-dados.md#split_profilesjson)).

### Modo fixo, com histórico (R6.11)

Cada versão vale a partir de um mês. O percentual usado é o da versão com o maior
`from_month ≤ invoice_month`; mês anterior à primeira versão usa a primeira.

| Versão | De | Eu | Esposa |
|--------|----|----|--------|
| 1 | 2026-01 | 60 | 40 |
| 2 | 2027-03 | 55 | 45 |

Lançamento de 2027-02 → 60/40. De 2027-03 → 55/45. Criar a versão 2 não altera nada antes de 2027-03.

### Modo proporcional à renda (R6.12)

Percentual do membro no mês `M` = `renda(membro, M) ÷ Σ renda(membros, M)`, arredondado a 2 casas;
o resíduo para fechar 100,00 vai para o membro de maior renda (empate: o primeiro de `members`).

Ex.: eu R$ 9.000, esposa R$ 6.000 → 60,00/40,00. Esposa passa a R$ 7.500 em 2027-03 →
54,55/45,45 desde 2027-03.

Se algum membro não tem renda (ou tem `0.00`) em `M`, ou a renda é tão desigual que um percentual
arredonda para `0.00`, usa o fallback (R13.12) e a UI mostra o aviso:

1. a versão **com percentuais** (versão fixa) mais recente com `from_month ≤ M` — "proporção fixa
   usada: renda de X ausente em M";
2. senão, a primeira versão com percentuais do histórico (mesmo aviso);
3. senão, divisão igual entre os membros, resíduo de centavos no primeiro — "divisão igual usada: …".

### Modo por versão (R13.12)

Cada versão do padrão escolhe seu próprio modo: percentual livre (`fixed`) ou proporcional à renda
(`income_proportional`). O modo vigente em `M` é o da versão com maior `from_month ≤ M`. Na versão
proporcional a UI esconde os percentuais (`shares` pode ficar vazio); versões seguintes podem voltar ao
percentual livre. Versões sem `mode` (formato antigo) seguem o `mode` do padrão.

| Versão | De | Modo | Eu | Esposa |
|--------|----|------|----|--------|
| 1 | 2026-01 | fixo | 70 | 30 |
| 2 | 2026-06 | proporcional à renda | — | — |
| 3 | 2027-01 | fixo | 50 | 50 |

Com eu R$ 9.000 e esposa R$ 6.000: lançamento de 2026-05 → 70/30; de 2026-06 a 2026-12 → 60/40 (renda);
de 2027-01 em diante → 50/50. Se a renda da esposa faltar em 2026-09, 2026-09 usa 70/30 (versão fixa
mais recente) com aviso.

### Onde usar

| Lugar | Exemplo |
|-------|---------|
| Donos de conta/cartão | Conta conjunta com `owners = {"split_id": "split_casal"}` |
| Regra | "MERCADO" → `split_casal` |
| Plano / assinatura | Streaming dividido pelo "Casal" |
| Lançamento (edição manual) | Escolher "Casal" no seletor de divisão |

O seletor de divisão na UI oferece: os padrões cadastrados, "só eu", "100% para…" e "personalizada".

## Donos e responsável

| Configuração | Donos | Responsável | Efeito padrão |
|--------------|-------|-------------|---------------|
| Meu cartão | eu 100% | eu | Tudo meu |
| Cartão da conta conjunta | eu 50%, Ana 50% | eu | Tudo dividido; Ana me deve 50% |
| Conta conjunta 60/40 | eu 60%, Ana 40% | Ana | Divisão 60/40; eu devo 60% a Ana |
| Meu cartão que meus pais usam | pais 100% | eu | Tudo dos pais; eles me devem tudo |
| Adicional do meu cartão usado pelos pais | pais 100% (no adicional) | eu (herdado do principal) | Linhas da seção do adicional são dos pais |

- Donos: 1 ou mais, lista fixa somando 100,00 ou padrão de divisão (R6.7, R6.10).
- Responsável: o **responsável principal** é exatamente 1 e pode ser um dos donos ou não (R6.8).
- Vários responsáveis (R14.1): `responsibles` (lista fixa somando 100,00 ou padrão de divisão) diz
  quem paga o banco e quanto. A parte de cada pessoa num lançamento é devida a **cada** responsável
  na proporção dele; a fração que cabe ao próprio responsável não vira dívida. Ex.: compra de 100
  dividida 50/50 entre eu e Ana, paga 60/40 por eu e Ana → Ana me deve 30 (50 × 60%) e eu devo 20 a
  Ana (50 × 40%): líquido, Ana me deve 10 (pagou 40 e consumiu 50). Centavos: resíduo para o
  principal se ele paga, senão para o maior percentual. "Repassar para" (R13.11/R13.14) vale para
  cada responsável. `responsibles = null` = só o principal paga (comportamento de R6.8).
- O que "Padrão" significa (R14.16): na UI, a divisão "Padrão" mostra os donos efetivos do
  cartão/conta ("Padrão = donos do cartão Inter — Eu 100%"); uma regra que casa ainda tem
  precedência.
- Herança (R6.9, R1.10): cartão adicional ← cartão principal ← conta vinculada. Cada campo
  (`owners`, `responsible_user_id`) é herdado separadamente quando `null`; `responsibles` vem
  **junto** com o `responsible_user_id` do mesmo nível (nunca misturado entre níveis).

```
resolve(card):
  chain       = [card, parent(card), account(card or parent)]  # ignorando os ausentes
  owners      = primeiro owners != null na cadeia
  responsible = primeiro responsible_user_id != null na cadeia
  assert owners válidos e responsible definido
```

## Regras padrão

Uma regra tem condições (`when`) e efeitos (`then`). Todas as condições preenchidas precisam casar.

| Condição | Casa quando |
|----------|-------------|
| `description_regex` | regex casa com a descrição normalizada |
| `card_id` / `account_id` | lançamento é daquele cartão/conta |
| `category_id` | categoria resultante da passada 1 (abaixo) |
| `min_amount` / `max_amount` | valor dentro da faixa (inclusive) |

Avaliação em **duas passadas** (determinística):

1. **Categoria**: entre as regras habilitadas com `then.category_id`, a de menor `priority` que casa
   (ignorando a condição `category_id`) define a categoria. Empate de prioridade: menor `id`.
2. **Divisão**: entre as regras habilitadas com `then.allocations`, a de menor `priority` que casa
   (agora considerando `category_id` contra a categoria da passada 1) define a divisão.

## Precedência (R5.3)

Uma lista única, igual para todo o sistema:

| # | Fonte | `allocation_origin` |
|---|-------|---------------------|
| 1 | Anotação manual (`annotations[fingerprint]`) | `manual` |
| 2 | Divisão do plano, assinatura ou compra recorrente vinculado, se definida | `plan:<id>` / `subscription:<id>` / `recurring:<id>` |
| 3 | Regra (passada 2) | `rule:<id>` |
| 4 | Donos próprios do cartão (`card.owners != null`, inclusive adicional) | `owners:card` |
| 5 | Donos herdados (principal/conta) ou da conta do extrato | `owners:account` |

**"Padrão"** (R14.16, relato do operador "ninguém recebe o valor") vale os níveis 3–5: a regra que casa
(passada 2, com a categoria do item) e, sem regra, os donos.
- **Lançamento manual**: resolvido **ao salvar** e gravado (`allocation_origin = rule:<id>` ou `owners:*`),
  como uma linha importada; uma regra criada depois não muda meses já acertados. Escolher "Padrão" de novo
  na edição resolve outra vez com as regras de hoje. Lançamentos antigos salvos sem divisão são gravados
  assim uma vez ao iniciar a app (com backup `padrao-freeze` em `data/.backups/`).
- **Previsões** (assinatura, gasto recorrente, parcelamento) sem divisão: resolvidas na leitura, com as
  regras de hoje; quando a fatura/extrato chega, a linha real é que fica gravada.
- Uma divisão escolhida no item sempre vence a regra.

O nível 5 sempre existe (invariante 5), então todo lançamento tem divisão. Categoria segue
1 (anotação) > 2 (plano/assinatura/recorrente) > 3 (regra, passada 1) > última categoria usada com a
mesma descrição (sugestão) > vazio. Vazio não é confirmável: a categoria é obrigatória (R1.11).

**Confirmação congela a escolha**: ao confirmar, o lançamento grava o `AllocationSpec` resolvido
(lista fixa ou `{split_id}`) e a origem. Mudar donos, regras ou o plano depois não altera lançamentos
confirmados; só a resolução por mês de um `split_id` continua dinâmica (R6.11/R6.12). Para reaplicar
regras a lançamentos já confirmados, há a ação explícita "Reaplicar regras" (com prévia).

## Arredondamento

Dois arredondamentos diferentes, nunca confundir:

| O quê | Regra |
|-------|-------|
| **Percentual** (fixo ou proporcional) | 2 casas; a soma é sempre exatamente 100,00 (validação da lista fixa; resíduo do proporcional como acima) |
| **Valor da parte** | `parte = amount × pct / 100`, arredondado para centavos (ROUND_HALF_EVEN); a diferença de centavos para `amount` vai para o **responsável** se ele estiver na divisão, senão para o maior percentual (empate: primeiro da lista) |

Ex.: R$ 100,00 dividido 33,34 / 33,33 / 33,33 (eu responsável, primeiro) → 33,34 + 33,33 + 33,33.
Ex.: R$ 10,00 dividido 33,34 / 33,33 / 33,33 → 3,33 + 3,33 + 3,33 = 9,99 → o responsável fica com 3,34.

## Saldos

Para cada lançamento que conta como gasto, cada usuário `U ≠ responsável R` deve a `R` sua parte:

```
deve(U → R) += parte(U)
```

Estorno (valor negativo) reduz a dívida da mesma forma. Depois:

```
saldo(A, B) = Σ deve(B → A) − Σ deve(A → B) − Σ acertos(B → A) + Σ acertos(A → B)
saldo > 0 → B deve a A
```

A tela "A receber" mostra o saldo com cada pessoa, detalhe por mês e por lançamento, filtro "só
confirmados" (padrão) ou "incluir Revisão", e marca meses `faltando` como incompletos (R8.9).

Exemplo:

| Lançamento | Cartão (responsável) | Divisão | Efeito |
|------------|----------------------|---------|--------|
| Mercado 200 | conjunto (eu) | eu 50, Ana 50 | Ana me deve 100 |
| Remédio 80 | meu (eu) | pais 100 | Pais me devem 80 |
| Jantar 120 | da Ana (Ana) | eu 50, Ana 50 | Eu devo 60 à Ana |
| Acerto: Ana me pagou 40 | — | — | Saldo eu x Ana: 100 − 60 − 40 = **0** |

### Repassar para (R13.11)

Um usuário pode ter "repassar o que deve para" (`users.collector_user_id`). Então cada parte que ele
deve vai para essa pessoa em vez do responsável:

```
credor(U) = collector(U) se definido (e ≠ U), senão R
deve(U → credor(U)) += parte(U)      (U = R continua sem dívida)
```

Ex.: pais com `collector = Ana`; remédio de R$ 80 no meu cartão, 100% pais → pais devem 80 à **Ana**
(não a mim). Repasse não é transitivo: vale só o coletor do devedor.

**Coletor → responsável (R13.14).** Quando o coletor não é o responsável, ele repassa o valor: gera
também a dívida coletor → responsável, com o mesmo valor, lançamento, cartão/conta, vencimento e mês.
Assim nenhum valor fica sem dono:

```
SE credor(U) ≠ R:  deve(credor(U) → R) += parte(U)
```

No exemplo: pais devem 80 à Ana **e** Ana deve 80 a mim. Se o coletor for o próprio responsável
(remédio no cartão da Ana), só existe a linha pais → Ana.

### Recebimentos por vencimento (R13.11)

`GET /api/reports/receivables?user_id=X&include_pending=false` lista o que X recebe/paga agrupado por
(contraparte, cartão principal ou conta, `invoice_month`) — 2 cartões no mesmo mês = 2 recebimentos;
cartão adicional entra no cartão principal. Dentro do grupo créditos e débitos se compensam; `direction`
é `receive` ou `pay` e `amount` é positivo. Data limite (`due_date`) = vencimento da fatura do cartão:
o do documento ativo daquele mês, senão o previsto pelo `billing_history`. Conta (PIX, débito, boleto)
usa o vencimento da fatura do **cartão principal vinculado** à conta em que uma compra no cartão no mesmo
dia cairia (R14.22; ex.: fechamento 3, vencimento 10 → PIX em 05/10 ou 20/10 vence em 10/11; vários
cartões: o primeiro por id); com vários lançamentos no mesmo recebimento vale o prazo mais tarde; conta
sem cartão vinculado fica sem data limite (`null`, vai para o fim).
Ordem: `due_date`, mês, contraparte.

**Previsto** (R14.15): `forecast.items` traz, no mesmo formato (sem `settled`/`status`), o que as
**previsões** (assinaturas, compras recorrentes, parcelas planejadas) de cartões/contas divididos vão
gerar de dívida, no mês atual e nos 2 próximos (a tela agrupa por mês e por pessoa); `forecast.totals` soma por direção.
Não entra em `items`/`totals`, não pode ser marcado como recebido e some quando a fatura/extrato
do mês chega (aí o lançamento real vira recebimento).

Cada item traz também (R13.16) `settled` = soma dos acertos **vinculados** ao item (mesmo par, na
direção do item — quem paga → quem recebe —, mesmo cartão principal/conta e `invoice_month`),
`remaining = max(amount − settled, 0)` e `status`: `open` (nada acertado), `partial` ou `received`
(`remaining = 0`). `overdue` = `remaining > 0` e `due_date < hoje`. `totals` somam `remaining`.

Acertos **sem vínculo** (`invoice_month = null`, ex.: PIX genérico ou sugerido pelo extrato) **não** são
rateados entre os itens: continuam só no saldo líquido de `/api/reports/balances`; `settled_month_total`
informa os acertos daquele mês entre o par, vinculados ou não (positivo: a contraparte pagou X;
negativo: X pagou). Acertos vinculados contam no saldo líquido como qualquer acerto (pelo `month`).
As linhas de `/api/reports/balances` também trazem `card_id`, `account_id` e `due_date`.

```json
{"user_id": "usr_ana",
 "items": [{"counterparty_user_id": "usr_bia", "direction": "receive", "card_id": "card_main",
            "account_id": null, "invoice_month": "2026-10", "due_date": "2026-10-10",
            "amount": "50.00", "settled": "20.00", "remaining": "30.00", "status": "partial",
            "overdue": true, "settled_month_total": "20.00"},
           {"counterparty_user_id": "usr_bia", "direction": "receive", "card_id": "card_main",
            "account_id": null, "invoice_month": "2026-11", "due_date": "2026-11-10",
            "amount": "20.00", "settled": "0.00", "remaining": "20.00", "status": "open",
            "overdue": false, "settled_month_total": "0.00"}],
 "totals": {"receive": "50.00", "pay": "0.00"}}
```

### Marcar como recebido (R13.16)

`POST /api/reports/receivables/mark-received` cria um acerto vinculado ao recebimento e devolve o
acerto criado (`201`):

```json
{"user_id": "usr_ana", "counterparty_user_id": "usr_bia", "direction": "receive",
 "card_id": "card_main", "account_id": null, "invoice_month": "2026-10", "amount": null}
```

- O item é localizado por (usuário, contraparte, `direction`, cartão — adicional vira o principal — ou
  conta, `invoice_month`), com o mesmo filtro de "A receber" (`include_pending`, padrão `false`).
- Acerto: `from` = quem paga (a contraparte em `receive`, o próprio usuário em `pay`), `to` = quem
  recebe, `amount` = `remaining` se omitido (valor informado pode ser parcial), `date` = hoje,
  `month` = `invoice_month`, `note` = `"Recebimento <cartão ou conta> MM/AAAA"`.
- Erros: usuário inexistente `404 not_found`; item inexistente `404 receivable_not_found`; nada a
  receber (`remaining = 0` e sem `amount`, ou `amount = 0`) `409 already_received`.
- **Desmarcar** = `DELETE /api/settlements/{id}` do acerto criado.

```json
{"id": "set_9", "origin": {"type": "manual"}, "from_user_id": "usr_bia", "to_user_id": "usr_ana",
 "amount": "30.00", "date": "2026-10-12", "month": "2026-10",
 "note": "Recebimento Cartão principal 10/2026", "warnings": [],
 "card_id": "card_main", "account_id": null, "invoice_month": "2026-10"}
```

## Mudanças que afetam meses já acertados (R6.13)

Editar renda (modo proporcional), uma versão de padrão de divisão ou uma divisão confirmada, de forma
que mude o saldo de um mês que já tem acerto (`settlements.month`), mostra antes de salvar:
"isso muda o saldo com Ana em 2026-09 de 0,00 para 12,40". Salvar é permitido; o aviso fica no histórico do saldo.

## Acertos

Registro manual (`settlements.json`) ou sugerido pelo extrato (crédito cujo remetente casa com
`aliases` de um usuário, [09](09-revisao-e-reconciliacao.md#reconciliação)). Tem `from_user_id`,
`to_user_id`, `amount`, `date`, `month` (mês ao qual se refere), nota e `origin`. O lançamento de
origem recebe `kind = settlement` e não conta como renda. Opcionalmente o acerto é vinculado a um
recebimento (`card_id` ou `account_id` + `invoice_month`, R13.16) — é o que "marcar como recebido" grava.

## Testes obrigatórios

Cada linha das tabelas "Donos e responsável", "Precedência" e "Saldos", os dois exemplos de
arredondamento, o algoritmo de duas passadas das regras, a confirmação congelando a divisão e os
exemplos de padrão de divisão (fixo com versões, proporcional, modo por versão, fallback sem renda/renda zero), o repasse (inclusive coletor → responsável, R13.14), os recebimentos por vencimento e o
"marcar como recebido" (R13.16) têm
teste próprio ([11](11-estrategia-de-testes.md#domain)).

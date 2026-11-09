# 07 — Regras de negócio: meses, parcelas, antecipação, assinaturas, projeção

[← Índice](README.md) · Requisitos: R1.2–R1.10, R7, R8.5–R8.9

Todas as regras desta página vivem em `backend/src/expense_tracker/domain/` como **funções puras**
(sem I/O; "hoje" vem de um `Clock` injetado, no fuso `TZ`). Cada exemplo desta página vira um teste.

## Mês de fatura

O mês de fatura de um lançamento é o mês do **vencimento** da fatura em que ele é cobrado.

| Origem | Regra |
|--------|-------|
| Importado de fatura | `invoice_month` = mês do `due_date` lido do PDF (o PDF manda) |
| Manual / projetado em cartão | Regra de fechamento abaixo, usando o `billing_history` vigente — ou o `closing_date` real do PDF, se a fatura daquele mês já foi importada |
| Extrato | Mês da data do lançamento |

Regra de fechamento: a compra na data `d` cai no primeiro fechamento **> d** (compra no próprio dia do
fechamento vai para a fatura seguinte). Vencimento = `due_day` no mesmo mês do fechamento se
`due_day > closing_day`, senão no mês seguinte. Dia inexistente no mês (ex.: 31 em fevereiro) = último
dia do mês. O `billing_history` usado é o de maior `from_month ≤` mês do fechamento candidato; mudar o
fechamento a partir de um mês não altera meses anteriores. Uma troca de fechamento/vencimento pode
fazer um mês ficar **sem fatura** (ex.: de 3/10 para 25/5 a partir de 2026-11: nenhuma fatura vence em
2026-11); esse mês aparece vazio, sem aviso de "faltando".

Exemplos (cartão: fechamento 3, vencimento 10):

| Compra | Fechamento | Vencimento | Mês de fatura |
|--------|-----------|------------|---------------|
| 2026-09-02 | 2026-09-03 | 2026-09-10 | 2026-09 |
| 2026-09-03 | 2026-10-03 | 2026-10-10 | 2026-10 |
| 2026-09-20 | 2026-10-03 | 2026-10-10 | 2026-10 |

Cartão fechamento 25, vencimento 5: compra 2026-09-10 → fecha 2026-09-25 → vence 2026-10-05 → `2026-10`.

Se o banco fechar num dia diferente (feriado), a diferença só aparece no lançamento manual; ela é
resolvida pela reconciliação manual × importado ([09](09-revisao-e-reconciliacao.md#reconciliação)),
que aceita mês ±1.

## Mês corrente de um cartão (`H`)

`H(cartão) = invoice_month(cartão, hoje)` pela regra acima: o mês da fatura que ainda está aberta.
Cada cartão tem o seu `H`. Ex.: fechamento 3; hoje 2026-10-02 → `H = 2026-10`; hoje 2026-10-03 → `H = 2026-11`.

## Parcelamentos

Plano: `total_installments N`, `first_invoice_month M0`, `total_amount`.

`installment_amount` = `total_amount / N` truncado em centavos; a **1ª** parcela leva o resto.
Ex.: 100,00 em 3x → 33,34 + 33,33 + 33,33. Para planos importados vale o valor lido do PDF
(todas as parcelas iguais a ele) e `total_amount = N × valor`.

```
schedule(plan):
  for n in 1..N:
     if plan.status_override.cancelled and n >= from_n: continue
     if plan.anticipation and n >= anticipation.from_n: continue
     yield Installment(n, month = M0 + (n-1), amount = amount_of(n))
  if plan.anticipation:
     yield AnticipationCharge(
        month  = anticipation.target_month,
        amount = anticipation.amount ?? Σ amount_of(n) for n in from_n..N)
```

### Status (R1.3)

Relativo a `H(cartão do plano)`:

| Status | Condição |
|--------|----------|
| `cancelado` | `status_override.status = cancelled` (exibe a partir de qual parcela) |
| (antecipada no banco) | `status_override.status = anticipated_at_bank`: parcelas `n..N` saem da projeção; o status segue as regras abaixo com o cronograma restante |
| `pago` | Todas as cobranças do cronograma em meses `< H` |
| `terminando` | Restam 1, 2 ou 3 cobranças em meses `≥ H` (R14.19) |
| `em andamento` | Restam 3 ou mais |

Uma antecipação conta como **uma** cobrança.

### Estorno de parcelamento (R8.7)

Estorno vinculado a um plano ([09](09-revisao-e-reconciliacao.md#reconciliação)) entra como `refund` na
fatura em que aparece, com a divisão do plano. Se o estorno é ≥ o valor restante do plano, a Revisão
sugere "cancelar o plano a partir da parcela n+1" (`status_override`). Estorno nunca cria plano.

## Antecipação

Quitar as parcelas `k..N` de uma vez.

1. Lançamentos → plano → "Antecipar": `target_month` padrão = primeiro mês `≥ H` sem fatura
   importada daquele cartão; editável, mas **nunca** `< H` (R7.1).
2. Parcela inicial padrão = a primeira cujo mês é `≥ target_month`. Parcela com mês **anterior** ao
   `target_month` não pode ser antecipada: ela já é cobrada na própria fatura (antecipá-la contaria
   duas vezes). Antecipação já vinculada à fatura real não pode ser refeita nem o plano cancelado.
3. Valor: **opcional**. Bancos costumam dar desconto de juros (3 × R$ 100 = R$ 300, mas o banco cobra
   R$ 285). Informado → a projeção usa ele; não informado → soma das parcelas.
4. Efeito: as parcelas `k..N` somem dos meses seguintes; aparece "Antecipação LOJA X (6–10/10)" em `target_month`.
5. Fatura real chegou: linhas vinculadas definem o valor real (`amount = Σ cobranças + Σ créditos de desconto`, R7.5).
6. Desfazer: permitido enquanto `linked_fingerprints` estiver vazio (R7.4).

Exemplo: 10x R$ 150 a partir de 2026-08, antecipado a partir da 6ª para 2026-12, sem valor:

| Mês | Antes | Depois |
|-----|-------|--------|
| 2026-08 … 2026-11 | 150 (1ª–4ª) | 150 (1ª–4ª) |
| 2026-12 | 150 (5ª) | 150 (5ª) + **750** (6ª–10ª) |
| 2027-01 … 2027-05 | 150 (6ª–10ª) | — |

Com fatura real trazendo as parcelas 6–10 (750) e "DESCONTO ANTECIPACAO −65,00": `amount = 685`.

## Assinaturas

| Período | Cobrança prevista |
|---------|-------------------|
| `monthly` | Todo mês de `start_month` até `end_month` (ou sem fim) |
| `annual` | Só no `month_of_year`, a partir de `start_month` |

`start_month`, `end_month` e `month_of_year` referem-se a **mês de fatura**. Reajuste: encerro a
vigência antiga (`end_month`) e crio outra, para não alterar o passado.

## Renda

Valor vigente de uma renda no mês `M` = entrada do histórico dela com o maior `from_month ≤ M`. A renda
do usuário em `M` é a soma das rendas com nome (`incomes`, R14.4; o `income_history` legado conta
como mais uma) + as rendas pontuais de `M` (`one_off_incomes`) + benefícios em conta. Total `0.00` →
sem renda naquele mês. A divisão proporcional à renda (R6.12) usa a mesma soma **sem** as rendas
pontuais: um bônus de dezembro aumenta a renda e a sobra de dezembro, mas não muda quem paga quanto
da casa. Sem pessoa selecionada, Resumo usa a renda da casa (soma de todos, R14.6). Para lançamentos,
`M` = `invoice_month` (a fatura de outubro é comparada com a renda de outubro, mês em que é paga).

## Real x projetado

**Regra central contra dupla contagem** (R8.5). Para cada (cartão principal, mês `M`):

```
doc = documento de fatura ativo (status pending_review | partially_confirmed | confirmed)
      do cartão para M — no máximo um (invariante 6)

usa_real = doc existe  E  (filtro inclui pendentes  OU  doc.status ≠ pending_review)

if usa_real:
     itens = lançamentos de doc (confirmados; + pendentes se o filtro incluir)
     if doc.open_invoice:      # fatura aberta (R4.11)
          itens += manuais provisórios e ocorrências previstas com data > doc.as_of
else:
     itens = schedule(planos) + assinaturas previstas + ocorrências de compras recorrentes
             + manuais provisórios (provisional = true)
```

O mesmo vale para contas com documento (corrente e benefício), por (conta, mês), com "documento" =
extrato cujo `period` cobre o mês inteiro. Extrato cobrindo só parte do mês: dias cobertos usam o real;
dias não cobertos, os manuais provisórios daquele intervalo.

- **Lançamentos manuais com documento são sempre previsão** (R8.6, R10.3): entram só quando o mês/período é projetado.
  Quando o documento chega, a reconciliação casa manual × importado; o manual casado é removido e sua
  anotação passa para o importado; o não casado gera aviso ([16](16-dia-a-dia.md#casamento-previsto--importado-r103)).
- Lançamentos em dinheiro (`cash`) são definitivos e sempre contam.
- Filtro padrão dos painéis: **só confirmados** (R5.5). Com ele, uma fatura ainda em revisão não
  zera o mês: o mês continua projetado até eu confirmar algo dela.

### Mês faltando (R8.9)

`M < H(cartão)` sem documento ativo → o mês é marcado `faltando`: mostra a projeção com destaque
("fatura de 2026-08 não importada"), aparece na tela Status, e os saldos "a receber" daquele mês
ficam marcados como incompletos. O aviso global "Fatura faltando" só aparece quando o cartão já estava em
uso naquele mês (R14.31): há fatura importada de um mês anterior ou um lançamento manual no próprio mês.
Previsões sozinhas ou lançamentos de outros meses não contam (apagar a única fatura do cartão não deixa
aviso).

## Projeção de 12 meses

Sempre **12 meses**, a partir do mês atual pela data real do momento (`Clock`, fuso `TZ`): meses
`C … C+11`, onde `C` = mês corrente do calendário. Para cada cartão, os meses `< H(cartão)` dentro da
janela já são reais (ou `faltando`); dos meses `≥ H`, aplica "real x projetado". A janela anda sozinha quando o
mês vira; não há configuração de tamanho (R1.13).

A projeção é **só de cartões** (R14.2): uma coluna por cartão principal (os adicionais somam no
principal, porque a fatura é uma só) e por cartão de benefício (conta tipo Benefício). Contas corrente e
dinheiro (débito, PIX, boleto, transferência, dinheiro) ficam fora da tabela, dos itens do mês, do gráfico
por categoria e do total, que se chama "Total dos cartões"; esses gastos aparecem no Resumo. A renda
comprometida da projeção (R1.9) continua contando tudo o que a pessoa gastou, inclusive nas contas.
**Pessoas** (R14.25): Resumo e Projeção aceitam uma ou várias pessoas (ex.: eu + esposa: partes e
rendas somadas) e abrem com a pessoa padrão escolhida em Configurações (guardada no navegador; vazio =
a casa); A receber abre como a primeira delas. A API recebe `user_id=usr_eu,usr_ana`.

**A receber por pessoa e período** (R14.28): as abas **Pessoa** ("Todas" ou uma por pessoa) mostram só o
que aquela pessoa tem que pagar, confirmado em aberto e previsto, e filtram também os saldos e **Vencimento** escolhe este mês, o próximo mês (padrão) ou todos em
aberto (pela data limite; sem data limite, pelo mês da fatura). Com todas as pessoas, um cartão por pessoa
mostra quanto ela te deve / você deve e, clicando, filtra só ela. O **Previsto** usa a mesma pessoa e
agrupa este mês e os 2 próximos por mês e por pessoa.

Com uma pessoa selecionada, a tabela e a lista de itens mostram só a parte dela (o item exibe "de R$ X",
o valor inteiro, quando a parte é menor). API: `GET /api/reports/month-items?cards_only=true&user_id=…`.

## Mês em foco e meses anteriores

- Toda tela abre no **mês atual** (`C`, pela data real). Não há "último mês visto" salvo.
- Um seletor de mês permite navegar para meses anteriores (e futuros, na projeção). Ao navegar, o
  cabeçalho mostra "vendo 2026-08 · voltar ao mês atual".
- Meses anteriores **são editáveis**: lançamentos manuais retroativos, recategorizar, mudar divisão,
  confirmar Revisão de faturas antigas, registrar acertos. Não há "mês fechado".
- Edição que muda o saldo de um mês já acertado dispara o aviso de R6.13
  ([08](08-divisoes-e-acertos.md#mudanças-que-afetam-meses-já-acertados-r613)).
- Lançamento manual retroativo em mês que **já tem documento ativo** entra como provisório e passa pela
  reconciliação contra esse documento na hora (casa → absorvido; não casa → aviso "não está na fatura de 2026-08").

## Resumo

| Painel | Cálculo |
|--------|---------|
| Pizza por categoria | Σ gasto do mês selecionado por categoria; itens sem categoria (R1.12) aparecem como "Sem categoria". Clicar numa categoria abre o histórico dela (R14.37) |
| Histórico por categoria (R14.37) | Uma ou várias categorias (abre na maior do mês): por mês, Σ gasto delas e, em cima da barra, a % do gasto do mês; embaixo, a média por mês e a % do total dos 12 meses |
| Gasto x renda | Por mês: gasto das pessoas selecionadas (suas partes) vs renda vigente delas; sem pessoa selecionada, gasto total vs **renda da casa** (soma da renda de todos os usuários, R14.6) |
| Empilhado por cartão | Por mês: Σ gasto por cartão; cada conta aparece como uma série |
| Por meio de pagamento (R11.4) | Por mês: Σ gasto por `payment_method` (crédito, benefício, débito/PIX/transferência/boleto, dinheiro); filtro disponível em todos os painéis |
| Resumo anual (R14.36) | Duas tabelas do ano selecionado: por categoria e por cartão/conta (cartões de benefício marcados). Rodapé: **total sem benefício** (o principal) e total com benefício. O mês atual tem uma cor leve e, em tela estreita, a tabela abre rolada até ele; o nome da linha fica fixo ao rolar |
| Metas de poupança | Meta cumprida no mês = Σ aportes do mês nos investimentos vinculados à meta ([15](15-investimentos.md)); sobra = renda − gasto − aportes |
| Gasto por pessoa (R1.9, R14.33) | Todas as pessoas: a parte de cada uma nos gastos do mês; quem tem renda mostra também a renda comprometida, quem não tem mostra "sem renda cadastrada". Por usuário com renda, por mês: `Σ parte do usuário nos gastos ÷ renda vigente`. Meses futuros usam a projeção. Gastos no benefício são comparados com a renda em benefício e mostrados à parte. Faixas: < 50% verde, 50–80% amarelo, > 80% vermelho (configurável). Na Projeção, só aparece quem tem renda |

O painel "Cartões e contas" saiu do Resumo (R14.33): o banner de avisos já mostra fatura/extrato faltando.

"Gasto" = `kind` que conta como gasto ([04](04-modelo-de-dados.md#transactionsjson)). Com filtro de
usuário, cada lançamento entra com a parte dele (`amount × pct`, arredondado como em
[08](08-divisoes-e-acertos.md#arredondamento)); sem filtro, com o valor cheio.

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
fechamento a partir de um mês não altera meses anteriores.

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
| `cancelado` | `status_override.cancelled` (exibe a partir de qual parcela) |
| `pago` | Todas as cobranças do cronograma em meses `< H` |
| `quase acabando` | Restam 1 ou 2 cobranças em meses `≥ H` |
| `em andamento` | Restam 3 ou mais |

Uma antecipação conta como **uma** cobrança.

### Estorno de parcelamento (R8.7)

Estorno vinculado a um plano ([09](09-revisao-e-reconciliacao.md#reconciliação)) entra como `refund` na
fatura em que aparece, com a divisão do plano. Se o estorno é ≥ o valor restante do plano, a Revisão
sugere "cancelar o plano a partir da parcela n+1" (`status_override`). Estorno nunca cria plano.

## Antecipação

Quitar as parcelas `k..N` de uma vez.

1. Lançamentos → plano → "Antecipar": escolho a parcela inicial (padrão: a primeira com mês `≥ H`).
2. `target_month` padrão = primeiro mês `≥ H` sem fatura importada daquele cartão; editável, mas
   **nunca** `< H` (R7.1).
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

Valor vigente no mês `M` = entrada de `income_history` com o maior `from_month ≤ M`. Sem entrada, ou
valor `0.00` → sem renda naquele mês. Para lançamentos, `M` = `invoice_month` (a fatura de outubro é
comparada com a renda de outubro, mês em que é paga).

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
ficam marcados como incompletos.

## Projeção de 12 meses

Sempre **12 meses**, a partir do mês atual pela data real do momento (`Clock`, fuso `TZ`): meses
`C … C+11`, onde `C` = mês corrente do calendário. Para cada cartão, os meses `< H(cartão)` dentro da
janela já são reais (ou `faltando`); dos meses `≥ H`, aplica "real x projetado". Mostra por cartão, por
categoria, por meio de pagamento e por usuário (aplicando as divisões). A janela anda sozinha quando o
mês vira; não há configuração de tamanho (R1.13).

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
| Pizza por categoria | Σ gasto do mês selecionado por categoria; itens sem categoria (R1.12) aparecem como "Sem categoria" |
| Gasto x renda | Por mês: gasto do usuário selecionado (sua parte) vs renda vigente |
| Empilhado por cartão | Por mês: Σ gasto por cartão; cada conta aparece como uma série |
| Por meio de pagamento (R11.4) | Por mês: Σ gasto por `payment_method` (crédito, benefício, débito/PIX/transferência/boleto, dinheiro); filtro disponível em todos os painéis |
| Resumo anual | Σ gasto por categoria × mês do ano selecionado, com total |
| Metas de poupança | Meta cumprida no mês = Σ aportes do mês nos investimentos vinculados à meta ([15](15-investimentos.md)); sobra = renda − gasto − aportes |
| Renda comprometida (R1.9) | Por usuário com renda, por mês: `Σ parte do usuário nos gastos ÷ renda vigente`. Meses futuros usam a projeção. Gastos no benefício são comparados com a renda em benefício e mostrados à parte. Faixas: < 50% verde, 50–80% amarelo, > 80% vermelho (configurável). Sem renda no mês: não exibe |

"Gasto" = `kind` que conta como gasto ([04](04-modelo-de-dados.md#transactionsjson)). Com filtro de
usuário, cada lançamento entra com a parte dele (`amount × pct`, arredondado como em
[08](08-divisoes-e-acertos.md#arredondamento)); sem filtro, com o valor cheio.

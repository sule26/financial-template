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

Se algum membro não tem renda (ou tem `0.00`) em `M`, usa a **versão de `history` vigente em `M`**
(mesma regra do modo fixo) e a UI mostra "proporção fixa usada: renda de X ausente em M".

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
- Responsável: exatamente 1; pode ser um dos donos ou não (R6.8).
- Herança (R6.9, R1.10): cartão adicional ← cartão principal ← conta vinculada. Cada campo
  (`owners`, `responsible_user_id`) é herdado separadamente quando `null`.

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

## Mudanças que afetam meses já acertados (R6.13)

Editar renda (modo proporcional), uma versão de padrão de divisão ou uma divisão confirmada, de forma
que mude o saldo de um mês que já tem acerto (`settlements.month`), mostra antes de salvar:
"isso muda o saldo com Ana em 2026-09 de 0,00 para 12,40". Salvar é permitido; o aviso fica no histórico do saldo.

## Acertos

Registro manual (`settlements.json`) ou sugerido pelo extrato (crédito cujo remetente casa com
`aliases` de um usuário, [09](09-revisao-e-reconciliacao.md#reconciliação)). Tem `from_user_id`,
`to_user_id`, `amount`, `date`, `month` (mês ao qual se refere), nota e `origin`. O lançamento de
origem recebe `kind = settlement` e não conta como renda.

## Testes obrigatórios

Cada linha das tabelas "Donos e responsável", "Precedência" e "Saldos", os dois exemplos de
arredondamento, o algoritmo de duas passadas das regras, a confirmação congelando a divisão e os
exemplos de padrão de divisão (fixo com versões, proporcional, fallback sem renda/renda zero) têm
teste próprio ([11](11-estrategia-de-testes.md#domain)).

# 04 — Modelo de dados (JSON)

[← Índice](README.md) · Requisitos: R2

## Regras gerais

- Todos os arquivos ficam em `data/` e seguem o envelope:
  ```json
  {"schema_version": 1, "items": [ ... ]}
  ```
- **Dinheiro**: string decimal canônica com ponto e exatamente 2 casas (`"150.00"`, `"-65.00"`), nunca float.
- **Percentual**: string decimal com exatamente 2 casas (`"33.34"`). Toda divisão fixa soma **exatamente** `"100.00"`.
- **Datas** em ISO (`"2026-09-14"`); **meses** como `"YYYY-MM"`.
- **IDs**: prefixo do tipo (`usr_`, `card_`, `acc_`, `tx_`, `plan_`, `split_`, `inv_`…) + ULID.
  Objetos derivados de importação usam id determinístico (ver [Origem](#origem-de-objetos-derivados)).
- Gravação atômica: `arquivo.tmp` → `fsync` → `os.replace` → `fsync` do diretório.
- Ordem de gravação numa operação de sync: dados (`staging`, `transactions`, derivados) primeiro,
  `import_manifest.json` por último. Se a app cair no meio, o scan de inicialização refaz a operação
  ([05](05-sincronizacao.md#garantias-e-falhas)).
- Backup em `data/.backups/<timestamp>/` antes de cada importação e migração (mantém `BACKUPS_KEEP`).
- Migração: ao iniciar, cada arquivo com `schema_version` antigo passa por `migrate_vN_to_vN+1` em sequência. Toda migração tem teste.

## Formas de divisão (`AllocationSpec`)

Onde o modelo aceita uma divisão (donos, regras, planos, assinaturas, investimentos, anotações,
lançamentos), aceita uma de duas formas:

```json
[{"user_id": "usr_eu", "pct": "50.00"}, {"user_id": "usr_ana", "pct": "50.00"}]   // fixa
{"split_id": "split_casal"}                                                        // padrão de divisão
```

O percentual de um `split_id` é resolvido pelo `invoice_month` do lançamento no momento do cálculo
([08](08-divisoes-e-acertos.md#padrões-de-divisão)). A lista fixa nunca muda.

## Arquivos

### users.json
```json
{"id": "usr_eu", "name": "Eu", "aliases": ["FULANO DE TAL"],
 "income_history": [{"from_month": "2026-01", "amount": "8000.00"}]}
```
`income_history` pode ser vazio (renda opcional). Renda `"0.00"` equivale a "sem renda" para cálculos
de proporção e renda comprometida. `aliases`: nomes que aparecem no extrato (sugestão de acerto).

### split_profiles.json
Padrões de divisão reutilizáveis (R6.10–R6.12).
```json
{"id": "split_casal", "name": "Casal", "members": ["usr_eu", "usr_esposa"],
 "mode": "fixed",
 "history": [
   {"from_month": "2026-01", "shares": [{"user_id": "usr_eu", "pct": "60.00"}, {"user_id": "usr_esposa", "pct": "40.00"}]},
   {"from_month": "2027-03", "shares": [{"user_id": "usr_eu", "pct": "55.00"}, {"user_id": "usr_esposa", "pct": "45.00"}]}
 ]}
```
`mode`: `fixed` ou `income_proportional` (nesse caso `history` é o fallback; obrigatório nos dois modos).

### accounts.json
```json
{"id": "acc_conjunta", "name": "Conta conjunta Banco X",
 "type": "checking",
 "owners": {"split_id": "split_casal"},
 "responsible_user_id": "usr_eu",
 "profile_id": "banco-x-extrato",
 "account_hint": "12345-6",
 "confirm_manual_after_days": null}
```
`owners` e `responsible_user_id` são obrigatórios em contas.
`type`: `checking` (conta corrente: débito, PIX, transferência, boleto), `benefit` (VR/VA) ou `cash`
(carteira). `confirm_manual_after_days`: para contas sem extrato em PDF (comum em benefício),
lançamentos manuais viram definitivos após N dias ([16](16-dia-a-dia.md#meios-de-pagamento-r11)).

### cards.json
```json
{"id": "card_x_black", "name": "Banco X Black",
 "parent_card_id": null,
 "account_id": "acc_conjunta",
 "owners": null,
 "responsible_user_id": null,
 "last_digits": ["1234", "9876"],
 "billing_history": [{"from_month": "2026-01", "closing_day": 3, "due_day": 10}],
 "limit": "15000.00",
 "profile_id": "banco-x-fatura"}
```
| Campo | Regra |
|-------|-------|
| `parent_card_id` | Adicional: a fatura é a do cartão-pai; `billing_history`, `limit` e `profile_id` vêm do pai (R1.10) |
| `owners` | `AllocationSpec` ou `null` = herda da conta vinculada (R6.9) |
| `responsible_user_id` | `null` = herda da conta; obrigatório se não houver conta (nem pai) |
| `last_digits` | Finais do físico, virtual etc.; identificam o cartão no PDF |
| `billing_history` | Fechamento/vencimento com vigência por mês; regra em [07](07-regras-de-negocio.md#mês-de-fatura) |

Depois de resolver herança (adicional ← pai ← conta), todo cartão tem donos válidos e exatamente um
responsável ([08](08-divisoes-e-acertos.md#donos-e-responsável)).

### categories.json · savings_goals.json
```json
{"id": "cat_casa", "name": "Casa", "color": "#4C6EF5", "budget": null}
{"id": "goal_reserva", "name": "Reserva", "monthly_amount": "500.00", "user_id": "usr_eu"}
```

**Categoria (tipo de gasto)** — R1.11, R1.12:

- A lista de `categories.json` é a única fonte de categorias; a UI só permite escolher dela (cadastro na tela Cadastros).
- `category_id` é **obrigatório** ao criar lançamento manual e ao confirmar na Revisão (a API rejeita `null` com `422 category_required`).
- Remover uma categoria em uso: a remoção é aceita (sem 409); em `transactions`, `staging`, planos,
  assinaturas, compras recorrentes e anotações o `category_id` vira `null`; regras que **definiam** essa
  categoria ficam com `then.category_id = null` e regras que a usavam como **condição** são desabilitadas
  (`enabled = false`). Tudo isso numa única operação, com backup antes.
- `category_id = null` em item já existente é um estado **válido mas pendente**: aparece no alerta
  global "N itens sem categoria" (banner em todas as telas + contador no menu) com atalho para
  recategorizar em lote (filtro "sem categoria" + seleção múltipla). Nos gráficos entra como "Sem categoria".
- Editar um item sem categoria exige escolher uma antes de salvar qualquer outra alteração.

### transactions.json
Lançamentos **confirmados** e lançamentos **manuais**.
```json
{
  "id": "tx_01J…",
  "fingerprint": "fp_5c1e…",
  "kind": "expense",
  "source": {"type": "import", "sha256": "…", "path": "faturas/bancox/2026-10.pdf", "line": 42},
  "provisional": false,
  "payment_method": "credit",
  "card_id": "card_x_black",
  "account_id": null,
  "purchase_date": "2026-09-14",
  "invoice_month": "2026-10",
  "description": "LOJA X",
  "amount": "150.00",
  "category_id": "cat_casa",
  "installment": {"plan_id": "plan_12", "n": 3, "of": 10},
  "links": {"subscription_id": null, "recurring_purchase_id": null, "investment_id": null,
            "settlement_id": null, "paid_invoice": null, "internal_transfer_fingerprint": null},
  "allocations": {"split_id": "split_casal"},
  "allocation_origin": "owners:account",
  "note": null
}
```

| Campo | Valores / regra |
|-------|-----------------|
| `kind` | `expense`, `refund` (negativo), `fee` (tarifa/juros/IOF), `income`, `transfer`, `settlement`, `investment` |
| `payment_method` | `credit`, `benefit`, `debit`, `pix`, `transfer`, `boleto`, `cash` ([16](16-dia-a-dia.md#meios-de-pagamento-r11)); `credit` exige `card_id`, os demais `account_id` |
| `income_type` | Só em `kind = income`: `cash` (padrão) ou `benefit` (crédito de VR/VA) |
| `category_id` | Obrigatório na criação/confirmação; `null` só após remoção da categoria (R1.12) |
| `source.type` | `import` (veio de PDF) ou `manual` |
| `provisional` | `true` para manual com documento (todo meio exceto `cash`): é previsão até casar com fatura/extrato (R8.6, R10.3) |
| `allocations` | `AllocationSpec` **gravado na confirmação** (R5.3). Mudar donos/regras depois não altera este lançamento |
| `allocation_origin` | `manual`, `plan:<id>`, `subscription:<id>`, `recurring:<id>`, `rule:<id>`, `owners:card`, `owners:account` |
| `links.paid_invoice` | No débito de pagamento de fatura: `{"card_id", "invoice_month"}` |

| `kind` | Conta como gasto | Conta como renda | Conta no total da fatura |
|--------|:---:|:---:|:---:|
| `expense`, `fee` | sim | — | sim |
| `refund` | sim (negativo) | — | sim |
| `income` | — | sim | — |
| `investment` | — | — | sim |
| `transfer`, `settlement` | — | — | — |

### staging.json
Mesmo formato de `transactions.json` mais:
```json
{"review": {"status": "pending",
            "suggestions": [{"type": "link_plan", "plan_id": "plan_12", "score": "0.93"}],
            "warnings": ["sum_mismatch"]}}
```
`review.status`: `pending` (aguarda) · `needs_choice` (ambíguo: escolher plano/investimento) ·
`overlap` (já existe na conta por outro extrato; não será confirmado).

### installment_plans.json
```json
{"id": "plan_12", "origin": {"type": "import", "fingerprint": "fp_…"},
 "card_id": "card_x_black", "description": "LOJA X",
 "total_installments": 10, "first_invoice_month": "2026-08",
 "total_amount": "1500.00", "installment_amount": "150.00",
 "category_id": "cat_casa", "allocations": null,
 "status_override": null,
 "anticipation": {"from_n": 6, "target_month": "2026-12", "amount": "700.00",
                  "linked_fingerprints": ["fp_…", "fp_…"]}}
```
- `total_amount` é a fonte; `installment_amount` é derivado (resto na 1ª parcela, [07](07-regras-de-negocio.md#parcelamentos)). Em planos importados, `installment_amount` = valor lido.
- `status_override`: `null` ou `{"status": "cancelled", "from_n": 5}`.
- `anticipation.linked_fingerprints`: linhas reais vinculadas (vazio = ainda não importada).

### subscriptions.json
```json
{"id": "sub_streaming", "description": "STREAMING", "amount": "39.90",
 "period": "monthly", "month_of_year": null, "card_id": "card_x_black",
 "start_month": "2025-03", "end_month": null, "category_id": "cat_lazer", "allocations": null}
```

### recurring_purchases.json
Compras recorrentes por intervalo (R12). Formato e regras em [16](16-dia-a-dia.md#compras-recorrentes-por-intervalo-r12).

### rules.json
```json
{"id": "rule_7", "priority": 10, "enabled": true,
 "when": {"description_regex": "MERCADO", "card_id": null, "account_id": null,
          "category_id": null, "min_amount": null, "max_amount": null},
 "then": {"category_id": "cat_mercado", "allocations": {"split_id": "split_casal"}}}
```
Algoritmo de avaliação em [08](08-divisoes-e-acertos.md#regras-padrão).

### settlements.json
```json
{"id": "set_3", "origin": {"type": "manual"},
 "from_user_id": "usr_pais", "to_user_id": "usr_eu",
 "amount": "800.00", "date": "2026-10-05", "month": "2026-10", "note": "PIX"}
```
`origin` = `{"type": "import", "fingerprint": …}` quando veio de sugestão do extrato.

### annotations.json
Minhas edições, por fingerprint. Sobrevivem à remoção do PDF (R3.5).
```json
{"fingerprint": "fp_5c1e…", "category_id": "cat_casa",
 "allocations": [{"user_id": "usr_pais", "pct": "100.00"}], "note": "presente", "kind": null,
 "link_choices": {"plan_id": "plan_12"},
 "updated_at": "2026-10-12T19:40:00-03:00"}
```

### card_choices.json
Escolhas de cartão feitas para arquivos `aguardando cartão` (R4.8), por `sha256` e por
`(profile_id, card_hint)` — usadas para não perguntar de novo.

### import_manifest.json
Ver [05](05-sincronizacao.md#manifesto).

### investments.json
Ver [15](15-investimentos.md#modelo-datainvestmentsjson).

## Fingerprint

Identidade estável de um lançamento importado; usada para reaplicar anotações, deduplicar extratos
sobrepostos e calcular o diff quando um documento muda ou é substituído.

```
fp = "fp_" + sha256(join("|",
       source_kind,                    # fatura | extrato
       card_id ou account_id,          # resolvido ANTES do staging (R4.8)
       purchase_date,                  # ISO
       normalize(description),
       amount,                         # forma canônica "150.00"
       installment "n/of" ou "",
       occurrence_index))              # ver abaixo
```

- `normalize`: maiúsculas, sem acento, espaços colapsados, sem o sufixo `NN/NN` de parcela.
- `occurrence_index`: 0, 1, 2… entre linhas com os 6 primeiros campos iguais, na **ordem em que
  aparecem no PDF**. Para extratos, contado dentro do arquivo; a deduplicação entre arquivos (R3.12)
  usa a contagem máxima vista por dia (dois extratos sobrepostos com 2 cafés iguais no mesmo dia → 2, não 4).
- O cartão é resolvido antes do fingerprint: arquivos sem cartão identificado ficam
  `awaiting_card` e não geram lançamentos ([06](06-perfis-de-banco.md#identificação-do-cartão-ou-conta)).

Limite conhecido: se o banco reemitir o PDF com descrição ou valor diferentes, o fingerprint muda;
a Revisão sugere o casamento aproximado ([09](09-revisao-e-reconciliacao.md#anotações-órfãs)).

## Origem de objetos derivados

Planos, acertos e movimentações de investimento criados a partir de uma linha importada guardam
`origin = {"type": "import", "fingerprint": fp}` e têm id determinístico `<prefixo>_` +
`sha256(fp)[:16]`. Assim:

- ao remover o PDF, a cascata sabe o que desfazer ([05](05-sincronizacao.md#cascata-de-remoção));
- ao recolocar o PDF, o objeto é recriado com **o mesmo id**, e as anotações que apontam para ele voltam a valer.

## Invariantes (verificados em teste)

1. Toda divisão fixa soma exatamente `100.00`; todo `split_id` referenciado existe e tem `history` não vazio.
2. Todo lançamento com `source.type = import` tem `source.sha256` presente no manifesto com status ativo.
3. Todo `*_id` referenciado existe (ou a gravação é rejeitada). Exceção única: `category_id = null` em itens cuja categoria foi removida (R1.12).
4. Nenhum float em disco.
5. Depois de resolver herança, todo cartão/conta tem donos válidos e um responsável.
6. No máximo **um** documento de fatura ativo por (`card_id` do cartão principal, `invoice_month`).
7. Fingerprints são únicos por cartão/conta entre lançamentos ativos (staging + transactions).

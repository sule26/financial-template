# 15 — Investimentos

[← Índice](README.md) · Requisitos: R9

Registro do dinheiro investido: quanto tenho em cada aplicação, como evoluiu e quanto foi aporte
versus rendimento. A app é offline: **os saldos são informados por mim** (não há cotação automática).

## Conceitos

| Conceito | Significado |
|----------|-------------|
| Investimento | Uma aplicação: "Reserva CDB Banco X", "Tesouro IPCA 2035", "Ações corretora Y" |
| Snapshot | O saldo do investimento numa data, informado por mim |
| Movimentação | Aporte (`contribution`, dinheiro entrando) ou resgate (`withdrawal`, saindo) |
| Aporte líquido | Σ aportes − Σ resgates |
| Rendimento | Saldo do último snapshot − aporte líquido acumulado até a data dele |

Tipos: `emergency_reserve` (reserva), `fixed_income` (renda fixa), `stocks` (ações), `funds`
(fundos), `pension` (previdência), `crypto`, `other`.

## Modelo (`data/investments.json`)

```json
{"id": "inv_reserva", "name": "Reserva CDB Banco X", "institution": "Banco X",
 "type": "emergency_reserve",
 "owners": {"split_id": "split_casal"},
 "goal_id": "goal_reserva",
 "account_id": "acc_conjunta",
 "snapshots": [{"date": "2026-09-30", "balance": "20150.00"},
               {"date": "2026-10-31", "balance": "20890.00"}],
 "movements": [{"date": "2026-10-05", "type": "contribution", "amount": "500.00",
                "origin": {"type": "import", "fingerprint": "fp_…"}}],
 "closed_at": null}
```

- `owners`: mesma forma de divisão do resto da app ([04](04-modelo-de-dados.md#formas-de-divisão-allocationspec)); define de quem é cada parte do saldo.
- `account_id`: conta de onde costumam sair os aportes (usada na sugestão vinda do extrato).
- `goal_id`: meta de poupança que os aportes cumprem (R9.6).

## Regras

- **Saldo atual** = último snapshot. Sem snapshot: aporte líquido (com aviso "saldo não informado").
- **Saldo numa data passada** = último snapshot até aquela data (para o gráfico de evolução).
- **Parte de cada usuário** = saldo × pct do usuário, resolvido pelo mês do snapshot (mesma lógica dos [padrões de divisão](08-divisoes-e-acertos.md#padrões-de-divisão)).
- **Aporte e resgate não são gasto nem renda.** No extrato, a linha de aplicação vira `kind = transfer`;
  na fatura do cartão (ex.: previdência cobrada no cartão), vira `kind = investment`, que conta no total
  da fatura mas não em gasto, renda comprometida nem "a receber" ([09](09-revisao-e-reconciliacao.md#reconciliação), linha 15).
- Movimentações vindas de importação seguem a [cascata de remoção](05-sincronizacao.md#cascata-de-remoção): nunca são apagadas em silêncio.
- **Meta**: aportes do mês no investimento vinculado contam como cumprimento da meta naquele mês
  ([07 › Resumo](07-regras-de-negocio.md#resumo)).
- Investimento encerrado (`closed_at`) sai do total atual mas continua no histórico.

Exemplo:

| Data | Evento | Valor | Aporte líquido | Saldo | Rendimento |
|------|--------|-------|----------------|-------|------------|
| 2026-09-01 | aporte | 20.000 | 20.000 | — | — |
| 2026-09-30 | snapshot | 20.150 | 20.000 | 20.150 | 150 |
| 2026-10-05 | aporte | 500 | 20.500 | — | — |
| 2026-10-31 | snapshot | 20.890 | 20.500 | 20.890 | 390 |

## Tela Investimentos

- Cards: total investido atual · total por usuário · rendimento acumulado.
- Gráfico de evolução do saldo total (linha) com aportes acumulados por baixo (área).
- Distribuição por tipo (pizza) e por usuário.
- Tabela por investimento: saldo, data do último snapshot (alerta se > 45 dias), aporte líquido, rendimento.
- Ações: novo investimento, "registrar saldo", "registrar aporte/resgate", encerrar.

## Do extrato e da fatura (R9.4)

O perfil classifica as linhas de aplicação/resgate (extrato) e de aporte cobrado no cartão (fatura):

```yaml
classify:
  - {match: 'APLICACAO|APLIC\.', kind: transfer,   tag: investment_contribution}   # extrato
  - {match: 'RESGATE',           kind: transfer,   tag: investment_withdrawal}     # extrato
  - {match: 'PREVIDENCIA',       kind: investment, tag: investment_contribution}   # fatura
```

A Revisão sugere o investimento (o único com `account_id` daquela conta, ou pede para escolher).
Também posso marcar qualquer linha como "aporte em investimento" manualmente.
Ao confirmar, cria a movimentação no investimento.

## Fora de escopo (por enquanto)

Cotação automática, importação de PDF de corretora, cálculo de IR. Candidatos à Fase 5.

## Testes obrigatórios

A tabela de exemplo acima, saldo sem snapshot, investimento encerrado, parte por usuário com padrão de
divisão que muda de versão, e o cenário "aplicação no extrato não conta como gasto"
([11](11-estrategia-de-testes.md#cenários)).

# Expense Tracker Web

Aplicação web pessoal para histórico completo de gastos: cartões, contas, parcelamentos,
assinaturas, renda, investimentos e divisão de gastos entre pessoas. Lê faturas e extratos em PDF
de qualquer banco a partir de uma pasta sincronizada.

> **Estado**: planejamento concluído; implementação começa pela Fase 0
> ([tasks.md](specs/expense-tracker-web/tasks.md)).

## Destaques

- Faturas e extratos em PDF lidos de `inbox/`, com sincronização por hash (adicionar, alterar, mover, remover)
- Perfis de banco em YAML: adicionar um banco sem escrever código
- Revisão antes de confirmar, com divisão e categoria sugeridas
- Divisão de gastos entre pessoas, padrões de divisão (ex.: "Casal" 60/40, que muda com o tempo), conta conjunta, "a receber"
- Antecipação de parcelamentos
- Resumo com gráficos, projeção de 12 meses (sempre a partir do mês atual), resumo anual, renda comprometida
- Lançamento rápido no dia a dia (crédito, VR, débito, PIX, dinheiro) que casa com a fatura/extrato sem duplicar
- Compras recorrentes por intervalo (ex.: ração a cada 45 dias)
- Lê PDF e CSV, inclusive fatura ainda aberta; perfis de exemplo para Inter e Nubank
- Investimentos: saldo, aportes, rendimento
- Dados em JSON, offline, só na sua máquina

Lista completa: [docs/02-funcionalidades.md](docs/02-funcionalidades.md).

## Documentação

Tudo está em [`docs/`](docs/README.md). Planejamento (requisitos, decisões, tasks) em
[`specs/expense-tracker-web/`](specs/expense-tracker-web/).

Para desenvolver: leia primeiro o [processo de desenvolvimento](docs/10-processo-de-desenvolvimento.md)
e a [estratégia de testes](docs/11-estrategia-de-testes.md). Guia para agentes de IA: [AGENTS.md](AGENTS.md).

## Rodar

Requer apenas Docker. Comandos em [docs/14-operacao.md](docs/14-operacao.md) (disponíveis a partir da Fase 0).

## Origem

Sucessora da planilha Google Sheets do projeto `personal-finance-sheets` (nenhum código reaproveitado).
Ideia inicial: [inicial_idea.md](inicial_idea.md).

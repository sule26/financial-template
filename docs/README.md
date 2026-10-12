# Documentação — Expense Tracker Web

Documentação completa do projeto. Este projeto é desenvolvido **inteiramente por IA (vibecoding)**:
estes arquivos são a fonte de verdade sobre o que o sistema faz, como funciona e como deve ser
construído. Se o código e a doc divergirem, é bug — corrija um dos dois na mesma mudança.

## Por onde começar

| Você quer… | Leia |
|------------|------|
| Entender o que é o projeto | [Visão geral](00-visao-geral.md) |
| Saber o significado de um termo | [Glossário](01-glossario.md) |
| Ver todas as funcionalidades | [Funcionalidades](02-funcionalidades.md) |
| **Desenvolver qualquer coisa** | [Processo de desenvolvimento](10-processo-de-desenvolvimento.md) → [Estratégia de testes](11-estrategia-de-testes.md) |

## Índice

### Produto
- [00 — Visão geral](00-visao-geral.md)
- [01 — Glossário](01-glossario.md)
- [02 — Funcionalidades](02-funcionalidades.md)

### Técnico
- [03 — Arquitetura](03-arquitetura.md)
- [04 — Modelo de dados (JSON)](04-modelo-de-dados.md)
- [05 — Sincronização com a pasta](05-sincronizacao.md)
- [06 — Perfis de banco (leitura de PDF)](06-perfis-de-banco.md)
- [07 — Regras de negócio: meses, parcelas, antecipação, assinaturas, projeção](07-regras-de-negocio.md)
- [08 — Divisões, "a receber" e acertos](08-divisoes-e-acertos.md)
- [09 — Revisão e reconciliação](09-revisao-e-reconciliacao.md)
- [15 — Investimentos](15-investimentos.md)
- [16 — Dia a dia: lançamento manual, meios de pagamento, compras recorrentes](16-dia-a-dia.md)

### Como construir
- [10 — Processo de desenvolvimento (obrigatório)](10-processo-de-desenvolvimento.md)
- [11 — Estratégia de testes (obrigatório)](11-estrategia-de-testes.md)
- [12 — Convenções de código](12-convencoes.md)

### Operar
- [13 — Segurança](13-seguranca.md)
- [14 — Operação: rodar, backup, restaurar, problemas comuns](14-operacao.md)

## Planejamento

Requisitos, decisões arquiteturais (com rationale) e lista de tarefas ficam em
[`specs/expense-tracker-web/`](../specs/expense-tracker-web/):

- [requirements.md](../specs/expense-tracker-web/requirements.md): o quê (requisitos `R*` numerados)
- [design.md](../specs/expense-tracker-web/design.md): por quê (decisões e trade-offs)
- [tasks.md](../specs/expense-tracker-web/tasks.md): plano de execução e estado de cada task

Os documentos técnicos citam os requisitos pelo código (ex.: `R3.4`) para rastreabilidade.

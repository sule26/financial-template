# 02 — Funcionalidades

[← Índice](README.md)

Lista completa, com origem e requisito correspondente em
[requirements.md](../specs/expense-tracker-web/requirements.md).

## Herdadas da planilha antiga

| Funcionalidade | Detalhe | Req. |
|----------------|---------|------|
| Vários cartões | Nome, dono(s), responsável, conta vinculada, dia de fechamento, dia de vencimento, limite | R1.1 |
| Parcelamentos | Parcelas distribuídas automaticamente nos meses de fatura | R1.2 |
| Status do parcelamento | `pago`, `quase acabando` (≤ 2 restantes), `em andamento` | R1.3 |
| Assinaturas | Mensais e anuais | R1.4 |
| Histórico de renda | Mudança de salário vale a partir de um mês, sem alterar o passado | R1.5 |
| Gastos por categoria | Gráfico de pizza | R1.6 |
| Evolução mensal | Barras gasto x renda | R1.6 |
| Gastos por cartão | Barras empilhadas | R1.6 |
| Projeção de 12 meses | Sempre a partir do mês atual (data real); meses anteriores navegáveis e editáveis | R1.6, R1.13 |
| Resumo anual | Por categoria | R1.6 |
| Atualização dinâmica | Categorias e metas de poupança novas aparecem no Resumo sozinhas | R1.7 |
| Ajuda | "Como usar" e "Como modificar" | R1.8 |

## Novas

| Funcionalidade | Detalhe | Req. | Doc |
|----------------|---------|------|-----|
| Banco de dados em JSON | Arquivos legíveis em `data/`, gravação atômica | R2 | [04](04-modelo-de-dados.md) |
| Sincronização com a pasta | Novo, alterado, movido, removido, duplicado; via hash | R3 | [05](05-sincronizacao.md) |
| PDFs de qualquer banco | Perfis YAML adicionáveis sem código, com tela de teste | R4 | [06](06-perfis-de-banco.md) |
| PDF com senha | Senha guardada fora de `data/` | R4.5 | [06](06-perfis-de-banco.md#pdf-com-senha) |
| Revisão antes de confirmar | Editar, confirmar unitário/lote/arquivo | R5 | [09](09-revisao-e-reconciliacao.md) |
| Regras padrão | Divisão e categoria sugeridas automaticamente | R5.3 | [08](08-divisoes-e-acertos.md#regras-padrão) |
| Sugestão de regra | Edição repetida vira sugestão de regra | R5.4 | [09](09-revisao-e-reconciliacao.md) |
| Usuários com renda opcional | Pessoas para atribuir gastos | R6.1 | [08](08-divisoes-e-acertos.md) |
| Divisão por porcentagem | Entre quaisquer usuários, somando 100% | R6.2 | [08](08-divisoes-e-acertos.md) |
| A receber | Quanto cada pessoa me deve, detalhado | R6.3–R6.5 | [08](08-divisoes-e-acertos.md#saldos) |
| Acertos | Registrar pagamentos entre pessoas | R6.4 | [08](08-divisoes-e-acertos.md#acertos) |
| Conta conjunta e vários donos | Cartão/conta com 1+ donos (com %) e 1 responsável; divisão padrão = donos | R6.7–R6.9 | [08](08-divisoes-e-acertos.md#donos-e-responsável) |
| Padrões de divisão | Ex.: "Casal" 60/40, reutilizável; muda a partir de um mês sem alterar o passado; ou proporcional à renda | R6.10–R6.12 | [08](08-divisoes-e-acertos.md#padrões-de-divisão) |
| Renda comprometida | % da renda de cada usuário (com renda) tomada pelos gastos dele, inclusive na projeção | R1.9 | [07](07-regras-de-negocio.md#resumo) |
| Investimentos | Saldos informados ao longo do tempo, aportes/resgates, rendimento, total por tipo e por usuário, vínculo com metas | R9 | [15](15-investimentos.md) |
| Lançamento do dia a dia | Lançamento rápido com categoria e meio de pagamento; vira previsto e casa com a fatura/extrato sem duplicar | R10 | [16](16-dia-a-dia.md) |
| Meios de pagamento | Crédito, VR/VA (benefício), débito, PIX, transferência, boleto, dinheiro; separados nos painéis | R11 | [16](16-dia-a-dia.md#meios-de-pagamento-r11) |
| Compras recorrentes por intervalo | Ex.: ração a cada 45 dias no cartão X; prevista por data, reancorada pela compra real | R12 | [16](16-dia-a-dia.md#compras-recorrentes-por-intervalo-r12) |
| Categorias de uma lista | Obrigatórias; remover uma em uso deixa itens sem categoria + alerta até recategorizar | R1.11, R1.12 | [04](04-modelo-de-dados.md#categoriesjson--savings_goalsjson) |
| Fatura "nada a pagar" | Compras importadas mesmo com total a pagar R$ 0,00 | R4.9 | [06](06-perfis-de-banco.md#fatura-nada-a-pagar-r49) |
| Fatura aberta / CSV | Lê CSV e faturas ainda não fechadas; a fechada substitui sem duplicar | R4.10, R4.11 | [06](06-perfis-de-banco.md#fatura-aberta-e-formatos-tabulares-csv--r410-r411) |
| Cartões adicionais e virtuais | Seções por cartão na fatura, donos próprios | R1.10, R4.7 | [06](06-perfis-de-banco.md#identificação-do-cartão-ou-conta) |
| Acerto sugerido pelo extrato | PIX recebido de uma pessoa vira sugestão | R6.6 | [09](09-revisao-e-reconciliacao.md#reconciliação) |
| Antecipação de parcelamento | Parcelas restantes vão para a próxima fatura | R7 | [07](07-regras-de-negocio.md#antecipação) |
| Sem dupla contagem | Parcela, antecipação, assinatura, pagamento de fatura | R8 | [09](09-revisao-e-reconciliacao.md#reconciliação) |

## Ideias futuras (Fase 5, a decidir)

Orçamento por categoria com alertas · limite comprometido por cartão · detecção automática de
assinaturas · economia com antecipações · fluxo de caixa mensal · relatório por pessoa (PDF/CSV) ·
backup versionado de `data/` · compras internacionais (IOF/câmbio).

Para adicionar uma ideia: crie o requisito em `requirements.md`, a task em `tasks.md` e siga o
[processo](10-processo-de-desenvolvimento.md).

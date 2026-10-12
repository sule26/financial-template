# 01 — Glossário

[← Índice](README.md)

| Termo | Significado | Onde aprofundar |
|-------|-------------|-----------------|
| **Operador** | Eu, a única pessoa que usa a app | [00](00-visao-geral.md) |
| **Usuário** | Pessoa a quem gastos são atribuídos. Renda opcional. Não faz login | [08](08-divisoes-e-acertos.md) |
| **Donos** | Usuários (1 ou mais, cada um com %) de um cartão ou conta; definem a divisão padrão | [08](08-divisoes-e-acertos.md#donos-e-responsável) |
| **Responsável** | O único usuário que paga o banco por um cartão/conta; os demais devem a ele | [08](08-divisoes-e-acertos.md#donos-e-responsável) |
| **Conta conjunta** | Conta com mais de um dono; cartões vinculados herdam os donos | [08](08-divisoes-e-acertos.md#donos-e-responsável) |
| **Cartão** | Cartão de crédito, com fechamento, vencimento e limite | [04](04-modelo-de-dados.md#cardsjson) |
| **Conta** | Conta bancária, origem de extratos | [04](04-modelo-de-dados.md#accountsjson) |
| **Fatura** | PDF da fatura de um cartão | [06](06-perfis-de-banco.md) |
| **Extrato** | PDF de movimentação de uma conta | [06](06-perfis-de-banco.md) |
| **Inbox** | Pasta monitorada com os PDFs (`inbox/faturas`, `inbox/extratos`) | [05](05-sincronizacao.md) |
| **Manifesto** | Registro de cada PDF conhecido: caminho, hash, estado | [05](05-sincronizacao.md#manifesto) |
| **Hash** | SHA-256 do conteúdo do arquivo; identifica mudanças | [05](05-sincronizacao.md) |
| **Perfil de banco** | YAML que ensina a app a ler PDFs de um banco | [06](06-perfis-de-banco.md) |
| **Lançamento** | Uma linha de gasto, estorno, receita, transferência ou acerto | [04](04-modelo-de-dados.md#transactionsjson) |
| **Fingerprint** | Identidade estável de um lançamento, calculada a partir do conteúdo | [04](04-modelo-de-dados.md#fingerprint) |
| **Anotação** | Edição manual minha (divisão, categoria, nota), guardada por fingerprint | [04](04-modelo-de-dados.md#annotationsjson) |
| **Revisão (staging)** | Lançamentos importados aguardando confirmação | [09](09-revisao-e-reconciliacao.md) |
| **Mês de fatura** | Mês do vencimento da fatura em que o lançamento é cobrado | [07](07-regras-de-negocio.md#mês-de-fatura) |
| **Parcelamento (plano)** | Compra em N parcelas, com cronograma | [07](07-regras-de-negocio.md#parcelamentos) |
| **Antecipação** | Quitar parcelas restantes de um plano numa única fatura | [07](07-regras-de-negocio.md#antecipação) |
| **Assinatura** | Cobrança recorrente mensal ou anual | [07](07-regras-de-negocio.md#assinaturas) |
| **Projeção** | Valor previsto de meses futuros (parcelas + assinaturas) | [07](07-regras-de-negocio.md#projeção-de-12-meses) |
| **Divisão (allocation)** | Lista `{usuário, %}` somando 100%, ou referência a um padrão de divisão | [08](08-divisoes-e-acertos.md) |
| **Padrão de divisão** | Divisão nomeada e reutilizável (ex.: "Casal" 60/40), com versões por mês ou proporcional à renda | [08](08-divisoes-e-acertos.md#padrões-de-divisão) |
| **Renda comprometida** | Parte do usuário nos gastos do mês ÷ renda dele no mês | [07](07-regras-de-negocio.md#resumo) |
| **Investimento** | Aplicação com saldos informados (snapshots) e aportes/resgates | [15](15-investimentos.md) |
| **Meio de pagamento** | Crédito, benefício (VR/VA), débito, PIX, transferência, boleto, dinheiro | [16](16-dia-a-dia.md#meios-de-pagamento-r11) |
| **Benefício** | Conta VR/VA com saldo e créditos do empregador | [16](16-dia-a-dia.md#meios-de-pagamento-r11) |
| **Lançamento previsto** | Manual com documento; conta até casar com a fatura/extrato | [16](16-dia-a-dia.md#casamento-previsto--importado-r103) |
| **Compra recorrente** | Compra repetida por intervalo (ex.: 45 dias), reancorada pela compra real | [16](16-dia-a-dia.md#compras-recorrentes-por-intervalo-r12) |
| **Fatura aberta** | Fatura ainda não fechada (geralmente CSV), válida até a data de exportação | [06](06-perfis-de-banco.md#fatura-aberta-e-formatos-tabulares-csv--r410-r411) |
| **Documento ativo** | O único arquivo de fatura que vale para um (cartão, mês) | [05](05-sincronizacao.md#substituição-de-fatura) |
| **Mês corrente (C)** | Mês do calendário pela data real; toda tela abre nele | [07](07-regras-de-negocio.md#mês-em-foco-e-meses-anteriores) |
| **Regra** | Condição que define divisão/categoria padrão | [08](08-divisoes-e-acertos.md#regras-padrão) |
| **A receber** | Saldo que outra pessoa me deve (ou eu devo) | [08](08-divisoes-e-acertos.md#saldos) |
| **Acerto (settlement)** | Pagamento entre usuários que abate o saldo | [08](08-divisoes-e-acertos.md#acertos) |
| **Reconciliação** | Vincular linha importada a plano, antecipação, assinatura ou fatura | [09](09-revisao-e-reconciliacao.md#reconciliação) |
| **Task** | Unidade de trabalho do [tasks.md](../specs/expense-tracker-web/tasks.md) | [10](10-processo-de-desenvolvimento.md) |
| **DoD** | Definition of Done: checklist para uma task estar pronta | [10](10-processo-de-desenvolvimento.md#definition-of-done) |

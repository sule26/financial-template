# Feature: Expense Tracker Web

Aplicação web pessoal (single-user, local) para histórico completo de gastos, substituindo
a planilha Google Sheets do projeto anterior. Nada do código antigo é reaproveitado; apenas
as features são mantidas.

## Glossário

| Termo | Significado |
|-------|-------------|
| Operador | Eu — única pessoa que usa a app. Não há login. |
| Usuário | Pessoa para quem gastos são atribuídos (eu, pais, parceira…). Não faz login. |
| Fatura | PDF de fatura de cartão de crédito. |
| Extrato | PDF de extrato de conta bancária. |
| Mês de fatura | Mês do **vencimento** da fatura em que o lançamento é cobrado (calculado a partir do fechamento do cartão; para importados, lido do PDF). |
| Perfil de banco | Configuração declarativa que ensina a app a ler PDFs de um banco. |
| Divisão (allocation) | Lista `{usuário, %}` somando 100% que define quem paga cada lançamento. |
| Donos | Usuários (1 ou mais, com %) a quem os gastos de um cartão/conta são atribuídos por padrão. |
| Responsável | O único usuário que paga o banco por aquele cartão/conta; os outros devem a ele. |
| Conta conjunta | Conta com mais de um dono; cartões vinculados herdam os donos. |
| Padrão de divisão | Divisão nomeada e reutilizável (ex.: "Casal" 60/40), com histórico por mês ou proporcional à renda. |
| Renda comprometida | Parte do usuário nos gastos do mês ÷ renda dele no mês. |
| Investimento | Aplicação (reserva, renda fixa, ações…) com saldos informados ao longo do tempo e aportes/resgates. |
| Meio de pagamento | Crédito, benefício (VR/VA), débito, PIX, transferência, boleto, dinheiro. |
| Cartão de benefício | VR/VA: conta com saldo e créditos do empregador, separada do cartão de crédito. |
| Compra recorrente | Compra repetida por intervalo (ex.: a cada 45 dias), prevista por data e reancorada pela compra real. |
| Lançamento previsto | Lançado à mão antes do documento; vira definitivo ao casar com a fatura/extrato. |
| Revisão | Área de staging onde lançamentos importados aguardam confirmação. |
| Antecipação | Quitar parcelas futuras de um parcelamento numa única fatura. |

---

## R1 — Features herdadas da planilha

- R1.1 WHEN eu cadastro um cartão THEN the system SHALL guardar nome, dono(s), responsável, conta vinculada (opcional), finais do cartão (físico, virtual, adicionais), dia de fechamento e de vencimento **com histórico por mês** (mudar o fechamento não altera meses passados) e limite (ver R6.7–R6.9).
- R1.10 WHEN um cartão é **adicional** de outro (ex.: adicional usado pelos pais) THEN the system SHALL tratá-lo como cartão próprio com donos próprios, mas cuja fatura é a do cartão principal.
- R1.2 WHEN eu cadastro uma compra parcelada THEN the system SHALL distribuir as parcelas nos meses de fatura corretos (mês do vencimento, calculado a partir do fechamento), com o resto de centavos na 1ª parcela.
- R1.3 WHEN um parcelamento é exibido THEN the system SHALL mostrar o status: `pago` (todas as parcelas em meses passados), `quase acabando` (≤2 parcelas restantes) ou `em andamento`.
- R1.4 WHEN eu cadastro uma assinatura (mensal ou anual) THEN the system SHALL gerar a cobrança prevista nos meses correspondentes.
- R1.5 WHEN a renda de um usuário muda THEN the system SHALL registrar o novo valor com mês de vigência, sem alterar meses anteriores.
- R1.6 WHEN eu abro o Resumo THEN the system SHALL exibir: gráfico de pizza por categoria, barras mensais (gasto x renda), barras empilhadas por cartão, projeção de 12 meses e resumo anual por categoria.
- R1.7 WHEN eu crio, edito ou removo categorias e metas de poupança THEN the system SHALL refletir no Resumo sem nenhuma outra ação.
- R1.11 Categorias (tipo de gasto) SHALL vir de uma lista em `data/categories.json`, editável na tela Cadastros; todo lançamento, manual ou confirmado na Revisão, SHALL ter categoria **obrigatória** escolhida dessa lista.
- R1.12 WHEN eu removo uma categoria em uso THEN the system SHALL permitir a remoção, deixar os itens afetados (lançamentos, planos, assinaturas, compras recorrentes, regras) **sem categoria** e exibir um alerta persistente ("N lançamentos sem categoria") com atalho para recategorizar em lote; o alerta some quando não restar nenhum.
- R1.8 WHEN eu acesso a ajuda THEN the system SHALL exibir "Como usar" e "Como modificar" (substituem as abas de instruções da planilha).
- R1.9 WHEN um usuário tem renda cadastrada no mês THEN the system SHALL exibir a **renda comprometida** dele: sua parte dos gastos (real ou projetada) ÷ renda vigente, por mês, inclusive nos 12 meses de projeção; WHEN não tem renda THEN o indicador não é exibido.
- R1.13 The system SHALL projetar sempre **12 meses** a partir do mês corrente pela data real (sem configuração), e toda tela SHALL abrir no mês corrente; WHEN eu navego para meses anteriores THEN the system SHALL permitir editá-los (lançar, recategorizar, redividir, confirmar, acertar).
- R1.14 The system SHALL ter **modo escuro**: tema claro, escuro ou "seguir o sistema" (padrão), alternável no cabeçalho, com a escolha guardada no navegador; gráficos e cores de categoria SHALL manter contraste AA nos dois temas.

## R2 — Armazenamento em JSON

- R2.1 The system SHALL guardar todos os dados em arquivos JSON numa pasta `data/` configurável.
- R2.2 The system SHALL gravar de forma atômica: uma queda no meio da gravação nunca deixa JSON corrompido.
- R2.3 Cada arquivo SHALL ter `schema_version`; WHEN a versão é antiga THEN the system SHALL migrar ao iniciar, guardando backup do original.
- R2.4 Valores monetários SHALL ser guardados como string decimal (nunca float).

## R3 — Sincronização com a pasta (hash)

- R3.1 The system SHALL monitorar uma pasta de entrada (`inbox/`) com subpastas `faturas/` e `extratos/`.
- R3.2 WHEN um PDF novo aparece THEN the system SHALL calcular o SHA-256, ler o PDF e colocar os lançamentos em Revisão.
- R3.3 WHEN o conteúdo de um PDF muda (hash diferente no mesmo caminho) THEN the system SHALL reprocessar, manter o que já foi confirmado se não mudou e mandar para Revisão só as diferenças.
- R3.4 WHEN um PDF é removido THEN the system SHALL remover todos os lançamentos dele.
- R3.5 WHEN um PDF removido volta (mesmo hash ou mesmos lançamentos) THEN the system SHALL reaplicar minhas edições anteriores (divisões, categoria, notas).
- R3.6 WHEN um PDF é movido ou renomeado (mesmo hash) THEN the system SHALL apenas atualizar o caminho, sem reprocessar.
- R3.7 WHEN dois arquivos têm o mesmo hash THEN the system SHALL importar o conteúdo uma única vez e sinalizar a duplicata.
- R3.8 The system SHALL fazer varredura completa ao iniciar e periodicamente, além de reagir a eventos do sistema de arquivos.
- R3.9 WHEN um arquivo ainda está sendo copiado THEN the system SHALL esperar o tamanho estabilizar antes de processar.
- R3.10 The system SHALL exibir o estado de cada arquivo: `pendente revisão`, `parcialmente confirmado`, `confirmado`, `aguardando cartão`, `substituído`, `erro`, `perfil desconhecido`, `duplicado` (códigos em docs/05).
- R3.11 WHEN chega um segundo PDF de fatura para o mesmo (cartão, mês de fatura) com hash diferente (fatura parcial e depois final, reemissão com outro nome) THEN the system SHALL tratá-lo como **substituto**: diff por fingerprint contra o anterior, que vira `substituído` após eu confirmar a substituição. Nunca há dois documentos ativos para o mesmo (cartão, mês).
- R3.12 WHEN extratos da mesma conta têm períodos sobrepostos THEN the system SHALL importar cada lançamento uma única vez (deduplicação por fingerprint na conta).
- R3.13 WHEN um PDF é removido ou alterado THEN the system SHALL desfazer ou sinalizar tudo o que foi derivado dos lançamentos removidos (planos criados, vínculos de antecipação, fatura paga, acertos e movimentações de investimento sugeridos), conforme a tabela de cascata em docs/05.

## R4 — Leitura de PDFs de qualquer banco

- R4.1 The system SHALL ler faturas e extratos em PDF usando **perfis de banco** que eu posso adicionar sem mexer no código.
- R4.2 WHEN um PDF chega THEN the system SHALL detectar automaticamente o perfil; WHEN nenhum perfil reconhece o arquivo THEN o arquivo fica como `perfil desconhecido`.
- R4.3 WHEN eu crio ou edito um perfil THEN the system SHALL permitir testá-lo contra um PDF da pasta, mostrando linhas reconhecidas, linhas ignoradas e o total conferido.
- R4.4 WHEN o perfil consegue extrair o total da fatura THEN the system SHALL comparar com a soma dos lançamentos e sinalizar divergência.
- R4.5 WHEN o PDF tem senha THEN the system SHALL usar a senha cadastrada para aquele perfil, guardada num arquivo de segredos fora de `data/`.
- R4.6 WHEN uma linha de fatura indica parcela (ex.: `03/10`) THEN the system SHALL extrair número e total de parcelas.
- R4.7 WHEN a fatura tem seções por cartão (titular, adicional, virtual) THEN o perfil SHALL poder declarar o marcador de seção e cada linha SHALL ser atribuída ao cartão daquela seção.
- R4.8 WHEN o PDF não permite identificar o cartão automaticamente THEN o arquivo SHALL ficar `aguardando cartão` até eu escolher, e nenhum lançamento dele vai para a Revisão antes disso.
- R4.9 WHEN a fatura indica valor a pagar zero ou menor que as compras (pagamento antecipado, crédito de fatura anterior, "nada a pagar") THEN the system SHALL extrair e importar **todas as compras do período** normalmente; o valor a pagar é guardado à parte e não substitui a soma das compras nem os gastos.
- R4.10 The system SHALL ler, além de PDF, arquivos **CSV** (e outros formatos tabulares declarados no perfil), inclusive **faturas abertas** (ainda não fechadas) exportadas pelo banco; o perfil declara formato, codificação, separador e o mapeamento de colunas.
- R4.11 WHEN uma fatura aberta é importada THEN ela SHALL valer como dado real do (cartão, mês) **até a data de exportação**, somada aos meus lançamentos previstos posteriores a essa data; WHEN chega uma versão mais nova (aberta ou fechada) do mesmo (cartão, mês) THEN the system SHALL substituí-la pelo fluxo de R3.11, preservando confirmações e edições das linhas mantidas.

## R5 — Revisão e confirmação

- R5.1 WHEN lançamentos são importados THEN the system SHALL exibi-los em Revisão com divisão e categoria sugeridas pelas regras padrão.
- R5.2 WHEN estou em Revisão THEN the system SHALL permitir editar valor, descrição, categoria e divisão; confirmar um a um, em lote ou o arquivo inteiro.
- R5.3 The system SHALL aplicar a divisão padrão nesta ordem: (1) edição manual > (2) divisão do plano/assinatura vinculado > (3) regra > (4) donos próprios do cartão > (5) donos da conta (herdados pelo cartão ou do extrato). Ao confirmar, o lançamento grava a divisão vigente (lista fixa ou referência a padrão de divisão); mudanças posteriores em donos ou regras não alteram lançamentos já confirmados.
- R5.4 WHEN eu aplico a mesma edição (mesma categoria e/ou mesma divisão, comparada já resolvida) a lançamentos com a mesma descrição normalizada em **2 arquivos diferentes** THEN the system SHALL sugerir criar uma regra.
- R5.5 Lançamentos em Revisão SHALL aparecer nos painéis marcados como "não confirmados" (filtro), sem misturar com os confirmados por padrão.

## R6 — Usuários, divisões e "a receber"

- R6.1 WHEN eu cadastro um usuário THEN the system SHALL aceitar renda como opcional.
- R6.2 WHEN um lançamento é dividido THEN the system SHALL aceitar qualquer combinação de usuários com percentuais somando exatamente 100%.
- R6.3 WHEN um lançamento no cartão de A tem parte atribuída a B THEN the system SHALL contabilizar esse valor como dívida de B para A.
- R6.4 WHEN eu registro um acerto (B pagou X para A) THEN the system SHALL abater do saldo.
- R6.5 WHEN eu abro "A receber" THEN the system SHALL mostrar saldo por pessoa, detalhado por mês e lançamento.
- R6.6 WHEN o extrato tem crédito recebido de uma pessoa (ex.: PIX dos pais) THEN the system SHALL sugerir registrá-lo como acerto.
- R6.7 WHEN eu cadastro uma conta ou cartão THEN the system SHALL aceitar um ou mais **donos**, cada um com um percentual (soma 100%); a divisão entre os donos é a divisão padrão dos lançamentos dele.
- R6.8 WHEN eu cadastro uma conta ou cartão THEN the system SHALL exigir exatamente um **responsável** (quem paga o banco), que pode ser um dos donos ou não; os saldos "a receber" são calculados em relação ao responsável.
- R6.9 WHEN um cartão está vinculado a uma conta (ex.: conta conjunta) e não define donos próprios THEN the system SHALL herdar donos e responsável da conta.
- R6.10 WHEN eu cadastro um **padrão de divisão** (ex.: "Casal": eu 60%, esposa 40%) THEN the system SHALL permitir usá-lo no lugar de percentuais fixos em donos de cartão/conta, regras, planos, assinaturas e lançamentos.
- R6.11 WHEN eu altero os percentuais de um padrão de divisão a partir de um mês THEN the system SHALL aplicar a nova proporção só a lançamentos desse mês em diante, sem alterar meses anteriores.
- R6.12 WHEN um padrão de divisão está no modo "proporcional à renda" THEN the system SHALL calcular os percentuais de cada mês pela renda vigente dos membros naquele mês; WHEN algum membro não tem renda (ou tem renda zero) no mês THEN the system SHALL usar a versão fixa do histórico vigente naquele mês e exibir aviso.
- R6.13 WHEN eu altero renda, padrão de divisão ou divisão de forma que mude o saldo de um mês que já tem acerto registrado THEN the system SHALL avisar antes de salvar, mostrando a diferença.

## R7 — Antecipação de parcelamento

- R7.1 WHEN eu antecipo um parcelamento a partir da parcela k THEN the system SHALL mover as parcelas k..N para o mês alvo (padrão: a próxima fatura ainda não importada do cartão, nunca um mês passado; editável) e removê-las dos meses seguintes.
- R7.2 WHEN eu informo o valor efetivamente cobrado (com desconto do banco) THEN the system SHALL usar esse valor; senão SHALL usar a soma das parcelas restantes.
- R7.3 WHEN a fatura real com a antecipação é importada THEN the system SHALL casar as linhas com a antecipação registrada, sem duplicar, e o valor da fatura prevalece.
- R7.4 WHEN a antecipação é desfeita antes da fatura ser importada THEN the system SHALL restaurar o cronograma original.
- R7.5 WHEN a fatura traz o desconto da antecipação como linha de crédito separada THEN the system SHALL vinculá-la ao plano (herdando a divisão do plano) e o valor da antecipação SHALL ser a soma das cobranças mais os créditos vinculados.

## R8 — Reconciliação (sem dupla contagem)

- R8.1 WHEN uma parcela importada corresponde a um parcelamento existente THEN the system SHALL vinculá-la ao parcelamento, sem criar compra nova.
- R8.2 WHEN uma parcela importada não tem parcelamento THEN the system SHALL criar o parcelamento e projetar as parcelas futuras.
- R8.3 WHEN uma cobrança importada corresponde a uma assinatura THEN the system SHALL vinculá-la à assinatura.
- R8.4 WHEN o extrato tem pagamento de fatura THEN the system SHALL classificá-lo como transferência (não é gasto) e marcar a fatura como paga.
- R8.5 For each (cartão, mês), the system SHALL usar os dados **reais** (lançamentos do documento de fatura ativo) quando ele existe e passa no filtro de confirmação, e a **projeção** (parcelamentos + assinaturas + lançamentos manuais previstos) quando não.
- R8.6 Lançamentos manuais com documento (cartão de crédito, benefício, débito, PIX…) SHALL ser **previstos**: WHEN a fatura ou o extrato correspondente é importado THEN the system SHALL sugerir casá-los com as linhas importadas (absorvendo minha anotação) e avisar os que não casaram (ver R10.3).
- R8.7 WHEN um estorno referencia uma compra parcelada (mesma descrição, `n/of` ou valor) THEN the system SHALL vinculá-lo ao plano, nunca criar plano novo; WHEN o estorno cobre o restante THEN the system SHALL sugerir cancelar o plano.
- R8.8 WHEN uma fatura importada não traz a parcela que um plano esperava naquele mês THEN the system SHALL avisar (`parcela esperada ausente`), com opções: antecipada no banco, cancelada, ignorar.
- R8.9 WHEN um (cartão, mês) já passou e não tem fatura importada THEN the system SHALL marcá-lo como `faltando` nos painéis e no Status, e os saldos daquele mês como incompletos.
- R8.10 WHEN existe uma saída numa conta minha e uma entrada de mesmo valor noutra conta minha em ±2 dias THEN the system SHALL sugerir classificar ambas como transferência interna (não é gasto nem renda).

## R9 — Investimentos

- R9.1 WHEN eu cadastro um investimento THEN the system SHALL guardar nome, instituição, tipo (reserva, renda fixa, ações, fundos, previdência, cripto, outro), dono(s) (divisão fixa ou padrão de divisão) e meta opcional vinculada.
- R9.2 WHEN eu registro o saldo de um investimento numa data THEN the system SHALL guardar a posição (snapshot) sem apagar as anteriores.
- R9.3 WHEN eu registro um aporte ou resgate THEN the system SHALL guardá-lo como movimentação do investimento, que não conta como gasto nem como renda (inclusive quando o aporte é cobrado numa fatura de cartão: `kind = investment`, conta no total da fatura mas não em gasto).
- R9.4 WHEN o extrato tem uma aplicação ou resgate THEN the system SHALL sugerir vinculá-la a um investimento como aporte/resgate.
- R9.5 WHEN eu abro Investimentos THEN the system SHALL exibir: total investido atual, evolução no tempo, distribuição por tipo e por usuário, aportes x rendimento (saldo − aportes líquidos) por investimento.
- R9.6 WHEN um investimento está vinculado a uma meta de poupança THEN the system SHALL contar os aportes do mês como cumprimento da meta.

## R10 — Lançamento do dia a dia (antes da fatura/extrato)

- R10.1 WHEN eu registro um gasto manualmente THEN the system SHALL pedir: data, valor, descrição, **categoria**, **meio de pagamento** (R11) e divisão (pré-preenchida pela precedência de R5.3); parcelas opcionais (só cartão de crédito).
- R10.2 The system SHALL oferecer um formulário de **lançamento rápido** (poucos campos, teclado, sugestão de categoria/divisão pela descrição usando as regras e o histórico) acessível de qualquer tela.
- R10.3 Todo lançamento manual de meio de pagamento que gera documento (crédito, VR, débito, PIX) SHALL ser **previsto** até casar com a fatura ou o extrato importado; WHEN o documento chega THEN the system SHALL casar (sem duplicar), transferir minhas edições para a linha importada, importar o que faltava e listar os manuais que não casaram.
- R10.4 Gastos em dinheiro SHALL ser definitivos (não há documento para casar).

## R11 — Meios de pagamento

- R11.1 The system SHALL suportar os meios: **cartão de crédito**, **cartão de benefício** (VR/VA/refeição/alimentação), **débito**, **PIX**, **transferência**, **boleto** e **dinheiro**.
- R11.2 Cartão de benefício SHALL ser uma conta própria (com saldo, créditos do empregador e extrato), separada dos cartões de crédito; os créditos do benefício SHALL aparecer como "renda em benefício", separada da renda em dinheiro.
- R11.3 Débito, PIX, transferência e boleto SHALL estar ligados a uma conta bancária e casar com o extrato dela.
- R11.4 WHEN eu abro o Resumo THEN the system SHALL permitir ver e filtrar os gastos por meio de pagamento (crédito x benefício x débito/PIX x dinheiro).

## R12 — Compras recorrentes por intervalo

- R12.1 WHEN eu cadastro uma compra recorrente (ex.: ração dos gatos a cada 45 dias, ~R$ 250, no cartão X) THEN the system SHALL guardar descrição, valor estimado, intervalo (dias, semanas ou meses), data da última compra, meio de pagamento, categoria e divisão.
- R12.2 The system SHALL prever as próximas ocorrências pela data (última compra + intervalo) e colocar cada uma no mês de fatura correspondente; um mês pode ter zero, uma ou duas ocorrências.
- R12.3 WHEN uma compra real casa com a ocorrência prevista (descrição similar, valor ±20%, data ±⌈intervalo/3⌉ dias) THEN the system SHALL vinculá-la e **reancorar** as próximas ocorrências a partir da data real.
- R12.4 WHEN a ocorrência prevista passa da tolerância sem compra THEN the system SHALL avisar ("ração prevista em 10/11 não apareceu") com opções: adiar, pular, encerrar.

## R13 — Feedback do operador (2026-10-13)

Pedidos feitos durante o uso, registrados aqui para não se perderem (tasks na Fase 6 do tasks.md).

- R13.1 The system SHALL ter um visual premium (tema próprio, animações, skeletons, transições) respeitando `prefers-reduced-motion` e contraste AA nos dois temas.
- R13.2 WHEN um cartão (principal) ou conta (não dinheiro) é criado ou renomeado THEN the system SHALL criar a pasta `inbox/faturas/<nome em minúsculo>` / `inbox/extratos/<nome em minúsculo>`; arquivos dentro dela SHALL ser atribuídos a esse cartão/conta, e o nome do arquivo `YYYY-MM` SHALL ser usado como mês da fatura quando o documento não informar o vencimento (aviso se divergir).
- R13.3 The system SHALL ler os bancos suportados (perfis de exemplo embutidos) sem exigir copiar perfis para `profiles/`.
- R13.4 WHEN uma pessoa está selecionada na Projeção/Resumo THEN the system SHALL mostrar só os cartões e contas dela (dona ou responsável) e um total geral de contas + cartões.
- R13.5 The system SHALL permitir cadastrar **benefícios** com nome (ex.: "VR", "Auxílio home office"), pessoa, onde cai (cartão de benefício ou conta corrente) e valor mensal com vigência; benefício em conta soma na renda, benefício em cartão soma na renda em benefício, e o cartão de benefício é meio de pagamento.
- R13.6 The system SHALL impedir excluir usuário com qualquer vínculo (contas, cartões, divisões, lançamentos, anotações, acertos, investimentos, benefícios), explicando o que o prende.
- R13.7 The system SHALL criar, na primeira execução, as categorias: Alimentação, Aluguel, Animais, Banco, Casa, Compras, Delivery, Digital, Educação, Entretenimento, Família, Lazer, Moradia, Outros, Pessoal, Presente, Saúde, Trabalho, Transporte.
- R13.8 The system SHALL ter seletor de mês dinâmico (escolher mês/ano direto, teclado), sem navegar um mês por vez.
- R13.9 Perfis de banco SHALL ser simples de usar: mostrar quais bancos já são suportados, testar um arquivo e ver o resultado em linguagem clara; YAML só no modo avançado.
- R13.10 The system SHALL ter uma tela **Configurações** para escolher a cor de destaque do app (várias opções) além do tema claro/escuro, guardada no navegador.
- R13.11 WHEN um usuário tem "repassar para" definido THEN tudo o que ele deve SHALL ser devido a essa pessoa; e "A receber" SHALL mostrar um recebimento por cartão/conta e mês, com a data limite = vencimento da fatura do cartão onde a compra foi feita (2 cartões → 2 recebimentos).
- R13.12 Cada **versão** de um padrão de divisão SHALL escolher seu modo (percentual livre ou proporcional à renda); no modo proporcional a UI SHALL esconder os percentuais; versões seguintes podem voltar ao percentual livre.
- R13.13 Todo campo de mês/data na UI SHALL usar seletor (calendário/mês), nunca texto livre `YYYY-MM`.
- R13.14 WHEN o coletor ("repassar para") não é o responsável pelo cartão THEN the system SHALL gerar também a dívida coletor → responsável, para que nenhum valor fique sem dono.
- R13.15 Investimentos SHALL ter instituição escolhida de uma lista: contas cadastradas ou instituições configuráveis que não são banco (corretora, exchange, previdência, outro) — tela Cadastros → Instituições.
- R13.16 Em "A receber", cada recebimento (pessoa, cartão/conta, mês) SHALL poder ser marcado como **recebido** (gera um acerto vinculado a esse cartão/mês) e desmarcado; recebimentos quitados aparecem como recebidos.
- R13.17 Cartão de benefício (VR/VA) SHALL ser uma conta do tipo Benefício com **dia de renovação** opcional (1–31; o crédito do benefício cai nesse dia), sem fechamento nem vencimento; o dia de renovação SHALL ser rejeitado em contas de outro tipo. A tela de Cartões SHALL orientar a cadastrar o benefício em Contas, e a lista de Cartões SHALL mostrar os donos e o responsável efetivos (herdados da conta ou do cartão principal, com a origem).

## R14 — Feedback do operador (2026-11): visibilidade e cadastro

Pedidos feitos depois do tour visual de 2026-11 (tasks na Fase 7 do tasks.md).

- R14.1 WHEN eu cadastro uma conta ou cartão THEN the system SHALL aceitar **um ou mais responsáveis** (quem paga o banco), cada um com percentual somando 100% (lista fixa ou padrão de divisão, como os donos); com um só responsável o comportamento é o de R6.8. A parte de cada pessoa num lançamento SHALL ser devida a cada responsável na proporção dele (a parte que cabe ao próprio responsável não vira dívida). O **responsável principal** (o de maior percentual; empate: primeiro da lista) recebe o resíduo de centavos e as sugestões de acerto. No cartão, responsáveis são herdados junto com o responsável principal (nunca misturados entre níveis). "Repassar para" (R13.11, R13.14) vale para cada responsável.
- R14.2 The **Projeção** SHALL mostrar só cartões: uma coluna por cartão principal (adicionais somados no principal) e por cartão de benefício (conta tipo Benefício); contas corrente e dinheiro não entram na tabela, nos itens do mês nem no total, que passa a ser "Total dos cartões". A lista de itens do mês SHALL respeitar a pessoa selecionada.
- R14.3 Em toda tela (tabelas, gráficos, legendas, selects, avisos), cartões e contas SHALL ter rótulo inequívoco: um nome único entre cartões e contas aparece como está ("Nubank"); quando dois ou mais têm o mesmo nome (sem diferenciar maiúsculas/espaços), cada um ganha o que o distingue: cartão "Inter (cartão ••1234)", adicional "Inter (adicional ••5678)", conta "Inter (conta)", benefício "VR (benefício)", dinheiro "Carteira (dinheiro)". Dois itens nunca aparecem com o mesmo rótulo.
- R14.4 Um usuário SHALL poder ter **várias rendas** com nome (ex.: "Emprego A", "Freela"), cada uma com valor e histórico de vigência, e **rendas pontuais** de um único mês (ex.: "Bônus" em 2026-12). A renda do mês é a soma das rendas vigentes + pontuais do mês + benefícios em conta (R13.5). Renda pontual entra na renda do mês, na sobra e na renda comprometida, mas **não** na divisão proporcional à renda (R6.12), para um extra de um mês não mudar a divisão da casa.
- R14.5 O cadastro de **cartão** SHALL ser guiado: seções (identificação, quem usa e quem paga, fatura, leitura do PDF), texto de ajuda em cada campo, banco escolhido numa lista de bancos suportados (não id livre), a pasta onde colocar as faturas, e um resumo ao vivo de donos/responsáveis efetivos ("herdado da conta Inter: Casal 60/40"). O mesmo vale, no que couber, para o cadastro de conta.
- R14.6 Sem pessoa selecionada, Resumo e Projeção SHALL usar a renda da casa (soma das rendas de todos), inclusive no gráfico "Gasto x renda"; nenhuma tabela SHALL cortar colunas ou valores (rolagem horizontal visível ou layout que caiba) e a coluna **Ações** SHALL ficar fixa à direita quando a tabela rola, para os botões estarem sempre ao alcance; listas de abas (Cadastros, Lançamentos) SHALL quebrar linha em vez de esconder abas; tudo isso SHALL funcionar em 1440, 1024 e 768 px de largura; nenhum rótulo técnico interno (ex.: `owners:account`) SHALL aparecer para o operador.
- R14.7 Toda task que toca a UI SHALL passar pelo **tour visual** (`task ui-tour`): todas as telas e abas, claro e escuro, com dados sintéticos, sem erro de console nem API 5xx, e as capturas revisadas (docs/11).
- R14.8 A Revisão de uma **fatura de cartão** SHALL ter só gastos: linhas que o perfil classifica como pagamento/transferência/receita/acerto (ex.: "PAGAMENTO RECEBIDO", que é o pagamento visto pelo lado do cartão e já aparece no extrato) não entram na Revisão nem viram lançamento; o tipo de uma linha de fatura só pode ser Gasto, Estorno, Tarifa/juros ou Investimento (previdência no cartão, R9.4) — a UI só oferece esses e a API recusa os outros (`422 invalid_kind`).
- R14.9 Assinaturas e compras recorrentes SHALL ter **histórico de preço** (reajustes: valor a partir de um mês); o valor previsto de cada mês é o vigente nele, sem alterar meses anteriores. A divisão (padrão de divisão ou percentuais) SHALL aparecer na lista das duas.
- R14.10 Compras recorrentes SHALL poder ser **desativadas e reativadas** (Cadastros e Lançamentos → Recorrentes); ao reativar, opcionalmente com a data da próxima compra.
- R14.11 Assinaturas e compras recorrentes SHALL guardar os **períodos em que ficaram desativadas** (de um mês até outro, ou "até agora"); cobranças previstas e avisos de "não ocorreu" só existem nos meses ativos. Desativar abre um período a partir da primeira compra que não aconteceu (ou do mês atual); reativar fecha o período no mês anterior à volta.
- R14.12 O cabeçalho SHALL mostrar o nome do app com a descrição "controle financeiro" (não "livro-caixa pessoal").
- R14.13 The system SHALL permitir escolher o **idioma** da interface entre português (pt-BR, padrão) e inglês (en) em Configurações, guardado no navegador; datas e dinheiro seguem o idioma escolhido, valores continuam em R$.
- R14.14 No cadastro de compra recorrente, "Data da última compra" SHALL explicar que é a última compra que já aconteceu (a próxima prevista = essa data + intervalo).
- R14.15 "A receber" SHALL ter uma seção **Previsto**: o que cada pessoa vai dever (ou eu vou dever) pelas assinaturas, compras recorrentes e parcelas divididas, no mês atual e nos 2 próximos, agrupado por mês e por pessoa (com o cartão/conta de origem), separado dos recebimentos confirmados (não entra nos totais nem pode ser marcado como recebido); vira recebimento de verdade quando a fatura/extrato chega.
- R14.16 Onde a divisão pode ficar em "Padrão", a UI SHALL dizer o que o padrão significa naquele cartão/conta (ex.: "Padrão = donos do cartão Inter — Eu 100%"), lembrando que uma regra pode mudar. "Padrão" sem divisão gravada (lançamento manual, assinatura, gasto recorrente) SHALL valer como na Revisão: a regra que casa e, sem regra, os donos — nunca "ninguém".
- R14.17 Ao salvar um lançamento rápido que cai em outro mês de fatura (data futura ou depois do fechamento), a app SHALL ir para esse mês e avisar, para o lançamento não parecer sumido.
- R14.18 A cor de destaque escolhida (R13.10) SHALL valer também para a cédula do total do mês no Resumo, a moeda do logo e o **favicon** (com contraste AA do texto da cédula em todas as cores).
- R14.19 Parcelamentos: os lançamentos do mês SHALL listar as **parcelas previstas** com "parcela N/M"; a aba Parcelamentos SHALL mostrar quanto falta (parcelas, valor, próxima parcela e mês), o status **terminando** quando faltam 3 ou menos, e esconder os terminados (pagos/cancelados) com a opção "Mostrar terminados".
- R14.20 Um parcelamento SHALL poder ser **editado** depois de criado: descrição, categoria e divisão sempre; cartão, valor total, número de parcelas e 1ª fatura só nos lançados à mão (os vindos da fatura seguem o banco).
- R14.21 A aba Parcelamentos SHALL mostrar o **valor da parcela por mês** ("10x de R$ 400,00") e o valor da próxima parcela.
- R14.22 Um recebimento de conta (PIX, débito, boleto) SHALL ter como data limite o vencimento da fatura do **cartão vinculado** à conta em que uma compra no cartão no mesmo dia cairia (assim o prazo nunca já nasce vencido); num recebimento com vários lançamentos vale o prazo mais tarde; conta sem cartão continua sem data limite.
- R14.23 Um lançamento manual SHALL poder mudar de **meio de pagamento, cartão ou conta** depois de salvo (mesmas regras do lançamento novo); o mês de fatura é recalculado.
- R14.24 Cada categoria SHALL ter uma descrição opcional do **que entra nela**; as categorias padrão (R13.7) já vêm descritas (ex.: Casa = "Contas da casa: luz, água, gás, internet; móveis…"), e a descrição aparece na lista de Categorias, em cada opção do seletor de categoria e abaixo do campo quando escolhida.
- R14.26 The system SHALL ter **Contas da casa** (luz, água, gás, aluguel, condomínio, internet…): um **gasto recorrente** (antigo "compra recorrente", renomeado porque nem tudo é compra) do tipo "Conta da casa", em que cada ocorrência é um vencimento (pagar não muda as datas), com reajustes (R14.9) e períodos desativada (R14.11); a tela Contas da casa mostra, para o mês, previsto, pago (lançamentos vinculados), vencimento e situação (paga, pendente, atrasada depois do vencimento, desativada) e permite **registrar o pagamento** (lançamento manual vinculado à conta e ao mês da conta). Um mês já pago por um lançamento vinculado não é previsto de novo (sem dupla contagem). Assinaturas antigas marcadas como conta da casa continuam aparecendo.
- R14.27 Assinaturas e gastos recorrentes SHALL poder **mudar de divisão a partir de um mês** (ex.: começo a dividir as contas da casa em janeiro): cada mudança vale do mês dela em diante, os meses anteriores não mudam, e a lista mostra a divisão de hoje e a próxima mudança.
- R14.28 "A receber" SHALL ter **uma aba por pessoa** (e "Todas"), qualquer que seja o tipo de gasto: a aba mostra o que ela tem que pagar confirmado em aberto e o previsto (assinaturas, gastos recorrentes, parcelas) e filtra todos os painéis, inclusive os saldos; e escolher o **vencimento** (este mês, próximo mês — padrão —, todos em aberto), com o total por pessoa; e os reajustes SHALL aparecer na lista com o **último reajuste como preço principal** (se começa num mês futuro: "R$ 50,00 a partir de jan/2027 (hoje R$ 44,90)"). Um débito vencido em aberto aparece em qualquer período.
- R14.29 Lançamentos SHALL mostrar os **previstos do mês** que ainda não viraram lançamento: parcelas ("parcela N/M"), assinaturas e gastos recorrentes (contas da casa incluídas), com data, cartão/conta e valor.
- R14.30 Gastos recorrentes SHALL mostrar a **próxima data** prevista na lista e permitir repetir **de tantos em tantos** (ex.: de 30 em 30 dias) ou **todo dia X do mês** (31 em mês curto = último dia). O dia escolhido fica guardado (`day_of_month`): uma compra real em outro dia não tira as próximas do dia X.
- R14.31 Avisos SHALL refletir o estado atual: apagar a única fatura de um cartão não deixa avisos de "Fatura faltando" (um mês passado só fica faltando se o cartão já tinha fatura importada antes dele ou se há lançamento manual nele); o aviso de itens sem categoria SHALL dizer onde eles estão (lançamentos, parcelamentos, assinaturas, gastos recorrentes) com um link para cada lugar.
- R14.32 Num cartão de benefício com mais de um benefício (ex.: Caju com VR e Home office), o lançamento pago com benefício SHALL permitir escolher **qual benefício** foi usado — no lançamento rápido, na edição, em Assinaturas, em Gastos recorrentes e no pagamento de Contas da casa — sempre que o meio for cartão de benefícios (com um benefício só ele já vem escolhido; sem nenhum ligado ao cartão, a tela diz como ligar). Lançamentos SHALL mostrar o benefício junto do cartão (ex.: "Caju · Home office"). Trocar de cartão/meio limpa o benefício. O tipo de conta e o meio de pagamento se chamam **Cartão de benefícios** (sem "VR/VA"). (Saldo por benefício: fora deste requisito.)
- R14.33 Resumo: o **Resumo anual** SHALL destacar o mês atual com uma cor leve; o painel "Cartões e contas" SHALL sair do Resumo; o painel "Renda comprometida" SHALL ganhar um nome mais claro e mostrar **todas as pessoas** — com renda cadastrada: porcentagem comprometida como hoje; sem renda: o gasto dela e "sem renda cadastrada".
- R14.34 As listas de Gastos recorrentes (Cadastros e Lançamentos → Recorrentes) SHALL mostrar a **categoria** de cada um (e "todo dia X" quando for o caso).
- R14.36 O Resumo anual SHALL ter duas tabelas: **por categoria** e **por cartão/conta** (incluindo os cartões de benefício); as duas SHALL mostrar no rodapé o **total sem benefício** (o principal) e o **total com benefício**. Os painéis do Resumo SHALL se dividir sem sobrar buraco nem estourar a tela em 1440, 1024 e 768 px.
- R14.37 No Resumo, "Gasto x renda (12 meses)" SHALL ficar compacto, e SHALL haver um painel **Histórico por categoria**: escolho uma categoria ou um grupo delas (clicando na lista de Gastos por categoria ou no seletor) e vejo os 12 meses do valor e da **% do total** de cada mês, com a média, para entender o que começou a gerar custo; sem nada escolhido, mostra **todas as categorias** empilhadas. A lista de Gastos por categoria SHALL mostrar a **%** de cada categoria no mês.
- R14.35 Arquivos de configuração do repositório SHALL usar a extensão `.yaml` (nunca `.yml`, a não ser que uma ferramenta exija).
- R14.25 Em Configurações SHALL dar para escolher a(s) **pessoa(s) padrão**; Resumo e Projeção abrem com a parte dessa(s) pessoa(s) e a renda delas (várias pessoas = partes e rendas somadas, ex.: eu + esposa; vazio = a casa) e permitem trocar a seleção; A receber abre como a primeira delas. API: `user_id` aceita vários ids separados por vírgula.

## Acceptance Criteria

- [ ] Todas as features de R1 equivalentes às da planilha antiga.
- [ ] Adicionar, alterar, mover e remover um PDF em `inbox/` se reflete na app em ≤ 1 intervalo de varredura, sem reiniciar.
- [ ] Remover e recolocar um PDF restaura minhas divisões.
- [ ] Novo banco adicionado só com um perfil (sem código) e testado na tela de perfis.
- [ ] Nenhum lançamento contado duas vezes nos cenários: parcela importada x prevista, antecipação (inclusive com desconto em linha separada), assinatura, pagamento de fatura no extrato, lançamento manual x importado, fatura parcial + final, extratos sobrepostos, transferência entre contas minhas.
- [ ] Saldo "a receber" bate com a soma das partes atribuídas menos acertos.
- [ ] Cartão vinculado a conta conjunta com 2 donos 50/50 gera divisão 50/50 por padrão, e o saldo é calculado contra o responsável.
- [ ] Padrão "Casal" 60/40 alterado para 55/45 a partir de um mês muda só os meses seguintes; modo proporcional à renda acompanha mudanças de salário.
- [ ] Renda comprometida exibida por usuário com renda, inclusive na projeção.
- [ ] Saldo investido total e por usuário bate com o último snapshot de cada investimento; aplicação no extrato não aparece como gasto.
- [ ] Gastos lançados à mão durante o mês (crédito, VR, débito, PIX) não duplicam quando a fatura/extrato chega; o que faltava é importado; os não casados são listados.
- [ ] Resumo separa crédito, benefício (VR), débito/PIX e dinheiro.
- [ ] Compra recorrente a cada 45 dias aparece em 0, 1 ou 2 faturas conforme as datas, e se reancora pela compra real.
- [ ] Matar o processo durante uma gravação não corrompe nenhum JSON.
- [ ] Fatura aberta em CSV importada no meio do mês, depois a fatura fechada em PDF: nada duplica, edições preservadas.
- [ ] Remover uma categoria em uso deixa os lançamentos sem categoria e mostra o alerta até eu recategorizar.
- [ ] Cobertura de testes ≥ 90% no backend.

## Fora de escopo

- Login, multiusuário com acesso, hospedagem pública.
- Integração direta com bancos (Open Finance) e OCR de PDF escaneado (imagem).
- Cotação automática de investimentos (a app é offline; saldos são informados por mim).
- Envio de dados financeiros para LLM/serviço externo.
- App mobile.

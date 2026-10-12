# 11 — Estratégia de testes (obrigatório)

[← Índice](README.md) · Processo: [10](10-processo-de-desenvolvimento.md)

## Pirâmide

```
            ┌──────────┐
            │   e2e    │  Playwright: inbox → Revisão → painéis (poucos, caminhos críticos)
            ├──────────┤
            │ cenários │  backend inteiro com tmp dirs + PDFs sintéticos (sem HTTP mock)
            ├──────────┤
            │   API    │  FastAPI TestClient, um teste por endpoint/erro
            ├──────────┤
            │ módulos  │  storage, profiles, importing, sync, review — isolados
            ├──────────┤
            │  domain  │  funções puras, exemplos da doc (a maioria dos testes)
            └──────────┘
   frontend: Vitest + Testing Library por componente/tela
```

Regra: **cada camada é testada antes de ser usada pela de cima**. Nenhuma task da Fase N começa com
testes da Fase N−1 vermelhos.

## Ferramentas

| Parte | Ferramenta |
|-------|-----------|
| Backend | pytest, pytest-cov (gate 90%), hypothesis (propriedades do domínio) |
| PDFs de teste | reportlab gera PDFs sintéticos em tempo de teste (com e sem senha) |
| Tempo | relógio injetado (`Clock` protocolado); nunca `datetime.now()` direto no domínio |
| Frontend | Vitest, Testing Library, MSW (mock da API só no frontend) |
| e2e | Playwright contra o container de uso |
| Arquitetura | teste que importa os módulos e verifica a direção das dependências ([03](03-arquitetura.md#camadas-e-dependências-permitidas)) |

**Nenhum PDF real** (com dados pessoais) entra no repositório. Fixtures são sintéticas.

## Testes de arquitetura

Um teste (T0.6) percorre os imports de `backend/src/expense_tracker/` e falha se algum módulo importar
algo proibido pela tabela de [03](03-arquitetura.md#camadas-e-dependências-permitidas) (ex.: `domain`
importando `storage`). Também verifica que `domain` não usa `open`, `os`, `pathlib` nem `datetime.now`.

## O que testar por módulo

### domain
- Cada exemplo e tabela de [07](07-regras-de-negocio.md) e [08](08-divisoes-e-acertos.md) = um teste parametrizado.
- Bordas: fechamento no dia 31 em fevereiro; virada de ano; troca de `billing_history`; `H` no dia do
  fechamento; parcela 1/1; resto de centavos na 1ª parcela; antecipação a partir da 1ª e da última
  parcela; `target_month < H` rejeitado; plano cancelado; divisão com 3 pessoas e centavos; renda sem
  histórico e renda zero; estorno.
- Padrão de divisão: versão vigente por mês (antes da 1ª, na troca, depois); proporcional à renda com
  aumento de salário e resíduo; fallback para a versão vigente quando falta renda; renda comprometida
  com e sem renda; aviso R6.13 ao mudar mês com acerto.
- Propriedades (hypothesis):
  - partes de uma divisão somam exatamente o valor;
  - `schedule` com antecipação tem o mesmo total que sem antecipação quando `amount` não é informado;
  - saldo(A,B) = −saldo(B,A).

### storage
- Ida e volta de cada arquivo (gravar → ler = igual).
- **Crash**: simular falha entre `write` e `os.replace` (monkeypatch) → arquivo antigo intacto e legível.
- Lock: segunda instância falha com erro claro.
- Migração: arquivo `schema_version` antigo → migrado + backup criado.
- Rejeita float e referência inexistente (invariantes de [04](04-modelo-de-dados.md#invariantes-verificados-em-teste)).

### profiles / importing
- Schema: perfil válido carrega; cada campo inválido gera mensagem específica.
- Detecção: 1, 0 e 2+ perfis casando.
- Parse do PDF sintético de exemplo: header, linhas, parcelas, ignorados, multiline, formato br/us,
  inferência de ano na virada.
- Soma x total: igual e divergente.
- PDF com senha: senha certa, errada, ausente.
- Timeout de regex catastrófica → `error`.
- Plugin Python carregado e usado.

### sync
Uma função de teste por linha das tabelas de [05](05-sincronizacao.md): cada `status`; eventos NOVO,
ALTERADO (diff adicionados/removidos/mantidos), MOVIDO, DUPLICADO (e promoção quando o original sai),
REMOVIDO (anotações preservadas); substituição de fatura (aprovar, recusar, remover o substituto);
extratos sobrepostos (`overlap` e transferência de posse); cada linha da tabela de **cascata** (e a
recriação com o mesmo id ao recolocar o PDF); arquivo ainda sendo copiado; ignorados e symlink para
fora; `awaiting_card` e reprocessamento após a escolha; crash entre a gravação dos dados e a do
manifesto + recuperação no scan de inicialização. Watchdog testado só como "dispara scan"; a lógica
fica em `scan()`, testável sem eventos reais.

### review
- Precedência completa da divisão (os 5 níveis de [08](08-divisoes-e-acertos.md#precedência-r53)) e da categoria.
- Regras em duas passadas, empate de prioridade.
- Herança donos/responsável adicional ← principal ← conta.
- Confirmação congela a divisão: mudar donos depois não altera o confirmado; `split_id` continua resolvendo por mês.
- Cada linha (1–15) da tabela de reconciliação de [09](09-revisao-e-reconciliacao.md#reconciliação), a
  ordem de aplicação e os avisos 7, 8, 10.
- Sugestão de regra: 2 arquivos sim, 2 edições no mesmo arquivo não; divisão fixa equivalente a `split_id`.
- Anotação órfã.

### API
- Cada endpoint: sucesso, validação 422, não encontrado 404, conflito 409 (quando aplicável).
- Valores monetários sempre string na resposta.

### Cenários

Testes ponta a ponta no backend (sem HTTP), com `tmp_path` para `data/` e `inbox/`:

| Cenário | Verifica |
|---------|----------|
| Fatura com parcela 3/10 de plano existente | sem compra nova; total do mês = fatura |
| Fatura com parcela 1/10 sem plano | plano criado; 9 meses projetados |
| Remover a fatura que criou o plano | plano apagado; projeção some; recolocar recria o mesmo plano |
| Antecipação registrada + fatura com as parcelas | sem duplicar; valor real gravado; meses seguintes vazios |
| Antecipação + desconto em linha separada | `amount` = cobranças − desconto; desconto com a divisão do plano |
| Fatura sem a parcela esperada | aviso; "antecipada no banco" cria a antecipação |
| Estorno de compra parcelada | `refund` vinculado; nenhum plano novo; sugestão de cancelar se total |
| Assinatura prevista + cobrança na fatura | conta uma vez |
| Manual no cartão + mesma compra na fatura | conta uma vez; anotação do manual vai para o importado |
| Fatura parcial e depois final do mesmo mês | um documento ativo; diff aplicado |
| Dois extratos sobrepostos | cada lançamento uma vez |
| Fatura + extrato com pagamento dela | pagamento é `transfer`; fatura paga; gasto conta uma vez |
| PIX da minha conta para a conjunta | ambos `transfer`; nem gasto nem renda |
| PIX dos pais no extrato | sugestão de acerto; não conta como renda |
| Remover PDF e recolocar | lançamentos somem e voltam com as divisões editadas |
| Cartão da conta conjunta 50/50 | divisão padrão 50/50; saldo contra o responsável |
| Adicional com seção própria na fatura | linhas do adicional com os donos dele; um documento só |
| Aplicação em investimento no extrato / previdência no cartão | `transfer` / `investment`; não conta como gasto; movimentação criada |
| Padrão "Casal" muda de 60/40 para 55/45 | meses anteriores intactos; meses seguintes com a nova proporção |
| Mês passado sem fatura | marcado `faltando`; saldos incompletos |
| Fatura só em revisão + filtro "só confirmados" | mês continua projetado (não zera) |
| Gastos lançados à mão no mês (crédito, VR, débito, PIX) + fatura/extratos | nenhum duplicado; faltantes importados; não casados listados |
| Ração a cada 45 dias | 0/1/2 ocorrências por fatura conforme a tabela de [16](16-dia-a-dia.md#previsão); reancora pela compra real |
| Fatura com total a pagar R$ 0,00 (pago antecipado) | todas as compras importadas; pagamentos `transfer`; soma = `total` |
| Fatura aberta (CSV) e depois fechada (PDF) | substituição; confirmações e edições preservadas; nada duplica |
| Várias parcelas do mesmo plano numa fatura | sugestão de antecipação feita no banco (7b) |
| Remover categoria em uso | itens `null`; alerta com contagem; some após recategorizar |
| Projeção | sempre 12 meses a partir do mês corrente do `Clock`; vira sozinha na troca de mês |
| Lançamento retroativo em mês com documento ativo | reconciliação imediata (absorvido ou aviso) |

### Perfis de exemplo (Inter, Nubank)

PDFs **sintéticos** gerados com reportlab imitando os layouts de [06](06-perfis-de-banco.md#perfis-de-exemplo-validados-inter-e-nubank)
(cabeçalho repetido por página, datas por extenso, sinais `+`/`−` U+2212, seções por cartão, final por
linha, "Próxima fatura", antecipação com desconto, total a pagar zero). Cada perfil de
`profiles/examples/` tem teste: zero linhas não reconhecidas e soma = total. Nunca usar o PDF real em teste.

### Segurança

Um teste por linha de [13](13-seguranca.md#controles) que seja verificável em código: `Host` fora de
`127.0.0.1`/`localhost` → 400; mutação sem `X-Requested-With` → 403; sem headers CORS na resposta;
caminho com `..` ou symlink para fora de `inbox/` rejeitado; senha de PDF ausente de logs, respostas e
`data/` (busca pelo valor após uma importação); log INFO sem descrição/valor; timeout de parse.
Configuração do container (não-root, rootfs read-only, `cap_drop`) verificada por um teste que lê o
`docker-compose.yml`.

### Frontend
- Cada tela: renderiza com dados (MSW), estado vazio, estado de erro.
- Formulários: validação de divisão (soma 100), donos (soma 100), dinheiro.
- Revisão: editar linha, confirmar lote.

### e2e (Fase 4)
Soltar PDF sintético na inbox → aparece em Status → Revisão → editar divisão → confirmar → Resumo
mostra valor → remover arquivo → some → recolocar → divisão editada volta.

## Comandos

```bash
task test        # backend + frontend, em containers
task coverage    # backend com --cov-fail-under=90 e relatório por pacote
task lint        # ruff, mypy, eslint, tsc
task trace       # cada R* citado em tasks.md por task [x] tem teste test_r<x>_<y>_*
task e2e         # sobe o container de uso e roda Playwright
task ci          # tudo acima + docs-check + pip-audit/npm audit (o que o CI roda)
```

Definidos na Fase 0 (T0.4); detalhes em [14](14-operacao.md).

## Convenções de teste

- Nome: `test_<req>_<comportamento>` quando cobre requisito (`test_r7_1_anticipation_moves_remaining_installments`).
- Um comportamento por teste; Arrange / Act / Assert visíveis.
- Fixtures reutilizáveis em `backend/tests/conftest.py`; builders (`make_card(...)`) em vez de JSON gigante.
- Sem `sleep` em teste: relógio injetado e funções de scan chamadas diretamente.
- Teste que precisa de rede é bug: a app é offline.

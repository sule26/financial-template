# 06 — Perfis de banco (leitura de PDF)

[← Índice](README.md) · Requisitos: R4 · Decisão: [design.md › Decisão 2](../specs/expense-tracker-web/design.md)

Um **perfil** é um arquivo YAML em `profiles/` que ensina a app a ler PDFs de um banco. Adicionar um
banco novo = criar um perfil e testá-lo na tela Perfis. Nenhum código, nenhum rebuild.

`profiles/examples/` (versionado) tem exemplos; os perfis reais ficam em `profiles/*.yaml`
(fora do git, porque podem conter nomes e trechos meus).

## Pipeline

```
PDF ──(pypdf: abre com senha se houver)──► pdfplumber: texto por página (layout preservado)
    ──► detecção do perfil ──► header (vencimento, fechamento, total)
    ──► seção de lançamentos ──► linhas ──► RawTransaction[] ──► conferência soma x total
```

## Formato

```yaml
id: banco-x-fatura               # único; [a-z0-9-]
name: Banco X — fatura
kind: fatura                     # fatura | extrato
detect:
  all: ["BANCO X", "Resumo da fatura"]   # todas precisam aparecer
  none: ["Extrato de conta"]             # nenhuma pode aparecer (opcional)
password: banco-x                # chave em secrets/pdf-passwords.yaml (opcional)

header:
  due_date:     {regex: 'Vencimento\s+(?P<v>\d{2}/\d{2}/\d{4})', format: '%d/%m/%Y'}
  closing_date: {regex: 'Fechamento\s+(?P<v>\d{2}/\d{2}/\d{4})', format: '%d/%m/%Y'}
  total:        {regex: 'Total de lançamentos\s+R\$\s*(?P<v>[\d.]+,\d{2})'}   # soma das compras do período
  amount_due:   {regex: 'Total a pagar\s+R\$\s*(?P<v>-?[\d.]+,\d{2})'}       # o que o banco cobra (pode ser 0)
  card_hint:    {regex: 'final\s+(?P<v>\d{4})'}     # opcional: identifica o cartão

transactions:
  section: {start: 'Lançamentos', end: 'Total da fatura'}   # opcional
  card_section: 'Cartão final (?P<v>\d{4})'                 # opcional: muda o cartão corrente (R4.7)
  line: '^(?P<date>\d{2}/\d{2})\s+(?P<desc>.+?)\s+(?P<amount>-?[\d.]+,\d{2})$'
  date_format: '%d/%m'           # sem ano → inferido (abaixo)
  installment: '(?P<n>\d{1,2})/(?P<of>\d{1,2})\s*$'   # aplicado à descrição
  ignore: ['PAGAMENTO RECEBIDO', 'SALDO ANTERIOR']
  negative_means: refund         # refund | expense
  multiline: false               # true: linha sem data é continuação da descrição anterior
  amount_format: br              # br (1.234,56) | us (1,234.56)

# Classificação de linhas (faturas e extratos). Primeira que casa vence.
# tag (opcional): investment_contribution | investment_withdrawal | anticipation | anticipation_discount
classify:
  - {match: 'PAGAMENTO FATURA', kind: transfer}                 # extrato
  - {match: 'PIX RECEBIDO',     kind: income}                   # extrato
  - {match: 'TARIFA|IOF|JUROS', kind: fee}
  - {match: 'APLICACAO',        kind: transfer, tag: investment_contribution}
  - {match: 'PREVIDENCIA',      kind: investment, tag: investment_contribution}   # fatura
  - {match: 'ANTECIP',          tag: anticipation}
  - {match: 'DESC.*ANTECIP',    tag: anticipation_discount}
```

Grupos nomeados obrigatórios em `line`: `date`, `desc`, `amount`. Opcional: `n`, `of` (se a
parcela vier numa coluna própria).

## Detecção

Para cada perfil cujo `kind` bate com a pasta (`faturas/` ou `extratos/`), testa `detect`.

| Resultado | Ação |
|-----------|------|
| Exatamente 1 perfil casa | Usa esse |
| Nenhum | `status=unknown_profile` |
| Mais de 1 | `status=error` "perfis ambíguos: A, B" (refine o `detect`) |

## Identificação do cartão ou conta

Resolvida **antes** de calcular fingerprints e antes do staging.

1. Se o perfil tem `card_section`, cada linha pertence ao cartão cujo `last_digits` contém o final da
   seção corrente (adicionais e virtuais, R4.7). Linhas antes da primeira seção usam o passo 2.
2. `card_hint` do header casa com algum `last_digits` cadastrado.
3. Senão, o único cartão cadastrado com `profile_id` igual ao perfil.
4. Senão, escolha anterior em `card_choices.json` para este `sha256` ou para (`profile_id`, `card_hint`).
5. Senão, o arquivo fica `awaiting_card` (R4.8) e a tela Status pede para escolher; a escolha é gravada
   e o arquivo é reprocessado.

Final de seção sem cartão cadastrado → `awaiting_card` com a mensagem "final 5678 não cadastrado".
Para extratos, o mesmo vale com `account_hint`. Com cartões adicionais, o documento de fatura
pertence ao cartão **principal** (`parent_card_id`), e cada linha guarda o cartão da sua seção.

## Inferência de ano

Datas sem ano usam a data de fechamento (fatura) ou o fim do período (extrato): o ano é aquele que deixa a
data **≤ fechamento** e a menos de 12 meses dele. Ex.: fechamento 03/01/2027, linha `28/12` → 2026.
Parcelas lançadas com a data da compra original (ex.: `14/03` na parcela 8/10) seguem a mesma regra.

O **fechamento real** lido do PDF (`closing_date`) e o vencimento (`due_date`) vão para o manifesto e
prevalecem sobre o `billing_history` do cartão para aquele mês ([07](07-regras-de-negocio.md#mês-de-fatura)).

## PDF com senha

`secrets/pdf-passwords.yaml` (modo 0400, montado read-only, fora do git):

```yaml
banco-x: "12345678900"
```

A senha nunca vai para `data/`, para log ou para a API.

## Fatura "nada a pagar" (R4.9)

Algumas faturas mostram **total a pagar R$ 0,00** (ou menor que as compras) porque paguei antes,
houve crédito de fatura anterior ou estorno grande. As compras do período continuam lá e **são
importadas normalmente** — o gasto aconteceu.

| Campo | Significado | Usado em |
|-------|-------------|----------|
| `total` | Soma das compras/encargos do período (o que lancei no cartão) | Conferência soma x total |
| `amount_due` | O que o banco cobra no vencimento (pode ser 0 ou negativo = crédito) | Casamento com o pagamento no extrato |

- Linhas como "PAGAMENTO ANTECIPADO", "CRÉDITO FATURA ANTERIOR", "SALDO ANTERIOR" vão em `ignore`
  (não são compras): elas explicam a diferença entre `total` e `amount_due`, mas não entram em gasto.
- Se o perfil só consegue extrair `amount_due`, a conferência soma x total é pulada (aviso `no_total`)
  — nunca se compara a soma das compras com o valor a pagar.
- Pagamento antecipado no extrato (antes do vencimento, valor ≠ `amount_due`) casa com a fatura pela
  linha 12 da reconciliação com a regra estendida de [09](09-revisao-e-reconciliacao.md#reconciliação).

## Fatura aberta e formatos tabulares (CSV) — R4.10, R4.11

Alguns bancos exportam a fatura **ainda aberta** (ou o extrato) em CSV. O perfil declara `format`:

```yaml
id: banco-y-fatura-aberta-csv
kind: fatura
format: csv                      # pdf (padrão) | csv
open_invoice: true               # este formato representa fatura ainda não fechada
csv:
  encoding: utf-8                # utf-8 | latin-1 | cp1252 (utf-8 com BOM é aceito)
  delimiter: ';'
  skip_rows: 0
  header_row: true
  columns:                       # nome da coluna no arquivo → campo
    date: 'Data'
    desc: 'Lançamento'
    amount: 'Valor'
    installment: 'Parcela'       # opcional ("3/10" ou "3 de 10")
    card_hint: 'Final do Cartão' # opcional, por linha (adicionais)
detect:
  columns: ['Data', 'Lançamento', 'Valor']   # cabeçalho precisa ter estas colunas
date_format: '%d/%m/%Y'
amount_format: br
negative_means: refund
ignore: ['PAGAMENTO']
invoice_month_from: due_date_column | filename | ask   # como descobrir o mês de fatura
```

- Detecção para CSV: pelas colunas do cabeçalho (`detect.columns`), em vez de texto.
- O pipeline depois do parse é o mesmo do PDF (`ParseResult`), então reconciliação, fingerprint e
  Revisão não mudam. `ignore`, `classify` e `installment` funcionam igual.
- Mês de fatura de um CSV aberto: `invoice_month_from` — coluna de vencimento, padrão no nome do
  arquivo (`filename: '(?P<y>\d{4})-(?P<m>\d{2})'`) ou `ask` (o arquivo fica `awaiting_card` até eu informar
  cartão **e** mês, gravado em `card_choices.json`).
- CSV não tem senha nem total confiável: a conferência soma x total é pulada (`no_total`) a menos que
  o perfil tenha uma coluna/linha de total.
- Data de exportação (`as_of`): coluna/linha declarada no perfil, senão o `mtime` do arquivo.

### Como a fatura aberta convive com o resto

```
(cartão, mês) com documento ativo ABERTO (as_of = 2026-10-18):
   real      = linhas do CSV
   + manuais provisórios com data > as_of     (o que comprei depois da exportação)
   + ocorrências previstas com data > as_of
```

- Manuais com data ≤ `as_of` casam com as linhas do CSV (linha 9 da reconciliação).
- Um CSV aberto mais novo, ou o PDF fechado, do mesmo (cartão, mês) entra pelo fluxo de
  [substituição](05-sincronizacao.md#substituição-de-fatura). Fechado substituindo aberto é sugerido
  como padrão ("substituir fatura aberta de 18/10 pela fechada?"). Linhas mantidas continuam
  confirmadas com as minhas edições; linhas novas vão para a Revisão.
- Fingerprints: CSV e PDF do mesmo banco costumam ter descrições diferentes ("LOJA X" x "LOJA X SAO PAULO BR").
  O diff da substituição usa, além do fingerprint, o casamento aproximado da [anotação órfã](09-revisao-e-reconciliacao.md#anotações-órfãs)
  para transferir confirmação e edições entre versões.

## Perfis de exemplo validados (Inter e Nubank)

`profiles/examples/inter-fatura.yaml` e `nubank-fatura.yaml` foram escritos a partir de faturas reais
(out/2026) e validados contra o texto extraído: **zero linhas não reconhecidas** e soma = total
(Inter R$ 3.870,67 em 44 linhas, 24 parceladas, 2 cartões; Nubank R$ 927,27 em 14 linhas, 6 parceladas,
2 finais de cartão). Os PDFs reais **não** entram no repositório; os testes usam PDFs sintéticos que
imitam esses layouts.

O que esses layouts ensinaram (e o schema de perfil precisa suportar):

| Observado | Banco | Suporte no perfil |
|-----------|-------|-------------------|
| Cabeçalho (nome + cartão + vencimento + valor) repetido no topo de toda página | Inter, Nubank | `page_noise`: linhas removidas antes do parse |
| Datas por extenso: `09 de set. 2026`, `10 SET` | Inter, Nubank | `month_names: pt` + `date_format` |
| Sinal: Inter marca crédito com `+ R$`; Nubank com `−R$` (U+2212, não hífen) | ambos | `sign: plus_is_credit` / `minus_is_credit`; o grupo `sign` aceita `-` e `−` |
| Seções por cartão (`CARTÃO 1234****5678`) | Inter | `card_section` |
| Final do cartão por linha (`•••• 1111`) | Nubank | grupo `card_hint` na regex `line` |
| Seção "Próxima fatura" listando parcelas **futuras** | Inter | `section.end` antes dela — nunca importar |
| Pagamentos durante o mês dentro da lista de despesas (`PAGAMENTO ON LINE`) | Inter | `classify` → `kind: transfer, tag: invoice_payment` |
| Total a pagar R$ 0,00 com despesas de R$ 3.870,67 (pago antecipado) | Inter, Nubank | `total` ≠ `amount_due` (R4.9) |
| Total do período dividido em duas linhas ("compras" + "outros lançamentos") | Nubank | `total.sum_of` |
| Antecipação: parcelas `Antecipada - … Parcela 6/10` + `Desconto Antecipação −R$ 3,63` na mesma fatura | Nubank | `tag: anticipation` / `anticipation_discount` (R7.5) |
| Várias parcelas do **mesmo** plano na mesma fatura (Magalu 09/10 e 10/10; Casas Bahia 08–10/10) | Inter | antecipação feita no banco: reconciliação linha 7 cria a antecipação (ver [09](09-revisao-e-reconciliacao.md#reconciliação)) |
| Subtotal por titular ("Nome R$ 927,27") | Nubank | `ignore` |

`tag: invoice_payment` em fatura = pagamento recebido pelo banco (não é compra, não entra na soma); é
o espelho do débito no extrato (linha 12 da reconciliação), e pode ser usado para marcar a fatura paga
quando o extrato não foi importado.

## Conferência soma x total (R4.4)

Se o perfil extrai `total`, compara com a soma dos lançamentos que contam no total da fatura
(`expense`, `fee`, `refund`, `investment` — tabela em [04](04-modelo-de-dados.md#transactionsjson)),
ignorando as linhas de `ignore`. Diferença > R$ 0,01 → aviso `sum_mismatch` na Revisão, com o valor da diferença.
Esse aviso é o principal detector de "o banco mudou o layout".

## Tela Perfis (R4.3)

- Lista os perfis com contagem de arquivos e erros.
- Editor YAML com validação ao digitar (schema).
- "Testar": escolhe um PDF da inbox e mostra: perfil detectado, header extraído, linhas casadas,
  linhas ignoradas, linhas **não reconhecidas** dentro da seção, soma x total.
- "Ver texto bruto": o texto extraído do PDF, para escrever as regex.
- Salvar grava em `profiles/` e reprocessa os arquivos `unknown_profile` e `error` daquele tipo.

## Plugin Python (escape hatch)

Para layouts que regex não resolve: `profiles/plugins/<nome>.py` com

```python
class Parser:
    id = "banco-y-fatura"
    kind = "fatura"
    def detect(self, text: str) -> bool: ...
    def parse(self, pages: list[str]) -> ParseResult: ...
```

O `ParseResult` é o mesmo do perfil YAML, então o resto do pipeline não muda. Plugins precisam de
teste próprio com PDF sintético.

## Limites de segurança

Regex são escritas por mim, mas mesmo assim: cada arquivo tem tempo máximo de parse (10 s) para uma
regex catastrófica não travar a fila; estourou → `status=error`.

## Como adicionar um banco (passo a passo)

1. Copie o PDF para `inbox/faturas/<banco>/`. Ele vai aparecer como `unknown_profile`.
2. Em Perfis → "Novo perfil", parta de um exemplo de `profiles/examples/`.
3. Use "Ver texto bruto" para escrever `detect`, `header` e `line`.
4. "Testar" até: zero linhas não reconhecidas e soma = total.
5. Salve. O arquivo é reprocessado e vai para a Revisão.
6. Se a senha for necessária, adicione em `secrets/pdf-passwords.yaml`.

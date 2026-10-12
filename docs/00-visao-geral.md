# 00 — Visão geral

[← Índice](README.md)

## O que é

Aplicação web pessoal para guardar **todo o histórico de gastos**: cartões de crédito, contas
bancárias, parcelamentos, assinaturas e renda. Substitui uma planilha Google Sheets anterior,
mantendo todas as funcionalidades dela e adicionando:

- importação automática de **faturas e extratos em PDF** de qualquer banco, a partir de uma pasta;
- **sincronização** com essa pasta (adicionar, alterar ou remover o PDF reflete nos dados);
- **divisão de gastos entre pessoas** e controle do que cada uma deve;
- **antecipação de parcelamentos**.

## Para quem

Uma única pessoa (o operador), na própria máquina. Não há login. "Usuários" na app são as
pessoas para quem os gastos são atribuídos (eu, pais, parceira…), não contas de acesso.

## Como funciona, em uma frase por passo

1. Eu coloco PDFs de fatura/extrato em `inbox/`.
2. A app detecta o arquivo, calcula o hash, descobre o banco pelo [perfil](06-perfis-de-banco.md) e lê os lançamentos.
3. Os lançamentos vão para a [Revisão](09-revisao-e-reconciliacao.md) já com categoria e [divisão](08-divisoes-e-acertos.md) sugeridas.
4. Eu confiro, ajusto e confirmo.
5. Os painéis (resumo, projeção, a receber) se atualizam.
6. Se eu apagar o PDF, os lançamentos dele somem; se eu recolocar, minhas edições voltam.

```
inbox/*.pdf ──► sync (hash) ──► perfil de banco ──► Revisão ──► dados confirmados ──► painéis
```

## Princípios

| Princípio | Consequência |
|-----------|--------------|
| A pasta é a fonte dos dados importados | Sem PDF, sem lançamento importado ([05](05-sincronizacao.md)) |
| Nada importado entra sem eu confirmar | Toda importação passa pela Revisão ([09](09-revisao-e-reconciliacao.md)) |
| Nunca contar duas vezes | Para cada cartão e mês, o total vem do real **ou** do projetado ([07](07-regras-de-negocio.md#real-x-projetado)) |
| Dados legíveis e portáteis | JSON em disco ([04](04-modelo-de-dados.md)) |
| Offline e local | Nada sai da máquina ([13](13-seguranca.md)) |
| Tudo testado parte por parte | [Processo](10-processo-de-desenvolvimento.md) e [testes](11-estrategia-de-testes.md) obrigatórios |

## Fora de escopo

Login e acesso por várias pessoas, hospedagem pública, integração direta com bancos (Open Finance),
OCR de PDF escaneado, envio de dados para LLM ou serviço externo, app mobile.

## Próximo

[01 — Glossário](01-glossario.md)

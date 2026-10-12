# 14 — Operação: rodar, backup, restaurar, problemas comuns

[← Índice](README.md)

> Os comandos abaixo são **planejados** e passam a existir na Fase 0 (T0.4). Até lá esta página é a
> especificação deles.

## Pré-requisitos

Docker, docker compose e [Task](https://taskfile.dev) (go-task v3). Nada mais (sem Python/Node na
máquina). **Não há Makefile**: todos os comandos são tasks do `Taskfile.yml`.

## Primeira execução

```bash
mkdir -p data inbox/faturas inbox/extratos profiles secrets
cp profiles/examples/*.yaml profiles/          # opcional: partir dos exemplos
touch secrets/pdf-passwords.yaml && chmod 400 secrets/pdf-passwords.yaml
task up                                         # http://127.0.0.1:8080
```

## Comandos

| Comando | O que faz |
|---------|-----------|
| `task up` | Sobe o container de uso em segundo plano |
| `task down` | Para |
| `task dev` | Backend com reload + Vite com hot reload |
| `task test` | Testes de backend e frontend em containers |
| `task coverage` | Backend com gate de 90% |
| `task lint` | ruff, mypy, eslint, tsc |
| `task e2e` | Playwright contra o container de uso |
| `task trace` | Verifica que cada requisito das tasks concluídas tem teste |
| `task ci` | Tudo que o CI roda (test, coverage, lint, trace, docs-check, auditoria de dependências) |
| `task build` | Build da imagem |
| `task docs-check` | Verifica links quebrados entre os markdowns de `docs/` e `specs/` |
| `task backup` | Copia `data/` para `data/.backups/<timestamp>/` |

## Configuração (variáveis de ambiente)

| Variável | Padrão | Função |
|----------|--------|--------|
| `DATA_DIR` | `/app/data` | Pasta dos JSON |
| `INBOX_DIR` | `/app/inbox` | Pasta monitorada |
| `PROFILES_DIR` | `/app/profiles` | Perfis de banco |
| `SECRETS_FILE` | `/run/secrets/pdf-passwords.yaml` | Senhas de PDF |
| `SCAN_INTERVAL_SECONDS` | `60` | Varredura periódica |
| `PARSE_TIMEOUT_SECONDS` | `10` | Tempo máximo de leitura por PDF |
| `BACKUPS_KEEP` | `20` | Backups mantidos |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `TZ` | `America/Sao_Paulo` | Fuso usado em "hoje" e no mês atual |

## Backup e restauração

- Automático: antes de cada importação e migração (`data/.backups/`, mantém `BACKUPS_KEEP`).
- Manual: `task backup`.
- Fora da máquina: copie `data/`, `profiles/` e `secrets/` (este último com cuidado).
- Restaurar: `task down`, substituir `data/` pelo backup, `task up`. A varredura inicial reconcilia
  com o conteúdo atual da `inbox/` (arquivos que não existem mais têm seus lançamentos removidos).

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---------|----------------|-------------|
| PDF não aparece | Arquivo fora de `inbox/faturas` ou `inbox/extratos`, ou ainda copiando | Tela Status → "Varrer agora" |
| `unknown_profile` | Nenhum perfil reconhece | [06 › Como adicionar um banco](06-perfis-de-banco.md#como-adicionar-um-banco-passo-a-passo) |
| `error: senha inválida` | Senha errada/ausente | Ajustar `secrets/pdf-passwords.yaml` e varrer |
| Aviso `sum_mismatch` | Layout do banco mudou ou linha não reconhecida | Perfis → Testar → ver linhas não reconhecidas |
| Total do mês dobrado | Bug de reconciliação | Abrir bug com o cenário; ver [09](09-revisao-e-reconciliacao.md#por-que-não-há-dupla-contagem) |
| App não sobe: "lock held" | Outra instância rodando | `task down` / parar a outra instância |

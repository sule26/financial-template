# 14 — Operação: rodar, backup, restaurar, problemas comuns

[← Índice](README.md)

## Pré-requisitos

Docker, docker compose e [Task](https://taskfile.dev) (go-task v3). Nada mais (sem Python/Node na
máquina). **Não há Makefile**: todos os comandos são tasks do `Taskfile.yaml`.

## Primeira execução

```bash
task init     # cria data/, inbox/{faturas,extratos}, profiles/, secrets/pdf-passwords.yaml (0400)
cp profiles/examples/*.yaml profiles/   # opcional: começar pelos perfis de exemplo (Inter, Nubank)
task up       # http://127.0.0.1:8080  (outra porta: APP_PORT=8090 task up)
```

Coloque PDFs/CSVs em `inbox/faturas/<qualquer pasta>/` e `inbox/extratos/...`. A varredura roda ao
iniciar, a cada 60 s e quando a pasta muda; a tela Status tem "Varrer agora".

## Comandos (`task --list`)

| Comando | O que faz |
|---------|-----------|
| `task init` | Cria as pastas locais e o arquivo de senhas |
| `task up` / `task down` / `task logs` | Sobe, para e acompanha o container de uso |
| `task dev` | Backend com reload (porta 8000) + Vite com hot reload (http://127.0.0.1:5173) |
| `task test` | Testes de backend e frontend em containers |
| `task coverage` | Backend com gate de 90% (total e por pacote) + frontend com gate de 80% |
| `task lint` / `task format` | ruff + mypy + tsc + eslint / formatação automática |
| `task trace` | Cada requisito das tasks concluídas tem teste (`task trace -- --all` para todas) |
| `task docs-check` | Links e âncoras entre os markdowns |
| `task audit` | Vulnerabilidades conhecidas das dependências (pip-audit, npm audit) |
| `task build` | Imagem de produção `expense-tracker:local` |
| `task e2e` | Playwright contra um container descartável da imagem de produção |
| `task ci` | lint + coverage + trace + docs-check + build + audit (o mesmo do GitHub Actions) |
| `task backup` | Cópia de `data/*.json` em `data/.backups/<timestamp>-manual/` (nunca rotacionada) |

`task e2e` não faz parte do `task ci` (precisa subir a stack); rode antes de concluir uma fase.

## Configuração (variáveis de ambiente)

| Variável | Padrão | Função |
|----------|--------|--------|
| `APP_PORT` | `8080` | Porta publicada em 127.0.0.1 (só no `compose.yaml`) |
| `DATA_DIR` | `/app/data` | Pasta dos JSON |
| `INBOX_DIR` | `/app/inbox` | Pasta monitorada |
| `PROFILES_DIR` | `/app/profiles` | Perfis de banco (editáveis pela tela Perfis) |
| `PROFILES_EXAMPLES_DIR` | `/app/profiles-examples` | Perfis de exemplo embutidos na imagem |
| `SECRETS_FILE` | `/run/secrets/pdf-passwords.yaml` | Senhas de PDF |
| `SCAN_INTERVAL_SECONDS` | `60` | Varredura periódica |
| `PARSE_TIMEOUT_SECONDS` | `10` | Tempo máximo de leitura por arquivo |
| `BACKUPS_KEEP` | `20` | Backups automáticos mantidos |
| `ENABLE_WATCHER` | `1` | Reagir a eventos da pasta (a varredura periódica continua) |
| `ALLOWED_HOSTS` | — | Hosts extras aceitos além de `127.0.0.1`/`localhost` (separados por vírgula) |
| `LOG_LEVEL` | `INFO` | Nível de log (sem valores/descrições, docs/13) |
| `TZ` | `America/Sao_Paulo` | Fuso usado em "hoje" e no mês atual |
| `HOST` / `PORT` / `STATIC_DIR` | `0.0.0.0` / `8080` / `/app/static` | Internos do container |

## Backup e restauração

- Automático: antes de cada importação e migração (`data/.backups/`, mantém `BACKUPS_KEEP`).
- Manual: `task backup` (sufixo `-manual`, nunca apagado pela rotação).
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
| Porta 8080 ocupada | Outro serviço local | `APP_PORT=8090 task up` |
| `task up` ok, container "healthy", mas http://127.0.0.1:8080 não carrega | VPN roteando a sub-rede do Docker (ex.: `ip route get <ip do container>` sai pela interface da VPN) | O compose fixa a rede em `192.168.240.0/24`; se ela também colidir, troque o `subnet` em `compose.yaml` e rode `task down && task up` |
| Aviso "nova versão não pôde ser lida" | O arquivo mudou e a nova versão falhou (senha, timeout) | A versão anterior continua valendo; corrija e "Reprocessar" |

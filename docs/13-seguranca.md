# 13 — Segurança

[← Índice](README.md) · Decisão: [design.md › Decisão 5](../specs/expense-tracker-web/design.md)

Os dados são financeiros e pessoais. O modelo de ameaça é: **máquina pessoal, um operador, sem
exposição à rede**.

## Controles

| Risco | Controle |
|-------|----------|
| Acesso pela rede | Porta publicada só em `127.0.0.1`. **Não há autenticação, por decisão.** Expor em outra interface exige implementar autenticação antes |
| Requisição forjada por outro site aberto no navegador (CSRF / DNS rebinding) | API só aceita `Host` `127.0.0.1`/`localhost`; mutações exigem header `X-Requested-With`; CORS desabilitado |
| Senhas de PDF vazarem | `secrets/pdf-passwords.yaml` fora de `data/`, montado read-only, modo 0400, fora do git; nunca em log, API ou erro |
| Dados no git | `data/`, `inbox/`, `secrets/`, perfis reais e PDFs no `.gitignore`; fixtures de teste sintéticas |
| Path traversal | Todo caminho vindo da API é resolvido e precisa estar dentro de `inbox/`; symlinks para fora são ignorados |
| PDF malicioso | Parse em processo com timeout por arquivo; só leitura de texto (sem executar JavaScript/anexos do PDF) |
| Regex catastrófica no perfil | Timeout por arquivo; vira `status=error` |
| Plugin Python | Executa com os privilégios da app: só coloque plugins que você escreveu |
| Container | Usuário não-root, rootfs read-only, escrita só em `data/` e `profiles/` (editor de perfis), `inbox/` montado read-only, `cap_drop: ALL`, `no-new-privileges` |
| Clickjacking / sniffing | Toda resposta com `X-Frame-Options: DENY`, `Content-Security-Policy` (`frame-ancestors 'none'`, `default-src 'self'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` |
| Build | `.dockerignore` impede que `faturas/`, `inbox/`, `data/`, `secrets/` e PDFs/CSVs cheguem ao daemon Docker |
| Logs | Sem descrição/valor de lançamentos: access log do uvicorn desligado (as query strings têm valores) e falhas de job registram só o tipo do erro |
| Dados para terceiros | Nenhum. App offline; nenhuma dependência faz chamada de rede em runtime |
| Supply chain | Dependências pinadas; `pip-audit` e `npm audit` (nível high) no `task ci`. Imagens base pinadas por tag **e digest** (`Dockerfile`, `backend/Dockerfile.dev`, `Taskfile.yml`, `docker-compose.yml`; ao atualizar, troque os quatro) |

## Checklist ao mexer em algo sensível

- [ ] Algum dado novo é segredo? Então vai para `secrets/`, não para `data/`.
- [ ] Algum endpoint novo recebe caminho de arquivo? Validar prefixo `inbox/`.
- [ ] Algum log novo inclui valor/descrição? Rebaixar para DEBUG.
- [ ] Alguma dependência nova? Licença, pin e auditoria.

# Autonomia neste repositório

Arquivo **versionado** (o `.kiro/` entra no git). Sem dados pessoais nem caminhos absolutos aqui.

Autorização explícita do operador (2026-10-12), válida para qualquer agente trabalhando neste repositório:

## Pode fazer sem pedir permissão

- Criar, editar, mover e apagar **qualquer arquivo dentro deste repositório** (código, testes, docs,
  specs, configs, Taskfile, Dockerfile, compose, perfis de exemplo, fixtures sintéticas).
- Usar **Docker** e **docker compose** à vontade: build de imagens, containers descartáveis, subir e
  derrubar a stack local, rodar todos os testes, lint, cobertura, e2e.
- Rodar `task <qualquer>` e criar/alterar tasks no `Taskfile.yml`.
- Instalar dependências **dentro dos containers** (pinadas, licença permissiva).
- Ir e voltar quantas vezes precisar: implementar, testar, revisar, refatorar, até todas as tasks de
  `specs/expense-tracker-web/tasks.md` estarem corretas e validadas.
- Acionar subagents (revisor, refutador, test-author) sem perguntar.

## Não pode

- Nada de Kubernetes, kubectl, helm, AWS, ou qualquer infra/serviço fora desta máquina.
- Mexer fora deste repositório (exceto arquivos temporários em `/tmp`, que devem ser limpos).
- Ler ou copiar para o repositório dados de `faturas/`, `inbox/`, `data/`, `secrets/` (PDFs reais só
  podem ser lidos em container descartável para entender layout; nada pessoal vai para arquivos versionados).
- `git commit` / `git push` (continua exigindo aprovação do operador).
- Chamadas de rede em runtime da app ou envio de dados para serviços externos (download de imagens
  Docker e pacotes no build é permitido).

## Ferramentas

- Orquestração de comandos: **Taskfile** (`task`, go-task v3). **Não usar Makefile.**
- Sem Python/Node no host: tudo roda em container via `task`.

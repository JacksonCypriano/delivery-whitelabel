# Deploy blue/green

Este pacote substitui o deploy de produção atual por duas versões do `web`:
`web-blue` e `web-green`. Apenas uma recebe tráfego; a outra é criada, testada
e validada antes da troca do Nginx. Celery, beat, PostgreSQL e Redis continuam
únicos para não duplicar tarefas.

## Aplicação inicial

1. Copie os arquivos do pacote na raiz do projeto e mantenha as permissões de
   execução dos scripts.
2. Ajuste o compose de produção conforme o arquivo de referência incluído.
3. Execute uma vez: `bash scripts/prod/blue_green_deploy.sh`.

## Deploy e rollback

* Deploy: `bash scripts/prod/blue_green_deploy.sh`
* Rollback: `bash scripts/prod/blue_green_rollback.sh`

O script cancela se houver alterações locais, se não estiver na `main`, se os
testes falharem, se o health check falhar ou se o Nginx não validar. Neste caso
o tráfego permanece na versão anterior.

## Automação

O workflow `.github/workflows/deploy-production.yml` executa o deploy em cada
push na `main`. Cadastre no repositório os secrets `VPS_HOST`, `VPS_USER`,
`VPS_PORT` e `VPS_SSH_PRIVATE_KEY`. A chave pública correspondente deve estar
em `~/.ssh/authorized_keys` do usuário `deploy` na VPS.

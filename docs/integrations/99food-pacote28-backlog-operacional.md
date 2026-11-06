# Pacote 28 — sincronização de backlog 99Food sandbox (sem POST)

## Escopo e garantias

- Seleção paginada de webhooks **assinados e em quarentena**, para pedidos **já importados** da própria loja.
- `orderNew`, eventos não homologados e pedidos ainda não importados **não entram** na fila de sincronização local e continuam preservados.
- Cursor por ID crescente; eventos com envelope inválido não bloqueiam páginas seguintes. `sync_existing` revalida assinatura persistida, tenant, status e estado terminal, com transações e locks.
- Nenhum acesso HTTP à 99Food, nenhuma alteração de credenciais, nenhuma conexão em modo live, nenhum reenvio de confirmação/cancelamento/finalização.
- A API `GET integrations/99food/backlog/` e o painel de telemetria são somente leitura.
- Não é uma nova homologação de `deliveryStatus`, reembolso ou modalidades não comprovadas.

## Execução de homologação (no contêiner backend HML)

```sh
python manage.py process_99food_backlog --tenant vitrine-demo --limit 50 --pages 10
```

A saída apresenta os eventos elegíveis, páginas percorridas e `next_cursor` caso ainda haja backlog. Para **aplicar apenas eventos já conhecidos e vinculados**, de modo explícito, após conferir o preview:

```sh
python manage.py process_99food_backlog --tenant vitrine-demo --limit 50 --pages 10 --apply
```

Esse comando não envia POST à 99Food. Nunca rode em produção; requer `FOOD99_SANDBOX_ENABLED=1`, `FOOD99_SANDBOX_IMPORT_TO_ORDERS=1`, `FOOD99_LOCAL_EVENT_SYNC_ENABLED=1`, `CHANNELS_LIVE_ENABLED=0` e `CHANNELS_NETWORK_ENABLED=0`, além do settings module HML.

## Testes

```sh
./test-critical-back.sh homolog
./test-critical-front.sh
# Teste adicional se a suite crítica não incluir novos arquivos:
# python manage.py test apps.channels.test_food99_backlog_p28 --settings=config.settings.hml
```

Não houve deploy automático nem habilitação de flags. A verificação de sintaxe não substitui a execução das suítes no WSL.

## Pendências externas

Continuam exigindo documentação e/ou sandbox oficial: pedidos `delivery_type=0/1`, `deliveryStatus`, solicitações de cancelamento/reembolso e confirmação real com concorrência de múltiplos workers. Só considerar produção após evidência operacional verificável e autorização explícita.

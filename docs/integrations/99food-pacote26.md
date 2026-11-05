# Pacote 26 — Diagnóstico e recuperação conservadora (99Food)

## Escopo

- API `GET /api/merchant/integrations/99food/telemetry/` (prefixo depende do roteamento existente): isolada à homologação e ao administrador autenticado da loja via `MerchantAPI`.
- Visão React em `integracoes/99food/diagnostico`, com agregados de Inbox, Outbox, quarentena e alertas sem payloads ou tokens.
- Comando `recover_99food_uncertain`: somente sandbox HML, sem envio à 99Food; por padrão apenas visualização.
- Estados `sending` com mais de 120 segundos são considerados potencialmente enviados e **não** são repetidos. `--apply` marca como `uncertain` para exigir reconciliação oficial/humana.
- Eventos bloqueados intencionalmente na quarentena continuam contabilizados, mas não são automaticamente classificados como falha.

## Segurança

Não cria, edita ou exclui pedidos; não altera pagamentos, estoque, KDS, iFood, webhooks ou status oficiais. Não habilita nenhuma flag. A rotina de recuperação modifica apenas o estado local de comandos sandbox, com filtro por tenant, OneShot e tempo mínimo, e exige `--apply`.

## Execução

```bash
# Na raiz do projeto, em seu ambiente Docker/WSL de homologação:
./test-critical-back.sh homolog
./test-critical-front.sh

# Testes específicos pelo gerenciador já utilizado no projeto:
python manage.py test apps.channels.test_food99_operations_p26 --settings=config.settings.hml

# Consultar antes de alterar qualquer estado (exige DB e settings da HML):
python manage.py recover_99food_uncertain --tenant-slug vitrine-demo --settings=config.settings.hml

# SOMENTE após auditoria e conferência, para marcar como incerto (não reenvia):
python manage.py recover_99food_uncertain --tenant-slug vitrine-demo --apply --settings=config.settings.hml
```

Os comandos do Django devem ser executados no ambiente que possui as dependências e o banco correto (por exemplo, dentro do contêiner backend). **Não executar --apply automaticamente**.

## Pontos ainda necessários para liberação integral

A validação efetiva de entregas pela plataforma (`deliveryStatus`), reembolsos e solicitações de cancelamento depende do contrato oficial da 99Food e de testes reais no sandbox. Concorrência multi-worker, cronologia real de webhooks e a operação automática ponta a ponta também precisam de homologação de integração; passar testes locais não equivale a essa homologação.

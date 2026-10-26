# Correção de três falhas na suíte crítica — 26/10/2026

Este ZIP completo foi reconstruído a partir de `vemdedelivery-react-gratuidades-corrigido-completo.zip` sem modificar código de produção, migrations, telas ou integrações. Foi corrigido somente `apps/core/tests_critical/test_react_completion.py`.

## O que foi ajustado

1. **Concorrência de gratuidades:** o sinal `apps.billing.signals.new_store_subscription` cria automaticamente `Subscription` ao criar `Tenant`. O `setUp` de `FreeDaysConcurrencyTests` não deve executar novamente `Subscription.objects.create(tenant=...)`: agora consulta a assinatura existente usando `.get(tenant=...)` e preserva os dois testes reais de concorrência.
2. **Exclusão em massa no SuperAdmin:** `PlanAdmin` herda de `GlobalAdmin`, que bloqueia exclusão inclusive para superusuários. HTTP **403** é o comportamento correto. O teste de recusa por item protegido com HTTP **400** e posterior reaproveitamento de seleção agora usa `MarketplaceCategory`, recurso que admite exclusão. Foi acrescentado teste separado para garantir que planos continuem protegidos com HTTP **403** e a seleção não seja consumida.

## Validação disponível

- Sintaxe Python: OK.
- Testes integrados Django/PostgreSQL: **não executados aqui**, pois este ambiente não dispõe de Django nem Docker.
- Nenhuma alteração aplicada em produção.

## Executar no WSL na raiz do projeto de homologação

```bash
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py test \
  apps.core.tests_critical.test_react_completion.ReactCompletionTests.test_rejected_superadmin_bulk_delete_keeps_selection_available \
  apps.core.tests_critical.test_react_completion.ReactCompletionTests.test_superadmin_cannot_delete_billing_plans \
  apps.core.tests_critical.test_react_completion.FreeDaysConcurrencyTests -v 2
```

Depois execute a suíte completa:

```bash
bash test-critical.sh homolog
```

**Observação:** os dois testes de concorrência eram interrompidos durante o `setUp` pelo erro de assinatura duplicada. Ainda não há evidência, a partir do log original, de que a execução concorrente em si passou ou falhou. Se surgir outro erro dentro do teste após essa correção, diagnostique o novo traceback antes de declarar a suíte aprovada.

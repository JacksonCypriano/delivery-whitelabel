# Pacote 15 — KDS / Cozinha

Implementado para homologação em 08/10/2026. Produção não alterada.

Rota React `/painel/cozinha/`: aguardando preparo, em preparo e prontos;
prioridade, tempo de espera/preparo, atraso, observações e adicionais,
entrega/retirada, ações grandes e tela cheia.

API GET `/api/merchant/kitchen/` e POST `/api/merchant/kitchen/<id>/`.
As APIs herdam autenticação, CSRF e isolamento do MerchantAPI.
Reutiliza Order, transition_order, auditoria, outbox e realtime do Pacote 13.
Prioridade gera evento de auditoria, sem mensagem de mudança de status.
Migration orders.0015 adiciona kitchen_priority; nenhum pedido paralelo.

Arquivos: apps/merchant/kitchen.py, frontend/src/features/orders/Kitchen.tsx,
Kitchen.test.tsx, apps/core/tests_critical/test_package15_kitchen.py e migration.
Integrações mínimas: models.Order, orders._order_card, merchant.urls, App.tsx,
MerchantLayout.tsx, style.css e api/orders.ts para expor a nova tela e campo.
Não há novas tarefas Celery; usa as existentes.

Validação local: 780 testes backend, OK (22 ignorados em SQLite); 29 testes
frontend aprovados; build React/SSR e migrations check aprovados.
Evidência: docs/qa/package-15-validation.txt.
Pendente homologação PostgreSQL e teste com duas telas/WhatsApp real controlado.

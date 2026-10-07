# Pacote 13 — Operação completa de pedidos

## Estado

Implementação concluída no código e **candidata à homologação**. Não houve deploy, migrations ou alterações em produção. A validação final depende de `migrate`, build do frontend, suíte crítica e teste manual no ambiente de homologação.

## Objetivo

Transformar a área de pedidos do painel React em uma central operacional única, mantendo Django/DRF como fonte de verdade. O pacote cobre o fluxo do pedido desde a chegada até a entrega e conecta as mudanças de status às notificações do WhatsApp da própria loja.

## Entregas

### 13.1 Máquina de estados e auditoria

Novos estados operacionais:

`Pendente → Confirmado → Em preparo → Pronto → Saiu para entrega → Entregue`

Para retirada, `Pronto → Entregue`. Cancelamento pelo novo fluxo é permitido somente antes do início do preparo para preservar a semântica atual de devolução de estoque.

Cada mudança registra `OrderStatusEvent` com status anterior, novo status, responsável, origem, data/hora e observação. Alterações de previsão também deixam trilha de auditoria.

### 13.2 Central de pedidos React

A rota `/painel/orders` deixou de usar a listagem genérica e recebeu uma visão operacional por colunas, com:

- pedidos ativos separados por status;
- ações rápidas de transição;
- total, cliente, itens, forma de recebimento e origem;
- previsão e destaque de atraso;
- histórico recente de finalizados;
- tela de detalhe operacional;
- impressão de comanda pelo navegador;
- layout responsivo para desktop e celular.

### 13.3 Atualização em tempo real e alertas

Foi adicionado WebSocket ASGI em `/ws/merchant/orders/`, autenticado pela sessão Django e isolado pelo tenant do host. Redis é usado apenas como transporte de eventos. Não foi adicionada dependência nova: o projeto já possui ASGI/Uvicorn e `redis`.

Eventos de criação/alteração do pedido e atualização de pagamento publicam um aviso de atualização. O frontend consulta novamente a API, que continua sendo a fonte autoritativa. Se o WebSocket cair, existe polling de recuperação a cada 30 segundos.

O lojista pode habilitar alerta sonoro e notificação do navegador para novos pedidos.

### 13.4 Previsão de preparo

A loja pode configurar um tempo padrão e alterar a previsão de um pedido específico. A previsão é exibida no painel e pode ser informada pelo agente ao cliente enquanto o pedido estiver confirmado/em preparo.

### 13.5 WhatsApp automático por mudança de status

Foi criado um outbox durável (`OrderStatusNotification`). A mudança de status grava a mensagem na mesma transação do pedido; o envio externo ocorre depois pelo Celery. Há uma tentativa imediata e um job periódico de recuperação a cada 15 segundos.

A loja pode ligar/desligar individualmente avisos de:

- confirmado;
- em preparo;
- pronto;
- saiu para entrega;
- entregue;
- cancelado.

Mensagens substituídas por um status mais novo são ignoradas para evitar avisos atrasados. Falha no Evolution não desfaz a mudança de status e permanece registrada para nova tentativa.

### 13.6 Consulta de status pelo agente

O agente do WhatsApp agora pode consultar o pedido recente vinculado ao próprio número do cliente e responder de forma determinística. A consulta é restrita ao tenant e ao telefone do remetente; um número diferente não recebe os dados do pedido.

### 13.7 Pedido manual

Nova rota `/painel/orders/novo` para pedidos recebidos por balcão, telefone ou atendimento humano. O formulário usa o catálogo existente e reaproveita as regras de servidor para:

- preço atual;
- adicionais/opções;
- meio a meio;
- quantidade mínima/máxima;
- estoque;
- entrega/retirada;
- taxa de entrega;
- formas de pagamento presencial.

O navegador nunca envia preço como fonte de verdade: cotação e criação são recalculadas no backend. Pedido manual entra imediatamente na mesma fila operacional e recebe origem `Balcão / telefone`.

## Proteção de rascunhos do checkout

O checkout web já criava um `Order` de revisão antes de o cliente confirmar o envio. Esses rascunhos **não entram na central operacional**, não podem sofrer transição pelo novo endpoint e não são consultados pelo agente. Um pedido web só passa a ser operacional depois do ponto de confirmação atual (`whatsapp_opened_at`). Pedidos manuais entram imediatamente; pedidos criados pelo agente já chegam finalizados nesse sentido.

## Modelos/migration

Migration: `apps/orders/migrations/0013_order_operations.py`

Alterações em `Order`:

- novos status;
- `source`;
- `status_updated_at`;
- `estimated_ready_at`;
- telefone passa a aceitar vazio para pedido de balcão.

Na migration, os pedidos existentes recebem `status_updated_at = created_at` como backfill conservador, evitando que todo o histórico anterior pareça ter mudado de status no momento do deploy.

Novos modelos:

- `OrderStatusEvent`;
- `OrderNotificationSettings`;
- `OrderStatusNotification`.

## Novos endpoints do lojista

Todos sob `/api/merchant/` e protegidos pela sessão/permissão/tenant já existentes:

- `GET orders/`
- `GET orders/<id>/`
- `POST orders/<id>/transition/`
- `POST orders/<id>/estimate/`
- `GET|POST orders/settings/`
- `GET orders/manual/catalog/`
- `POST orders/manual/quote/`
- `POST orders/manual/`

WebSocket:

- `/ws/merchant/orders/`

## Arquivos principais

Backend:

- `apps/orders/choices.py`
- `apps/orders/models.py`
- `apps/orders/operations.py`
- `apps/orders/inventory.py`
- `apps/orders/realtime.py`
- `apps/orders/signals.py`
- `apps/orders/tasks.py`
- `apps/orders/apps.py`
- `apps/orders/views.py`
- `apps/merchant/orders.py`
- `apps/merchant/urls.py`
- `apps/integrations/whatsapp_agent/knowledge.py`
- `apps/integrations/whatsapp_agent/agent.py`
- `apps/integrations/whatsapp_agent/dialogue.py`
- `apps/integrations/whatsapp_agent/checkout_payments.py`
- `apps/integrations/tasks.py`
- `config/asgi.py`
- `config/settings/base.py`

Frontend:

- `frontend/src/api/orders.ts`
- `frontend/src/features/orders/OrdersBoard.tsx`
- `frontend/src/features/orders/OrderDetail.tsx`
- `frontend/src/features/orders/ManualOrder.tsx`
- `frontend/src/features/orders/orderHelpers.ts`
- `frontend/src/routes/App.tsx`
- `frontend/src/style.css`

Testes:

- `apps/core/tests_critical/test_package13_orders.py`
- `frontend/src/features/orders/orderHelpers.test.ts`

## Gates obrigatórios em homologação

1. aplicar migrations;
2. executar `npm ci` e `npm run build` no frontend;
3. executar a suíte crítica completa;
4. criar pedido web e confirmar que só aparece após a confirmação real do cliente;
5. criar pedido pelo agente e confirmar origem WhatsApp;
6. criar pedido manual, validar preço/estoque/taxa e cancelamento;
7. percorrer todos os status em pedido de entrega e retirada;
8. validar atualização em duas abas/dispositivos sem F5;
9. desconectar Redis e confirmar fallback HTTP sem perda do pedido;
10. validar alertas do navegador;
11. validar Evolution conectado e cada aviso configurável;
12. desligar Evolution e confirmar que a mudança de status continua salva e o outbox permanece recuperável;
13. perguntar o status pelo mesmo WhatsApp do pedido e por outro número;
14. validar impressão de comanda desktop/mobile;
15. validar isolamento com duas lojas/tenants.

## Não incluído neste pacote

KDS/cozinha, agendamento novo, recuperação de carrinho, pós-venda, áudio/imagens no agente, CRM/fidelidade, entregadores, iFood e 99Food continuam reservados para os próximos pacotes.

## Produção

**Não promover para produção neste pacote de trabalho.** Primeiro homologação, migrations e suíte crítica verdes, testes manuais e autorização explícita do responsável pelo projeto.

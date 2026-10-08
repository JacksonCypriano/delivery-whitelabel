# Pacote 16 — Agendamento e automações

Implementação para homologação; recursos desativados por padrão.

- Checkout React aceita agendamento opcional. Backend valida modalidade,
  loja ativa, antecedência (15–1440 min), horizonte (1–30 dias), intervalos
  e funcionamento que atravessa meia-noite. Preço e estoque continuam nos
  serviços existentes e são reconferidos na confirmação. Estoque é consumido
  na confirmação, inclusive para pedidos futuros; não é promessa de reposição.
- Carrinho: somente conta com telefone verificado e consentimento explícito
  naquela loja. O cliente pode salvar/revogar a preferência no carrinho.
  Visitantes anônimos não recebem mensagens automáticas.
- Pós-venda com nota 1–5 e comentário. Link opaco individual, escopo da loja,
  validade de 90 dias, CSRF e uma avaliação por pedido entregue.
- Reativação por dias sem compra, uma tentativa por última compra.
- Limite compartilhado: uma tentativa/cliente/loja a cada 7 dias, 9h–21h.
  Conversas pausadas são respeitadas. Consentimento e compra rechecados no envio.
- Outbox registra texto, destinatário, tentativa, resultado e compra posterior.
  Timeout é ambíguo: não repetir automaticamente, evitando duplicação.

Tela `/painel/automacoes/`. GET/POST `/api/merchant/sales/` usa MerchantAPI.
Público: POST `/preferencias/mensagens/`; GET/POST `/avaliacao/<token>/`.
Tasks `apps.orders.sales.plan_sales_messages` (beat 5 minutos) e
`deliver_sales_message`. Não houve envio real durante o desenvolvimento.

Migration orders.0016: Order.scheduled_for, SalesSettings, MarketingConsent,
SalesMessage, OrderFeedback. Novos arquivos: automation_models.py,
scheduling.py, sales.py, sales_views.py, merchant/sales.py, Sales.tsx e testes.
Integrações mínimas: checkout/views e orders/views validam o horário; models
registra novos modelos; URLs e navegação expõem telas; DTOs expõem agendamento;
tasks/base settings registram beat; camada React pública inclui preferências.

Limites: não inclui agendamento via conversa WhatsApp; cliente usa checkout.
Conversão indica compra posterior, sem afirmar causalidade. O envio depende
 de Evolution conectado, worker e beat. PostgreSQL e provedor real devem ser
validados em homologação. Não alterar produção.

Validação do pacote: 789 testes backend OK (22 ignorados), 31 frontend,
build e migrations check. Revalidação integrada: final-validation.txt.

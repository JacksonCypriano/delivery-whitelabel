# Pacote 18 — CRM, fidelidade e analytics

Tela React `/painel/crm/`, GET/POST `/api/merchant/crm/`, mesma autorização,
tenant e CSRF. Visão por cliente: entregas, gasto, ticket médio, última compra,
produtos recorrentes, cupons utilizados, avaliações, origem/UTM e observações.
Segmentos: novos (até 1 compra), recorrentes (2+), VIP (R$ 1.000+), frequentes
(5+), alto ticket (média R$ 100+), inativos (30 dias) e aniversariantes do mês.
Aniversário opcional, informado pela loja no perfil. Não inferido.

Pontos configuráveis por reais, somente pedidos entregues a partir da ativação.
Pedido online exige pagamento confirmado. Ledger com chave única por pedido.
Resgate transacional com trava por loja, saldo conferido no backend e chave de
idempotência. Gera CouponCampaign existente, restrito a esse cliente e uma
utilização. Não altera preços, descontos antigos nem cálculos do checkout.

Campanhas criadas desativadas. Ativação explícita na tela; task planeja o público
e usa o outbox do Pacote 16. Consentimento, segmento, pausa e limites rechecados
no envio. Métricas: enviadas e compras posteriores; não atribui causalidade.

Analytics: opt-in usando a preferência existente vdd_analytics_permission.
POST `/eventos/loja/` registra visita/produto/carrinho/checkout uma vez por
sessão/etapa/loja. Rejeita eventos de pagamento enviados pelo navegador.
UTM consentida fica no snapshot do pedido; fonte operacional permanece intacta.
Pedidos e pagamentos confirmados são contados a partir do banco/provedor.
São contagens distintas, não uma taxa de conversão causal entre pessoas.
DataLayer recebe store_visit/store_cart/store_checkout para GTM quando permitido.
GA4/GTM de aquisição existentes preservados. Meta Pixel/CAPI não ativados:
exigem IDs, token e mapeamento/homologação do proprietário.

Migration orders.0017: attribution, CustomerCampaign, LoyaltySettings,
LoyaltyEntry, CustomerProfile, FunnelEvent e vínculo da mensagem à campanha.
Novos arquivos: crm_models.py, orders/crm.py, merchant/crm.py, analytics.py,
CRM.tsx, Analytics.tsx e testes. Alterações aditivas no checkout, DTOs, rotas,
menu, settings, tasks e outbox são necessárias para conectar os recursos.
Tasks: accrue_loyalty e plan_customer_campaigns, a cada 5 min.

Homologação PostgreSQL deve testar duas tentativas simultâneas de resgate,
cupons no checkout, ativação/cancelamento de campanhas e consentimento.
Nenhum envio real ou integração de publicidade foi ativado no desenvolvimento.

Validação do pacote: 801 testes backend OK (22 ignorados), frontend/build
aprovados. Revalidação final integrada: 806 testes backend OK (22 ignorados),
34 frontend e migrations check aprovado.

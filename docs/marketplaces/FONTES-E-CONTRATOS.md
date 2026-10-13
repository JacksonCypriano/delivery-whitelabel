# Fontes oficiais consultadas — 09/10/2026

Consulta às páginas oficiais indexadas. Algumas páginas retornaram 403 na abertura direta; o portal OpenAPI 99Food exigia carregamento JavaScript/acesso não disponível. Nenhuma chamada autenticada de marketplace foi executada.

## Contratos iFood selecionados

| Operação | Contrato implementado | Referência oficial |
|---|---|---|
| Token centralizado | POST `/authentication/v1.0/oauth/token`; formulário grantType/clientId/clientSecret; accessToken/expiresIn | [Authentication centralized](https://developer.ifood.com.br/en-US/docs/food/guides/modules/authentication/centralized) |
| Associação | GET `/merchant/v1.0/merchants`, page/size; aprovação de permissão no portal | [Merchant endpoints](https://developer.ifood.com.br/en-US/docs/food/guides/modules/merchant/endpoints), [Request access](https://developer.ifood.com.br/en-US/docs/getting-started/first-steps/request-access) |
| Eventos | GET `/events/v1.0/events:polling`; array; header x-polling-merchants, até 100 lojas | [Events intro](https://developer.ifood.com.br/en-US/docs/food/guides/modules/events/intro), [Polling referência](https://developer.ifood.com.br/es-CO/docs/food/guides/modules/events/polling-overview) |
| ACK | POST `/events/v1.0/events/acknowledgment`; array de objetos `{id}` únicos, até 10.000 | Mesma referência de polling |
| Detalhes | GET `/order/v1.0/orders/{id}`; normalização Food estrita | [Order details](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/details) |
| Ações | POST `/order/v1.0/orders/{id}/confirm`, `/startPreparation`, `/readyToPickup`, `/dispatch`; aguardar evento | [Order workflow](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/workflow) |
| Cancelamento | GET `/cancellationReasons`; POST `/requestCancellation` com `{ "reason": "CODIGO" }` | [Order cancellation](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/cancellation), [Order endpoints](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/endpoints) |
| Webhook | Um evento por POST; X-IFood-Signature; HMAC SHA-256 hexadecimal sobre bytes brutos, clientSecret | [Webhook request](https://developer.ifood.com.br/en-US/docs/food/guides/modules/events/webhook-request), [Signature](https://developer.ifood.com.br/pt-BR/docs/guides/order/events/delivery-methods/webhook/signature) |
| Recuperação | Persistir antes do ACK; deduplicar; polling de reconciliação; respeitar retenção e limites | [Best practices](https://developer.ifood.com.br/en-US/docs/getting-started/documentation/best-practices), [Webhook practices](https://developer.ifood.com.br/en-US/docs/food/guides/modules/events/webhook-best-practices), [Improper use](https://developer.ifood.com.br/en-US/docs/getting-started/documentation/improper-use) |
| Agendamento | Janela e preparação informadas; sem antecipar preparo/despacho | [Scheduled orders](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/scheduled-orders) |

Base HTTP fixa: `https://merchant-api.ifood.com.br`. Nenhum URL de rede pode ser definido pelo lojista.

**Divergências observadas:** páginas gerais de Order mostram `/order/v1.0/orders:polling` com envelope `events`; a referência específica Events mostra `/events/v1.0/events:polling` com array. Este adaptador adota exclusivamente a referência específica Events; não faz tentativa de endpoints alternativos. O schema de detalhes usa `schedule`, enquanto o guia de agendamento também exemplifica `scheduled`; os dois nomes documentados são aceitos. A justificativa livre do operador é auditada localmente, mas o cancelamento envia `reason` como código conforme o guia atual de Order; não reutiliza o payload diferente de Shipping. Conferir esses contratos no aplicativo de teste é um bloqueio de homologação, não uma afirmação de interoperabilidade já comprovada.

## 99Food

[Portal Developers 99Food](https://developer-food.99app.com/) e [OpenAPI](https://developer-food.99app.com/pt-BR/openapi). O portal descreve cadastro/qualificação, aplicação, sandbox, depuração, aceite e autorização. Contratos autenticados não foram obtidos. Portanto não há endpoint, assinatura, payload ou token 99Food inventado no código.

As fixtures sintéticas não são capturas de produção e não comprovam homologação. A fixture iFood exercita o contrato selecionado; a fixture 99Food exercita somente o DTO interno.

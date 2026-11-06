# Pacote 29 — visibilidade de entrega 99Food no sandbox

## Contexto homologado

Pedido local #9, externo `5764698886316820920`, modalidade `MERCHANT`, atingiu `out_for_delivery`.
`confirmed` e `ready` foram confirmados pela Outbox e respectivos webhooks.
A tentativa `delivered` gerou a Outbox #11 em `awaiting`, uma única tentativa.
Não houve `orderFinish` processado; o pedido deve continuar `out_for_delivery`.
O `handover_code` de quatro dígitos observado não substitui um possível localizador/código exigido por página externa.

## Alterações de escopo seguro

- Cards operacionais (Kanban/KDS) mostram aviso específico de entrega pendente e não afirmam sucesso.
- Diálogo explica que a finalização depende da 99Food e que não se deve repetir a operação.
- API de pedidos exibe `sync_target`, `sync_command_id`, `sync_sent_at` e `food99_delivery_pending` sem expor segredos ou códigos.
- Telemetria sinaliza comandos `delivered` em `awaiting` mesmo antes de 5 minutos; preserva o tratamento de `uncertain`.
- Comando administrativo `audit_99food_delivery` inspeciona estado local da Inbox/Outbox sem escrita, rede, código ou dados privados.
- Testes verificam isolamento de tenant, não repetição e ausência de efeitos colaterais.

## Uso do diagnóstico (somente leitura)

```bash
python manage.py audit_99food_delivery --tenant vitrine-demo --order-id 5764698886316820920
```

Em VPS, executar dentro do backend HML. Não usar `--apply`, não chamar `send_reserved_action`, não alterar `Outbox` ou `Order` diretamente.

## Restrições

- Não muda contrato ou endpoint da 99Food, não adivinha códigos, não reenvia POST.
- Não habilita produção/iFood nem muda flags ou migrations.
- `awaiting` por si só não prova entrega concluída; `orderFinish` ou validação oficial devem ser conferidos.
- Requisitos de código/localizador de sandbox permanecem dependentes da documentação/suporte 99Food.

## Revisão: responsabilidade pela entrega (29.1)

- `delivery_by=PLATFORM`/`IFOOD`: o entregador da plataforma confirma no aplicativo da plataforma; a loja acompanha webhooks. Nenhuma solicitação de código no Kanban ou Logística.
- `delivery_by=MERCHANT`: motoboy próprio é responsável pela confirmação usando o fluxo oficial aplicável do marketplace; a loja acompanha pendência. O sistema NÃO possui ainda autenticação nem tela individual de motoboy para esta integração; não simular tal funcionalidade.
- `UNKNOWN`: não inferir responsabilidade. Confirmar na plataforma.
- A listagem `marketplace_orders` da API de Logística é **somente leitura**, limitada a 150 pedidos ativos da loja autenticada. POSTs atuais de atribuição/despacho/comprovação continuam bloqueando todos os pedidos `ifood`/`99food`.
- A página Logística separa pedidos locais (com comprovação interna) dos marketplaces (somente acompanhamento).
- A confirmação oficial da 99Food continua pendente para o pedido #9, Outbox #11 `awaiting`; não inventar código ou reenviar.
- Futuro: autenticação de motoboy, consentimento/permissões, vínculo seguro por pedido, confirmação oficial suportada por contrato do provedor e callbacks idempotentes. Esses recursos NÃO fazem parte deste pacote.

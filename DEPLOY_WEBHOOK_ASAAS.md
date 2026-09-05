# Webhook de aprovação das subcontas Asaas

Este pacote recebe os eventos de situação cadastral da subconta e libera o
recebimento online somente quando o Asaas enviar
`ACCOUNT_STATUS_GENERAL_APPROVAL_APPROVED`.

## Variáveis de produção

No `.env` usado pelo Compose, mantenha:

```dotenv
BILLING_ENABLED=true
ASAAS_ENVIRONMENT=production
ASAAS_API_KEY=<chave da conta-pai>
ASAAS_WEBHOOK_TOKEN=<token aleatório com pelo menos 32 caracteres>
ASAAS_WEBHOOK_URL=https://seu-dominio.com/integracoes/asaas/webhook/
```

O endereço precisa ser público, usar HTTPS e apontar para esta aplicação. Ao
criar a subconta, o sistema tenta cadastrar nela um webhook sequencial com os
eventos de aprovação. Se `ASAAS_WEBHOOK_URL` ainda estiver vazio ou o cadastro
do webhook falhar, o Celery consulta as subcontas pendentes a cada cinco
minutos como contingência.

## Publicação

Depois de aplicar os arquivos, execute o deploy habitual e confirme que os
processos `celery` e `celery-beat` estão ativos. Não há migração de banco para
este recurso.

## Teste rápido

1. Crie/edite uma conta de pagamentos online em uma loja de homologação e
   aceite os termos.
2. Simule ou aguarde o evento de aprovação geral do Asaas.
3. Confira no admin que a situação mudou para **Aprovada** e que um pedido com
   Pix/cartão passou a oferecer o checkout online.
4. Reenvie o mesmo evento: ele deve ser aceito sem duplicar processamento.

O token do cabeçalho `asaas-access-token` é validado antes de qualquer evento
ser salvo. A chave API da subconta continua criptografada e não aparece no
admin, nos logs ou nas mensagens ao lojista.

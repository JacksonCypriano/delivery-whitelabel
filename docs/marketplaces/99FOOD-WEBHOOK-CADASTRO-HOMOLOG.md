# 99Food — webhook inicial para cadastrar o aplicativo de teste

## Entrega

Foi acrescentada a rota Django `GET/HEAD/POST /integracoes/99food/test/webhook/`, isolada do webhook iFood e **sem nenhuma alteração de migrations**.

- `GET` e `HEAD`: HTTP **200** para verificar que a URL existe; GET retorna `{"provider":"99food","mode":"test","events_enabled":false}`.
- `POST`: HTTP **503**, cabeçalho `Retry-After: 300`; não salva o payload, não cria pedidos nem responde ACK fictício.
- Payloads superiores a 128 KiB retornam HTTP **413**.
- `/integracoes/99food/live/webhook/` e outros modos retornam **404**.

**IMPORTANTE:** este endpoint serve somente para **cadastrar/testar a existência da URL**. Não está pronto para receber eventos reais. O portal pode recusar o cadastro se exigir um POST de validação; nesse caso precisamos seguir o handshake oficial antes de prosseguir. **Não autorize lojas nem gere pedidos de teste enquanto POST continuar respondendo 503.**

## URL para informar no portal

`https://<DOMINIO-HTTPS-PUBLICO-DE-HOMOLOGACAO>/integracoes/99food/test/webhook/`

O endereço de homologação deve ser público, HTTPS válido e encaminhar a rota para o Django. **Nunca** usar `localhost`, `lvh.me` local ou o domínio de produção. Não usar o webhook do iFood nem um serviço de terceiros para simular recebimento de pedidos.

## Validar (depois de aplicar os arquivos em homologação)

```bash
curl -i 'https://<DOMINIO-HTTPS-PUBLICO-DE-HOMOLOGACAO>/integracoes/99food/test/webhook/'
curl -i -X POST 'https://<DOMINIO-HTTPS-PUBLICO-DE-HOMOLOGACAO>/integracoes/99food/test/webhook/' -H 'Content-Type: application/json' --data '{}'

docker compose -f docker/dev/docker-compose.yml exec -T backend \
  python manage.py test apps.channels.test_webhook_99food -v 2
bash test-critical.sh homolog
```

O primeiro deve retornar **200** e o segundo **503**. **Isso não significa que a plataforma já esteja integrada**, só que a rota está acessível.

## Para completar a integração oficial

Baixe no portal autenticado 99Food o arquivo **OpenAPI YAML** (ou exporte as páginas equivalentes) que detalhe: assinatura e cabeçalhos de webhook, desafios/handshake, formato dos eventos, IDs de estabelecimento e pedido, consulta de detalhes, autenticação/renovação, comandos, cancelamentos, validação da autorização do lojista e erros/limites. Com esse contrato, implementar adapter e testes reais no sandbox; só então habilitar processamento em Inbox/Outbox.

Mantenha o iFood e os pedidos nativos intocados. Nenhuma alteração em `.env` ou banco é necessária para essa etapa de cadastro de URL.

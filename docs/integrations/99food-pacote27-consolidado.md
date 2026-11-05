# 99Food — Pacote 27 consolidado: readiness e auditoria transversal

## O que entra

- Auditoria **somente leitura** de prontidão local, organizada em verificações internas e dependências externas.
- Auditoria de integridade de vínculo tenant/pedido, comandos antigos ou incertos, Inbox com erros, envelopes inválidos, quarentena com `app_shop_id` divergente e resíduos de cancelamento terminal.
- Comandos de gerenciamento para obter diagnóstico sem acessar SQL nem abrir payloads/token.
- Painel React de diagnóstico atualizado com critérios de liberação, modalidades dos pedidos, pendências externas e achados de integridade.
- Testes de isolamento, limites de relatório, ausência de POST, validação de estado e proteção contra uso fora da HML.
- Correção preventiva no diagnóstico da Inbox para ignorar quarentena somente quando o payload for objeto válido.

## Testes na raiz do repositório

```bash
./test-critical-back.sh homolog
./test-critical-front.sh
```

O arquivo `apps/channels/test_food99_readiness_p27.py` é novo. Se o script crítico mantiver uma lista fixa e não descobrir esse arquivo, também execute dentro do ambiente Django de homologação:

```bash
python manage.py test apps.channels.test_food99_readiness_p27 --settings=config.settings.hml
```

## Auditorias reais na HML (no contêiner backend)

```bash
python manage.py audit_99food_readiness --tenant-slug vitrine-demo --settings=config.settings.hml
python manage.py audit_99food_integrity --tenant-slug vitrine-demo --settings=config.settings.hml
```

Versões JSON (para capturar evidências operacionais e comparar depois):

```bash
python manage.py audit_99food_readiness --tenant-slug vitrine-demo --json --settings=config.settings.hml
python manage.py audit_99food_integrity --tenant-slug vitrine-demo --json --settings=config.settings.hml
```

Esses comandos não enviam GET/POST à 99Food, não alteram dados e não exigem habilitar o piloto. Não publique os relatórios fora da equipe; eles incluem IDs internos.

## Limites de interpretação

- Suítes unitárias passing **não** comprovam concorrência multi-worker, entrega da plataforma, retirada real, `deliveryStatus`, reembolso ou solicitação de cancelamento originada na 99Food.
- Os itens externos ficam `external_pending` **intencionalmente** até haver documentação e homologação real. O relatório **sempre** retorna `release_authorized=false`.
- A seção de integridade usa amostragem limitada por categoria. Não equivale a varredura exaustiva em base grande.
- O código desta entrega **não** habilita flags, não registra tarefas periódicas, não chama a API da 99Food e não muda pagamentos, KDS ou status de pedidos.
- A ativação do piloto automático para loja sandbox é uma operação distinta, explicitamente aprovada após auditoria; ela não é realizada por este pacote.

## Escopo ainda necessário antes de encerrar a integração

1. Executar pedidos completos automáticos no sandbox autorizado, incluindo restart e duplicidade de workers.
2. Solicitar à 99Food exemplos reais das modalidades `delivery_type=0` e `delivery_type=1` e dos respectivos webhooks.
3. Formalizar e testar `deliveryStatus`, reembolso e cancelamento iniciado pela plataforma/cliente.
4. Validar operação assistida e rollout de produção com autorização oficial, métricas e procedimento de reversão.

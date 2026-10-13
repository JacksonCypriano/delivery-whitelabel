# Relatório da entrega multicanal — 09/10/2026

Base: ZIP `vemdedelivery.zip` anexado nesta conversa. Código alterado em cópia local isolada; nenhum acesso a credenciais reais, banco remoto, deploy ou promoção para produção.

## Resultado e limites

**Não considerar homologação oficial concluída.** O pacote contém a implementação local e os meios de homologação. A API real 99Food não está implementada. O iFood possui adaptador de rede baseado nos contratos oficiais consultados, ainda sem execução autenticada ou aceite do provedor.

| Área | Situação |
|---|---|
| Core multicanal, isolamento, inbox/outbox, regras operacionais | Implementado; testes locais automatizados |
| Cards, detalhes, KDS/Novos, fullscreen existente e configurações React | Implementado; testes de componentes e build |
| iFood autenticação, merchant, eventos, detalhes, ações e assinatura | Código implementado; chamadas verificadas com mocks/fixtures |
| 99Food pedidos no core e nas duas telas | Somente simulação interna; não representa protocolo 99Food |
| Simulador persistente e repetição de eventos | Implementado; execução local em processos separados |
| PostgreSQL, concorrência real e suíte crítica no Docker homolog | Pendente: PostgreSQL/Docker indisponíveis neste ambiente |
| Layout em browser real/tablet/monitor e fullscreen nativo | Roteiro automatizado entregue; execução pendente |
| Credenciais, autorização real e homologação iFood/99Food | Pendente; nenhuma credencial real foi usada |

## Verificações executadas

- Django `check`: sem problemas.
- `makemigrations --check --dry-run`: sem migrations faltantes.
- `migrate` em SQLite isolado: aplicado, incluindo orders/0019 e channels/0001–0003. Nenhum dado de produção foi lido ou alterado.
- Suíte agregada: **861 testes, OK, 23 ignorados por condições do ambiente**. Isso corresponde a 838 testes executados com sucesso, não a 861 testes aprovados em PostgreSQL. O teste concorrente novo é um dos ignorados em SQLite.
- App channels: **53 testes, OK, 1 ignorado** (concorrência PostgreSQL).
- React/Vitest: **44 testes aprovados em 15 arquivos**.
- TypeScript e builds Vite do painel, público e SSR: aprovados.
- Scripts operacionais: **13 testes aprovados**.
- Simulador CLI em SQLite persistente: duas plataformas, repetição da mesma chave em processos distintos, sem duplicação.

A primeira execução da suíte identificou a necessidade do SSR local e uma regressão em `OrderItem.get_total_price()` quando o WhatsApp usa itens temporários sem pedido. O acesso foi protegido, um teste de regressão foi incluído e a suíte foi reexecutada. Não foram alteradas expectativas de testes antigos para esconder falhas.

As verificações JSDOM exercitam a identificação e a permanência dos cards dentro do monitor ao acionar fullscreen com a API do navegador mockada. Elas **não validam pixels, media queries nem fullscreen nativo**. O Chromium não estava instalado e seu download não produziu um arquivo utilizável; por isso a execução visual real permanece pendente, sem alegação de aprovação.

Comandos principais:

```bash
# Requer public-ssr/server.mjs ativo na URL interna de SSR durante a suíte.
python manage.py test apps.channels.tests apps.orders apps.accounts apps.merchant.tests apps.billing.tests apps.tenants.tests apps.integrations.tests apps.prospecting apps.core.tests_critical apps.marketplace.tests_marketing_acquisition --settings=config.settings.test_sqlite --noinput
npm test --prefix frontend
npm run build --prefix frontend
python -m unittest discover -s scripts/tests -p 'test_*.py'
# Gate ainda obrigatório no ambiente do projeto:
bash test-critical.sh homolog
```

Para QA visual, iniciar Vite em `127.0.0.1:5178` e executar `scripts/browser/marketplaces.mjs` com Playwright/Chromium instalados. `PLAYWRIGHT_MODULE` pode apontar para o `index.mjs` do Playwright em uma pasta de ferramentas isolada. O roteiro testa 390, 768, 1920 e 2560 px, Pedidos Ativos e KDS, entrada/saída de fullscreen, ausência de overflow da página e presença das três faixas; só intercepta APIs locais fictícias e gera screenshots em `output/marketplace-browser`.

## Arquivos

A lista compara os bytes do pacote com o ZIP anexado, sem dependências, caches e `staticfiles` coletados. Assets compilados têm hashes novos; a arquitetura de build foi preservada. Não há banco, `.env` com valores privados, chaves ou certificados no pacote entregue.

### Alterados

- `apps/billing/online.py`
- `apps/merchant/kitchen.py`
- `apps/merchant/logistics.py`
- `apps/merchant/orders.py`
- `apps/merchant/urls.py`
- `apps/orders/admin.py`
- `apps/orders/choices.py`
- `apps/orders/inventory.py`
- `apps/orders/models.py`
- `apps/orders/operations.py`
- `apps/orders/tasks.py`
- `config/settings/base.py`
- `config/settings/prod.py`
- `config/settings/test.py`
- `config/urls.py`
- `frontend/src/api/orders.ts`
- `frontend/src/features/orders/Kitchen.tsx`
- `frontend/src/features/orders/OrderDetail.tsx`
- `frontend/src/features/orders/OrdersBoard.tsx`
- `frontend/src/features/orders/TransitionDialog.tsx`
- `frontend/src/layouts/MerchantLayout.tsx`
- `frontend/src/routes/App.tsx`
- `frontend/src/style.css`
- `test-critical.sh`

### Adicionados

- `.env.example`
- `LEIA-ME-MARKETPLACES.md`
- `apps/channels/__init__.py`
- `apps/channels/apps.py`
- `apps/channels/connectors.py`
- `apps/channels/fixtures/ifood_food.json`
- `apps/channels/management/__init__.py`
- `apps/channels/management/commands/__init__.py`
- `apps/channels/management/commands/bind_marketplace.py`
- `apps/channels/management/commands/link_marketplace_product.py`
- `apps/channels/management/commands/reconcile_marketplaces.py`
- `apps/channels/management/commands/simulate_marketplace_orders.py`
- `apps/channels/migrations/0001_initial.py`
- `apps/channels/migrations/0002_externalorder_financials.py`
- `apps/channels/migrations/0003_externalorder_platform_notes_and_more.py`
- `apps/channels/migrations/__init__.py`
- `apps/channels/models.py`
- `apps/channels/normalize.py`
- `apps/channels/services.py`
- `apps/channels/simulator.py`
- `apps/channels/tasks.py`
- `apps/channels/tests.py`
- `apps/channels/views.py`
- `apps/orders/migrations/0019_alter_order_payment_flow_alter_order_source.py`
- `docs/INTEGRACOES-MARKETPLACES.md`
- `docs/marketplaces/FONTES-E-CONTRATOS.md`
- `docs/marketplaces/RELATORIO-ENTREGA.md`
- `frontend/src/features/integrations/MarketplaceIntegrations.tsx`
- `frontend/src/features/orders/ChannelBand.test.tsx`
- `frontend/src/features/orders/ChannelBand.tsx`
- `frontend/src/features/orders/MultichannelScreens.test.tsx`
- `scripts/browser/marketplaces.mjs`
- `static/merchant/.vite/manifest.json`
- `static/merchant/assets/main-C-sBdhnA.css`
- `static/merchant/assets/main-D9BaSNNY.js`
- `static/public/.vite/manifest.json`

### Substituições de assets gerados

- `static/merchant/assets/main-B2l01lLW.js` — substituído pelo build atual.
- `static/merchant/assets/main-BGzf1C9J.css` — substituído pelo build atual.
- `static/merchant/assets/main-BOmqsQwi.js` — substituído pelo build atual.
- `static/merchant/assets/main-BkmIJgV6.css` — substituído pelo build atual.
- `static/merchant/assets/main-CBJ7BAEW.css` — substituído pelo build atual.
- `static/merchant/assets/main-CD2ZMRJ8.js` — substituído pelo build atual.
- `static/merchant/assets/main-CGBwTI-X.js` — substituído pelo build atual.
- `static/merchant/assets/main-CYfVZWRr.css` — substituído pelo build atual.
- `static/merchant/assets/main-CkSYuQfe.js` — substituído pelo build atual.
- `static/merchant/assets/main-CukWBAO8.css` — substituído pelo build atual.
- `static/merchant/assets/main-DR-930UB.js` — substituído pelo build atual.
- `static/merchant/assets/main-boYWTXrV.js` — substituído pelo build atual.

Consulte `docs/INTEGRACOES-MARKETPLACES.md` para instalação, operação, checklist de cadastro e lista completa de funcionalidades não implementadas. Consulte `FONTES-E-CONTRATOS.md` para as referências e divergências documentais que precisam de confirmação em sandbox.

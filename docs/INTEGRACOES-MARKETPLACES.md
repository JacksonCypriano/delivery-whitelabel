# VemDeDelivery — integração multicanal para homologação

**Estado da entrega: implementação local testável; não homologada pelos marketplaces e não liberada para produção.** Nenhuma credencial real foi usada. Não houve implantação no servidor do cliente.

## O que está disponível

- Django/DRF e o fluxo operacional existente continuam responsáveis pelos pedidos. O app `channels` acrescenta conexões, pedidos externos, caixa de entrada durável e fila de comandos. Não substitui o módulo `orders`.
- Pedidos Ativos, KDS, detalhes/comanda e seus monitores exibem VemDeDelivery (verde), iFood (vermelho) e 99Food (amarelo). Web, WhatsApp e balcão mantêm os valores históricos de `source`.
- Pedidos externos pendentes aparecem em **Novos** no KDS; pedidos próprios pendentes continuam fora da cozinha, como antes. Número interno, ID externo, adicionais, observações, agendamento e ações são preservados.
- Realtime usa o Redis/WebSocket já existente e seu fallback HTTP. O botão de som precisa ser ativado pelo operador, conforme a política de áudio do navegador. O KDS também oferece som e destaque de entradas novas.
- Solicitações externas são persistidas antes do envio. O painel aguarda um evento da plataforma para confirmar a mudança. HTTP 202 não conclui o pedido localmente.
- Seção `/painel/integracoes`: solicitação de vínculo, modo de teste/simulação, estabelecimento, último sincronismo, erro, desconexão e histórico paginado (10/25/50/100).

### iFood

Adapter para aplicação **centralizada**, com autenticação, token cifrado, renovação após expiração/401, estabelecimentos autorizados, polling, ACK, detalhes Food, assinatura de webhook, confirmação, início do preparo, pronto, despacho próprio e solicitação de cancelamento com motivo consultado dinamicamente. Os contratos estão discriminados em [FONTES-E-CONTRATOS.md](marketplaces/FONTES-E-CONTRATOS.md).

Escopo de importação: categoria FOOD, DELIVERY/TAKEOUT, itens com quantidade inteira. Agendamento usa janela e início de preparo informados pela plataforma. Não inicia preparo antes do horário informado; não despacha antes do agendamento; nunca despacha retirada ou entrega IFOOD. Prazos locais de preparo são estimativas, não alterações do prazo contratado com o marketplace.

### 99Food

**O adaptador de rede não está implementado.** `BlockedConnector` falha explicitamente em autorização, consulta, polling, comandos e normalização. A documentação pública acessível confirmou a existência do portal e sandbox, mas não forneceu contratos suficientes para implementar essas operações com segurança.

O modelo comum, interface do conector, telas, filas, regras de tenant e simulador funcionam para a origem `99food`. A fixture é um DTO **interno do VemDeDelivery**, não um suposto payload da 99Food. Para concluir, são necessários contratos oficiais liberados à integradora, regras de assinatura/autorização, catálogo de eventos/status, sandbox e homologação. Cadastro sozinho não transforma esse stub em integração real.

## Segurança, consistência e recuperação

1. O tenant vem da sessão e do host; jamais do corpo de eventos externos. A combinação fornecedor + modo + merchant tem um único proprietário. O lojista não pode associar arbitrariamente IDs alcançáveis pelo token global.
2. O vínculo real é administrativo, após conferir autorização e propriedade da loja. Segredos de aplicativo ficam no ambiente do backend/worker; token e snapshot do provedor usam a criptografia Fernet já existente em `apps.billing.secrets`. Nenhum deles é retornado ao React.
3. Preserve `SECRET_KEY` e os backups. A troca dessa chave exige planejamento de recifragem; não há nova rotina automática de rotação neste pacote. Endereços e itens mantêm o armazenamento utilizado pelos pedidos atuais.
4. Eventos são únicos por conexão/ID; pedidos por conexão/ID externo. Locks seguem conexão → pedido externo → pedido local. A caixa de entrada é gravada antes do ACK; reiniciar worker não perde o trabalho persistido.
5. Eventos atrasados/regressivos não retrocedem pedidos. Eventos desconhecidos ficam registrados e, quando há pedido, geram aviso para conferência no portal. Estados terminais conflitantes exigem revisão.
6. Retentativas têm atraso exponencial. Leituras/importações param em 10 tentativas; HTTP 404 de detalhes para após 10 minutos desde o recebimento. O evento passa a `blocked`, sem apagar seu histórico. Após corrigir a causa, o operador pode reprocessar somente as leituras bloqueadas.
7. Comando com timeout/5xx ou worker interrompido após envio passa a `uncertain`; não é reenviado cegamente. Polling e eventos posteriores reconciliam estados conhecidos. Se o provedor perdeu o evento ou expirou sua retenção, é necessário conferir no portal. Não há promessa de recuperação ilimitada nem endpoint de status inventado.
8. Desconectar suspende novas ações e recebimento local; conserva pedidos, eventos e vínculos de estoque. Uma requisição já em voo pode terminar. Revogue também a permissão no portal para remover a autorização externa.

### Estoque, pagamentos e contatos

- Nunca criar Asaas para `ifood`/`99food`, mesmo se alguém alterar indevidamente o campo de pagamento. Fluxos `marketplace` e `marketplace_due` distinguem pagamento antecipado de saldo na entrega.
- Total, desconto, frete, taxas adicionais, valores pagos/pendentes e totais de linha são preservados. O snapshot cifrado conserva benefícios/subsídios e demais detalhes recebidos. Não há conciliação financeira de repasses, comissões ou emissão fiscal por marketplace nesta entrega.
- Estoque só é debitado quando chega um estado de aceitação/preparo ou posterior; usa o ledger existente, uma vez por pedido. Cancelamento confirmado devolve apenas o que foi debitado, uma vez.
- O operador deve mapear `externalCode` para o produto local. Item sem vínculo ou estoque insuficiente não desaparece: permanece com aviso. Não há baixa retroativa automática ao criar um vínculo. Adicionais não têm composição/BOM de estoque separada neste pacote; vincule o SKU correspondente e homologue essa regra.
- Clientes externos não são associados automaticamente ao CRM. Telefone fica vazio e não há envio de notificações do agente/WhatsApp. O snapshot não é um consentimento para contato.
- O módulo atual de atribuição/comprovação de entregadores continua restrito aos pedidos próprios. Pedidos externos usam despacho permitido no painel multicanal e conclusão recebida da plataforma.

## Instalar em homologação

Trabalhe em uma cópia/branch de homologação e em banco separado, com backup. Não extraia este ZIP sobre a pasta de produção. Não copie `.env` de produção nem chaves reais.

1. Instale as dependências conforme o README do projeto. O pacote não inclui `node_modules`, ambiente virtual, banco ou segredos.
2. Acrescente as variáveis do `.env.example` deste pacote ao `docker/dev/.env` existente, preservando DB, Redis, Django e configurações já usadas em homologação. Não substitua todo o arquivo por esse complemento.
3. Para simulação sem APIs: `CHANNELS_SIMULATOR_ENABLED=1`, `CHANNELS_NETWORK_ENABLED=0`, `CHANNELS_LIVE_ENABLED=0`. O processo com `config.settings.prod` força simulador desligado.
4. Compile e suba os serviços de homologação:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
docker compose -f docker/dev/docker-compose.yml up -d --build db redis public-ssr backend celery celery-beat
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py migrate
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py check
bash test-critical.sh homolog
npm test --prefix frontend
```

Use **um beat** por ambiente. Os workers comuns descobrem `apps.channels.tasks` pelo Celery existente. Polling executa a cada 30 segundos; filas a cada 5 segundos. O polling divide estabelecimentos em lotes de até 100. Não exponha um endpoint novo em produção durante essa instalação.

Migrations adicionadas: `orders/0019` altera apenas choices; `channels/0001`, `0002`, `0003` criam tabelas e campos novos. Nenhum RunPython reescreve origens, preços ou históricos existentes. Não desfaça migrations que já contenham pedidos externos; prefira desativar conexões e interromper os workers enquanto investiga.

## Simular as duas plataformas

É preciso existir uma loja de homologação. Substitua `minha-loja` pelo slug dela:

```bash
docker compose -f docker/dev/docker-compose.yml exec -T backend python manage.py simulate_marketplace_orders --tenant minha-loja --provider all --order-key demo-1
```

Abra `https://<host-da-loja-de-homologacao>/painel/operacao` e `/painel/cozinha`. Os cards têm **SIMULAÇÃO**. Confirmar/iniciar preparo/cancelar cria comandos duráveis; o worker local gera eventos de simulação, sem internet. Repetir a mesma chave/evento não duplica o pedido.

Outros cenários:

```bash
# Outro pedido, retirada e pagamento na entrega
python manage.py simulate_marketplace_orders --tenant minha-loja --provider ifood --order-key retirada-1 --pickup --payment-due
# Evento externo de aceitação; a mesma chave identifica o pedido já criado
python manage.py simulate_marketplace_orders --tenant minha-loja --provider all --order-key demo-1 --event CONFIRMED
python manage.py simulate_marketplace_orders --tenant minha-loja --provider all --order-key demo-1 --event CANCELLED
# Processar filas manualmente no ambiente local quando não houver worker
python manage.py reconcile_marketplaces --mode test
```

As linhas curtas acima devem ser executadas dentro do backend de homologação ou prefixadas por `docker compose ... exec -T backend`. No último comando, o polling permanece desligado quando `CHANNELS_NETWORK_ENABLED=0`; a fila de simulação ainda é processada. Não envie uma nova fase com parâmetros diferentes esperando editar o snapshot do pedido já importado.

Vínculo opcional para testar estoque (IDs são exemplos, consulte os IDs locais):

```bash
python manage.py link_marketplace_product --tenant minha-loja --connection 1 --external-code DEMO-LANCHE --product 10
```

## Cadastrar o VemDeDelivery e configurar depois

### iFood — aplicativo de teste centralizado

- Criar conta no [Portal iFood Developer](https://developer.ifood.com.br/), identificar a integradora e obter aplicativo/loja de teste.
- Selecionar a aplicação centralizada e os módulos Food/Order, Events, Authentication e Merchant aplicáveis. Confirmar exigências atuais no portal.
- Solicitar permissão da loja pelo fluxo de permissões do aplicativo. O responsável autoriza no Portal do Parceiro. Conferir a relação entre tenant, CNPJ/estabelecimento e merchant ID antes de vincular.
- Somente em homologação, configurar `IFOOD_TEST_CLIENT_ID`, `IFOOD_TEST_CLIENT_SECRET`, `CHANNELS_NETWORK_ENABLED=1`, mantendo `CHANNELS_LIVE_ENABLED=0`. Reiniciar backend, worker e beat para carregar o ambiente. Não colar segredos no React, URLs, terminal como argumento ou tickets.
- Executar o vínculo administrativo:

```bash
python manage.py bind_marketplace --tenant minha-loja --provider ifood --merchant-id ID-AUTORIZADO --mode test --confirm-ownership
```

O comando consulta os estabelecimentos autorizados antes de habilitar; não transfere um vínculo pertencente a outro tenant. A confirmação de propriedade é responsabilidade do operador: o token centralizado por si só não prova a propriedade da conta local.

- Começar com polling; gerar pedido de teste no portal e acompanhar os eventos. Se usar webhook, cadastrar a URL HTTPS **de homologação** `/integracoes/ifood/test/webhook/`, conforme o processo do portal. Validar assinatura, firewall e requisitos de presença antes de optar por webhook como transporte principal. O polling continua ativo neste pacote.
- As credenciais `IFOOD_LIVE_*` e a chave `CHANNELS_LIVE_ENABLED` existem para uma etapa futura. Não há instrução de habilitá-las nesta entrega: dependem de homologação e autorização explícita do proprietário do VemDeDelivery.

### 99Food

- Criar conta e solicitar qualificação da integradora no [portal oficial](https://developer-food.99app.com/).
- Solicitar a documentação OpenAPI/contratos privados, credenciais de aplicativo de teste, loja sandbox e critérios de aceite.
- Obter fluxo exato de autorização por estabelecimento, nomes/formatos das credenciais, URLs por ambiente, assinatura/replay de webhook, eventos, status e ações permitidas, catálogo de erros, pagamentos, logística, agendamento, limites e retenção/reconciliação.
- Implementar esses contratos em um conector real com os mesmos métodos de `IFood`/`BlockedConnector`, adicionar fixtures oficiais anonimizadas e executar homologação. Não reutilizar os contratos iFood para a 99Food.
- Validar autorização da loja e impedir vínculo entre tenants antes de habilitar uma conta. A solicitação no React registra interesse; não executa OAuth da 99Food.

## Checklist obrigatório antes de considerar concluído

- [ ] Migrations e suíte crítica completas no PostgreSQL de homologação, incluindo concorrência; nenhum teste crítico ignorado sem justificativa.
- [ ] Validar navegador real em 390/768/1920/2560 px, tela cheia/retorno com Esc, tablets e áudio após interação. Há roteiro automatizado em `scripts/browser/marketplaces.mjs` (HTTP fictício).
- [ ] Receber pedidos reais **do sandbox** iFood, renovar token, verificar estabelecimento e assinatura; comparar todos os valores com o portal.
- [ ] Validar aceitação, preparo, pronto, entrega própria/plataforma, retirada, agendamento, cancelamento recusado e aceito.
- [ ] Duplicar/reordenar eventos, interromper worker, simular 401/429/5xx e reiniciar; confirmar ausência de dupla baixa ou dupla cobrança.
- [ ] Comparar dois tenants e todos os endpoints sensíveis, inclusive históricos e motivos de cancelamento.
- [ ] Confirmar ausência de chamadas Asaas e WhatsApp para pedidos externos; executar regressão dos pedidos próprios.
- [ ] Formalizar o escopo aceito pelo iFood e concluir critérios de presença/webhook se utilizados.
- [ ] Receber contratos 99Food, implementar o adaptador de rede e concluir seus testes e aceite oficial.
- [ ] Só depois planejar produção e pedir autorização explícita. Este ZIP não a concede.

## Fora do escopo implementado / limitações

Não implementados: API real 99Food; OAuth distribuído iFood; negociação Handshake, cancelamento parcial/ORDER_PATCHED; Grocery/picking, DINE_IN/INDOOR e quantidades fracionárias; sincronização de catálogo/cardápio; rastreamento de entregador, códigos de coleta/entrega e módulo Shipping; conciliação de repasses/comissões; impressão fiscal; heartbeat específico do webhook; aplicação automática de mudanças de itens posteriores ao snapshot inicial; recálculo retroativo de estoque sem vínculo; recuperação de eventos além da retenção do provedor.

Eventos fora do escopo precisam de conferência no portal. Pedidos com modalidade/estrutura não suportada permanecem na caixa de entrada com erro, em vez de inventar dados ou alterar a operação atual. Não anuncie cobertura integral de todos os módulos iFood/99Food com esta versão.

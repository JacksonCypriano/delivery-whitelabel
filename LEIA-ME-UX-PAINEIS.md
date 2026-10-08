# Revisão UX/UI dos painéis — homologação

Atualização do pacote completo 14–19. Não houve publicação nem alteração em produção. Não há migrações novas nesta revisão.

## Alterações

- Campos e botões com espaçamento em CRM/fidelidade, logística, atendimento, produtos e categorias.
- Automações organizadas em quatro grupos com explicações: agendamento, recuperação de carrinhos, avaliações e reativação. Limites dos campos alinhados ao servidor.
- Pedidos ativos e KDS com tela cheia nativa, saída pelo botão ou Esc e mensagem quando o navegador não oferece suporte. Os diálogos permanecem dentro da área de tela cheia.
- KDS mais compacto, com três colunas diferenciadas por cor e rolagem horizontal dentro do quadro em telas pequenas.
- Quadros de pedidos adaptados para celular, telas médias e monitores grandes; pedidos em andamento nunca são ocultados pela paginação.
- Grupos laterais recolhíveis nos dois painéis; realces verdes e laranja preservam a identidade.
- Notas fiscais: proteção contra contexto de navegação ausente, contadores zerados e estrutura de documentos sem registros. O erro relatado não se reproduziu na API local; o teste de regressão cobre a tela vazia sem contexto. Validar o caso original em homologação e consultar o erro do servidor se persistir.
- Tarifas renomeadas para “Tarifas Asaas · somente consulta”. Não existe cadastro de tarifas pelo lojista nessa tela. São condições do provedor; configurações administrativas continuam no painel global.
- “Pedidos e histórico” deixa explícita a diferença em relação a “Pedidos ativos”: a primeira tela inclui finalizados, a segunda prioriza os detalhes dos pedidos em andamento.

## Paginação

Padrão de 10 itens, com opções 25, 50 e 100. A paginação ocorre no servidor, inclusive nas listas administrativas de eventos de segurança, eventos de cobrança e auditoria de cobrança. A opção de carregar tudo é bloqueada nas listas genéricas para manter o limite.

Também paginados: produtos/categorias e demais recursos genéricos, histórico de alterações, histórico da conexão WhatsApp, cobranças, notas fiscais, conversas, entregas concluídas, mensagens de automação, avaliações, clientes/segmentos e campanhas do CRM e pedidos finalizados. O CRM filtra segmentos e pagina clientes antes de carregar os detalhes individuais.

Os pedidos ativos/KDS e seletores de entregadores permanecem completos por necessidade operacional. Detalhes internos de conversa (30 mensagens), checkouts (5), compras e avaliações por cliente (20) continuam como resumos limitados; não são históricos integrais paginados.

## Validação realizada

- Backend: 807 testes executados, 785 passaram e 22 foram ignorados por dependerem de PostgreSQL; nenhuma falha.
- Teste adicional de paginação administrativa passou: três tipos de eventos, páginas sem sobreposição, tamanho 25 e limite defensivo contra parâmetros excessivos.
- Frontend: 36 testes passaram, incluindo notas vazias e falha controlada de tela cheia.
- Compilação TypeScript, frontend merchant/admin, frontend público e SSR concluída.
- Verificação de migrações: nenhuma alteração pendente.
- Relatórios em `docs/qa/ux-*.txt`.

A inspeção visual automatizada não foi concluída: não havia navegador instalado e o download retornou um arquivo inválido. Os testes de interface são em DOM simulado. Conferir visualmente em homologação a 390, 1280 e 1920 pixels e em tela cheia real; validar também PostgreSQL, atualização em tempo real e a ocorrência original da tela fiscal. Os serviços externos e demais pendências do pacote anterior continuam conforme sua documentação.

## Homologação

Usar o procedimento já fornecido em `LEIA-ME-PACOTES-14-A-19.md`, preservando variáveis de ambiente e dados existentes. Os assets compilados atualizados estão incluídos. Verificar menu recolhível, formulários, paginação entre páginas com filtros, notas vazias e preenchidas, KDS com muitos pedidos e entrada/saída de tela cheia. Produção depende de autorização específica.

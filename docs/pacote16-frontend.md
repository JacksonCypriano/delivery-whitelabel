# Pacote 16.3 — frontend consolidado e correções da revisão

Este ZIP substitui os Pacotes 16, 16.1 e 16.2. Aplicar sobre a base original
`vemdedelivery-pacote16-frontend-20261113-134313.zip`, sem necessidade de aplicar
os incrementais anteriores. Também pode ser aplicado sobre a mesma base com o
16.2 já copiado, desde que não existam modificações locais conflitantes.

## Correções 16.3

- `Operations.tsx`: unificados os atributos duplicados em `className="admin-form card"`.
- `Logistics.tsx`: o seletor de entregador é remontado somente quando a atribuição
  confirmada do mesmo pedido muda. Mudanças externas, inclusive retirada da atribuição,
  atualizam o seletor. Atualizações sem mudança preservam a seleção local; outros
  campos de comprovação permanecem montados. Se a atribuição remota mudar durante
  uma escolha local não enviada, prevalece a atribuição confirmada pelo servidor.
- Testes existentes de Comercial, Logística e Automações passam a abrir a aba
  correspondente antes de interagir com seu conteúdo.
- Escritos 10 novos casos de regressão: 3 de sincronização logística, 5 de cadastros
  (salvar, cancelar, validação com arquivo, saída com rascunho, operação pendente)
  e 2 de abas (preservação de rascunho e navegação por teclado).

Revisão somente estática. Nenhum teste, compilador, lint, build, ambiente, chamada
às APIs do projeto, commit, push ou deploy foi executado. Os testes foram escritos
para validação posterior; não há declaração de aprovação funcional ou visual.

O conteúdo do 16.2 foi preservado, exceto os dois arquivos de implementação acima
e a documentação atualizada. A infraestrutura de testes existente foi reutilizada.
Backend, rotas de App, Inbox, KDS, Pedidos Ativos, Kanban e configurações de envio
não receberam novas alterações nesta correção.

## Correções finais do 16.2

- Comparação de seleções múltiplas independente da ordem, sem modificar o FormData enviado.
- Relacionamentos e normalizações de campos notificam o indicador de alterações após atualizar os valores. Consultas antigas de relacionamento são ignoradas.
- CEP ignora respostas obsoletas, campos desmontados/desabilitados e preserva endereços editados enquanto a consulta estava pendente.
- Comparação de alterações suspensa durante salvamento, quando o fieldset desabilitado deixa de participar de FormData. Reenvio bloqueado enquanto os dados salvos são recarregados.
- Confirmação de saída desnecessária é encerrada quando não há alteração/operação pendente; operação em andamento não oferece descarte. Diálogos restauram o foco e aceitam rótulos específicos, preservando os padrões anteriores.
- Roteador mantido para usar useBlocker; erro de renderização usa a mensagem padrão do painel. App e URLs permanecem intactos.
- Impressão acompanha mudanças do parâmetro order na mesma página e seleciona a fila sem desmontar preferências. SectionTabs aceita controle opcional, mantendo o comportamento dos consumidores existentes.

## Correções consolidadas da auditoria

ResourceDetail: o editor é remontado por recurso/ID, isolando formulário, erros, prévia, histórico e indicador dirty. O indicador compara os dados do formulário com o estado inicial, incluindo seleções múltiplas e arquivos. Cancelar restaura o esquema e os valores carregados, mediante confirmação. O salvamento só limpa o indicador após sucesso da API; erros de validação mantêm os inputs e arquivos montados. O formulário fica desabilitado durante a requisição. Respostas de operações de um editor desmontado são ignoradas; o carregamento também identifica sua geração.

Navegação: o ponto de entrada utiliza createBrowserRouter/RouterProvider da dependência já existente, mantendo App e suas rotas. Isso habilita useBlocker nos cadastros: mudanças de rota e histórico pedem confirmação quando há edição pendente; operações em andamento orientam a aguardar. Recarregar/fechar utiliza beforeunload. Eventos de sessão expirada/troca obrigatória de senha não são bloqueados. Não foi criada persistência de rascunho fora da página nem alterada a autenticação.

CSS: separação explícita entre admin-content, inbox-content e operational-content. Regras gerais de formulário, botões, cards, tabelas e espaçamento não alcançam Inbox nem rotas orders/operacao/cozinha. A Inbox mantém os estilos do Pacote 15 e recebe apenas ajustes específicos de foco, cabeçalho, paginação e rolagem de observações. O menu/cabeçalho externo continua compartilhado.

## Áreas refinadas

| Área | Mudança concreta |
| --- | --- |
| Dashboards dos dois painéis | Diretório com busca local e grupos, indicadores e atividades organizados. |
| Cadastros e listagens | Descrições específicas por recurso real, índice de seções, cancelar/restaurar, proteção de saída, erros associados, seleção intermediária e linhas destacadas, filtros e números alinhados. |
| Agente comercial | Abas Conexão, Piloto/alertas, Catálogo, Conhecimento e Atendimento/atividade; acesso direto à Inbox com pendências. |
| Inbox | Escopo visual isolado; área da conversa priorizada; seletor de tamanho sem efeito retirado, mantendo paginação fixa existente. Lógica de envio, takeover e alertas preservada. |
| Prospecção | Estado da campanha sempre visível; importação, janela/velocidade e resultados em abas; carregamento explícito nas ações. |
| Crédito, gratuidade, senha e Evolution | Cabeçalhos contextualizados, organização de formulários, histórico e feedback de salvamento. |
| CRM | Fidelidade, clientes, campanhas e funil/canais separados; mensagens de confirmação somente após resposta da API. |
| Automações | Configurações, avaliações e histórico separados; editar remove a indicação anterior de salvo. |
| Logística | Entregas em andamento como aba inicial; equipe, comprovantes e canais separados; formulários organizados e confirmação de operações. |
| Impressão | Preferências separadas da fila; link vindo de pedido abre a área de impressão; preservação de rascunhos durante atualização; estado não salvo e fila vazia explícitos. Comandos e chaves de impressão mantidos. |
| WhatsApp | Conexão, orientação e histórico separados, com ação de conexão prioritária. |
| Atendimento humano | Cabeçalho com atualização, estado destacado e lista vazia explícita. |
| Assinatura e cobranças | Ofertas separadas do histórico, paginação junto às cobranças, retorno à assinatura, indicação de consulta em andamento. |
| Notas e tarifas | Navegação ativa, tabelas/ações padronizadas e contexto fiscal dos serviços da plataforma. |
| iFood e 99Food | Ações claras, estado de conexão e mensagem de ausência de informação; detalhe usa largura própria. |
| Diagnóstico 99Food | Orientações e backlog em seções expansíveis; critérios de liberação e alertas continuam visíveis. |
| Login e alteração de senha | Erros associados aos campos, foco e estado de envio. |

Os recursos genéricos seguem os registros explícitos merchant e superpanel: loja/identidade/horários/entrega/perfil, produtos/categorias/adicionais/rótulos, clientes/cupons/utilizações; lojas/usuários/segurança, planos/assinaturas/cobranças/créditos/serviços/contas/tarifas, fiscal/auditoria/eventos, WhatsApp/marketing/marketplace/prospecção. O frontend continua usando os campos, ações e permissões retornados pelo backend. Não foram inventadas páginas de relatórios, equipe ou banners independentes onde não existe rota dedicada.

## Componentes e responsividade

SectionTabs mantém conteúdo montado e suporta seleção inicial, teclado e estado ativo. PageHeading centraliza títulos/ações nas páginas específicas. ResourceDirectory agrupa atalhos. Fields, RelationshipInput, Confirm, Feedback e Pagination receberam refinamentos de acessibilidade e apresentação. Grids, navegação mobile, campos longos, overflow de tabelas e abas foram tratados estaticamente. Nenhuma biblioteca foi instalada.

## Preservação e limitações

- Backend, infraestrutura, APIs, payloads, permissões e regras comerciais não foram alterados.
- OrdersBoard, Kitchen, OrderDetail, ManualOrder, TransitionDialog, ChannelBand e CSS operacional original permanecem sem edição. A página administrativa de Impressão foi organizada, mas os comandos de impressão/reimpressão não foram modificados.
- Vitrine, checkout e tema público permanecem sem mudanças. Não há mecanismo de tema escuro no painel React inspecionado; nenhum foi criado.
- A proteção de navegação foi implementada nos cadastros ResourceDetail, não em todos os formulários específicos do produto. A troca de abas mantém os respectivos painéis montados. Não há armazenamento permanente de rascunhos; sair após confirmar descarte perde as alterações, como informado no diálogo.
- Formulários e permissões dinâmicos não foram renderizados com dados reais. Cobertura por recurso usa os renderizadores compartilhados e descrições específicas; não significa uma tela independente reconstruída para cada model.
- Não foram executados testes, build, lint, compilador, servidores, containers, migrations, chamadas às APIs do projeto, screenshots, commit, push ou deploy. A conferência foi por leitura estática de código. Nenhum resultado visual em navegador está sendo declarado.
- Prioridade de validação local: bloqueio de navegação/voltar/avançar, salvar/cancelar cadastros com arquivos e inlines, erros de API, redirecionamentos de sessão, abas com rascunhos e comparação de Inbox/KDS/Pedidos Ativos.

## Aplicação no WSL

Salve o ZIP em /home/jacksoncypriano/projects:

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel
unzip -o /home/jacksoncypriano/projects/vemdedelivery-pacote16.3-frontend-consolidado.zip -d .
```

## Validação — comandos para executar posteriormente

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel
./test-critical-back.sh
./test-critical-front.sh
```

## Adicionar os arquivos exatos do pacote ao Git

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel
unzip -Z1 /home/jacksoncypriano/projects/vemdedelivery-pacote16.3-frontend-consolidado.zip | while IFS= read -r arquivo; do
  git add -- "$arquivo"
done
```

## Arquivos modificados/criados em relação ao projeto original

- `frontend/src/admin-workspace.css` (novo)
- `frontend/src/auth/Account.tsx`
- `frontend/src/components/Confirm.tsx`
- `frontend/src/components/Feedback.tsx`
- `frontend/src/components/Fields.tsx`
- `frontend/src/components/formState.ts` (novo)
- `frontend/src/components/PageHeading.tsx` (novo)
- `frontend/src/components/Pagination.tsx`
- `frontend/src/components/RelationshipInput.tsx`
- `frontend/src/components/ResourceDirectory.tsx` (novo)
- `frontend/src/components/SectionTabs.tsx` (novo)
- `frontend/src/features/dashboard/Activity.tsx`
- `frontend/src/features/dashboard/Dashboard.tsx`
- `frontend/src/features/finance/Finance.tsx`
- `frontend/src/features/integrations/Food99Telemetry.tsx`
- `frontend/src/features/integrations/MarketplaceIntegrations.tsx`
- `frontend/src/features/orders/CRM.tsx`
- `frontend/src/features/orders/Logistics.tsx`
- `frontend/src/features/orders/Printing.tsx`
- `frontend/src/features/orders/Sales.tsx`
- `frontend/src/features/resources/ListEditor.tsx`
- `frontend/src/features/resources/ResourceDetail.tsx`
- `frontend/src/features/resources/ResourceList.tsx`
- `frontend/src/features/resources/presentation.ts` (novo)
- `frontend/src/features/superadmin/Commercial.tsx`
- `frontend/src/features/superadmin/CommercialInbox.tsx`
- `frontend/src/features/superadmin/FreeDays.tsx`
- `frontend/src/features/superadmin/Operations.tsx`
- `frontend/src/features/whatsapp/Conversations.tsx`
- `frontend/src/features/whatsapp/Whatsapp.tsx`
- `frontend/src/layouts/MerchantLayout.tsx`
- `frontend/src/main.tsx`
- `docs/pacote16-frontend.md` (novo)


## Arquivos adicionados ou ajustados na correção 16.3

- `frontend/src/features/superadmin/Operations.tsx`
- `frontend/src/features/orders/Logistics.tsx`
- `frontend/src/features/superadmin/Commercial.test.tsx`
- `frontend/src/features/orders/NewModules.test.tsx`
- `frontend/src/features/orders/Sales.test.tsx`
- `frontend/src/features/orders/LogisticsRefresh.test.tsx` (novo)
- `frontend/src/features/resources/ResourceDetail.test.tsx` (novo)
- `frontend/src/components/SectionTabs.test.tsx` (novo)
- `docs/pacote16-frontend.md`
- `docs/pacote16.3-arquivos.txt` (manifesto completo do consolidado)

O restante do ZIP é idêntico ao 16.2 revisado. Aplique apenas o 16.3.

Para versionar a lista exata após aplicar:

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel || exit 1
git add --pathspec-from-file=docs/pacote16.3-arquivos.txt
git diff --cached --stat
git diff --cached
```

Confirme que não há alterações anteriores indevidas no staging. Depois dos testes
locais e da revisão do diff, crie o commit pelo seu fluxo habitual; push e deploy
não são feitos por nenhum comando de aplicação deste documento.

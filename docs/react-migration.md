# Pacote 12 — Migração React do painel do lojista

## Estado e limites da entrega

Implementação candidata à homologação. **A migração não está aprovada como concluída para produção ou cutover definitivo.** O código React, APIs, build estático, testes e documentação fazem parte deste projeto completo; o aceite final depende de PostgreSQL/Docker, suíte crítica na homologação e testes manuais das integrações. Nenhuma operação foi realizada na VPS, homologação remota ou produção.

Migrations novas: **nenhuma**. `makemigrations --check --dry-run` não detectou mudanças. Models, migrations, cálculos, serviços de estoque, fiscal, pagamentos e agente não foram reescritos. Páginas públicas, SEO, sitemap, canonical, schema, GA4 e GTM foram preservados.

## Arquitetura anterior e inventário

O painel principal era `TenantAdminSite` em `/admin/`, com Django/Unfold, ModelForms, formsets e hooks de salvamento que concentram regras importantes. Existia também um dashboard reduzido `/dashboard/`, com autenticação JWT e contadores. O SuperAdmin global também usa a mesma aplicação React em `/painel/` no domínio raiz, enquanto o lojista usa `/painel/` no subdomínio do tenant; o host define o escopo e cada contexto usa API e permissões próprias. O Django Admin global fica temporariamente disponível em `/superadmin-legacy/` apenas como fallback técnico durante a homologação.

O isolamento usa `TenantMiddleware`, que resolve a loja pelo host/subdomínio, combinado com usuário vinculado ao tenant, flags administrativas e querysets/permissões próprios. `ForceInitialPasswordChangeMiddleware` impõe troca da senha temporária no painel antigo.

O inventário detalhado está em **`docs/react-migration-inventory.md`**: 13 recursos, rotas, controladores, templates, models, formulários, campos, relações, ações, JavaScript, APIs e permissões. O detalhamento de cada subpacote está em **`docs/packages/package-12-react-migration.md`**.

## Nova arquitetura

- `/painel/` serve um shell Django com manifest Vite. Navegação, tabelas, formulários, estados e confirmações são componentes React.
- `/api/merchant/` fornece APIs DRF com sessão Django, CSRF, respostas JSON privadas e escopo obrigatório de tenant.
- `apps/merchant/registry.py` continua sendo a allowlist explícita dos 13 recursos do lojista. O SuperAdmin usa `apps/superpanel/registry.py`, uma allowlist separada dos recursos globais; os dois contextos nunca compartilham permissões nem escopo de dados.
- `schema.py` converte campos/valores/erros dos formulários existentes para um contrato JSON. Não envia HTML de templates nem código JavaScript do admin.
- `api.py` reaproveita `get_queryset`, permissões, `get_form`, formsets e hooks `save_form`, `save_model`, `save_related`, ações e log do admin. Isso preserva validação e efeitos colaterais no backend.
- `integrations.py` chama as views financeiras/WhatsApp existentes; `presenters.py` transforma somente os campos públicos permitidos em JSON. Nunca serializa o model inteiro ou chaves Asaas.
- Downloads fiscais usam o serviço existente de arquivos/hashes. Checkout hospedado no Asaas permanece externo, como antes.

Esta é uma migração da interface com adaptador de compatibilidade no backend. Os ModelAdmins/forms continuam sendo dependências executadas pelas APIs; sua remoção exigiria uma extração posterior, com testes, para serviços/formulários independentes. Não removê-los neste pacote.

## Estrutura frontend e componentes

`frontend/src/api/`: cliente, recursos, financeiro, WhatsApp. Uma única chamada `fetch` centralizada, URL relativa de mesma origem, cookies de sessão, CSRF, timeout, erros HTTP e eventos de sessão expirada/senha obrigatória.

`auth/`: login, logout e senha. `layouts/`: menu único responsivo. `routes/`: Router. `features/dashboard/`, `features/resources/`, `features/finance/`, `features/whatsapp/`: telas. Os 13 recursos CRUD/consulta compartilham componentes orientados pelo contrato de forms; não há treze implementações divergentes da mesma validação.

`components/`: Fields/FormFields, Feedback/Notice/Empty, confirmação. `hooks/useQuery`: carregamento, resposta, erro e recarga. `types/`: contrato dos campos. `utils/`: máscaras portadas dos scripts atuais. Estado local com hooks, sem Redux ou bibliotecas extras de estado/formulários.

Componentes principais: MerchantLayout, Dashboard, ResourceList, ResourceDetail, ListEditor, History, Finance, Whatsapp, Account. Campos decimais respeitam a configuração de localização do formulário. Datas/horas compostas são convertidas para as chaves esperadas pelo Django. Imagens usam multipart; inlines conservam management form, IDs, exclusão e validação. Máscaras de WhatsApp, telefone, CPF/CNPJ alfanumérico e horários foram portadas do código anterior. CEP chama a API já existente e permite correção manual.

## Telas e paridade

Disponíveis: dashboard/checklist; minha loja; identidade visual; horários com múltiplos intervalos; regiões e taxas; perfil/publicação; produtos/estoque/promoções/dias/imagens; categorias; grupos, opções e rótulos; meio a meio por ação existente; pedidos, itens, indicadores originais de 30 dias e cancelamento; clientes; campanhas/cupons/seleção de clientes/utilizações; assinatura/planos/adicionais/cobranças/histórico/notas/tarifas; subconta Asaas; WhatsApp/agente; autenticação e senha.

Listas oferecem busca, filtros, ordenação, hierarquia de datas quando existente, paginação e ações selecionadas. Campos `list_editable` permanecem disponíveis em “Editar campos desta página”, usando o formset original, verificação dos IDs da página/tenant e hooks de salvamento existentes. As telas não encaminham o usuário para formulários Django.

Pedidos mantêm os status existentes, sem criação/exclusão administrativa. Clientes e utilizações de cupons continuam somente leitura. Cancelamentos seguem a função de estoque original; publicação segue o checklist original. A proteção de estoque concorrente continua no hook existente e exige validação PostgreSQL.

## Autenticação, tenant e permissões

A sessão é a mesma do Django Admin antigo. Não são criados tokens no localStorage. `TenantAdminAuthenticationForm` é reutilizado, inclusive os rate limits e regras do login. Login anônimo exige CSRF explicitamente. As mutações autenticadas passam pelo SessionAuthentication do DRF. Campos de senha são marcados como sensíveis para relatórios de erro.

Todo endpoint de negócio exige usuário autenticado/ativo/staff/is_tenant_admin, não superusuário, com tenant do usuário igual ao resolvido no host. IDs vêm de querysets já restritos e relações de formulário são limitadas ao tenant. IDs de inlines são também conferidos contra o queryset do pai. Clientes são selecionados somente pelo relacionamento com os pedidos da loja. As permissões de cada ModelAdmin/Inline são verificadas, inclusive em ações e exclusões.

Senha temporária bloqueia os endpoints de negócio até sua alteração. Respostas 401 e 403 têm tratamento na interface; payload com `password_change_required` leva à troca de senha. Respostas privadas recebem `Cache-Control: private, no-store`.

## Endpoints novos

Prefixo `/api/merchant/`:

| Rota | Métodos | Finalidade |
|---|---|---|
| `session/` | GET, POST, DELETE | CSRF/sessão, login, logout |
| `password/` | POST | Alterar senha mantendo sessão |
| `dashboard/` | GET | Checklist, recursos permitidos, contadores e assinatura |
| `resources/:resource/` | GET | Lista, filtros, busca, ordenação, paginação e métricas |
| `resources/:resource/list-edit/` | GET, POST | Edição rápida dos campos permitidos na página atual |
| `resources/:resource/new/` | GET, POST | Schema e criação permitida |
| `resources/:resource/:id/` | GET, POST, DELETE | Consulta/edição e exclusão com confirmação |
| `resources/:resource/actions/` | POST | Ações já existentes sobre seleção escopada |
| `resources/:resource/:id/history/` | GET | Histórico de alterações paginado |
| `finance/` | GET | Assinatura, ofertas e histórico |
| `finance/purchase/` | POST | Formulário/cotação assinada e emissão existente |
| `finance/notes/` | GET | Notas da loja |
| `finance/fees/` | GET | Tarifas da subconta permitida |
| `finance/invoices/:uuid/` | GET | Cobrança da loja |
| `finance/invoices/:uuid/refresh/` | POST | Consulta pelo serviço existente |
| `finance/invoices/:uuid/notes/:kind/` | GET | PDF/XML arquivado, escopo e hashes originais |
| `whatsapp/` | GET, POST | Painel/ações; GET `?format=status` consulta status |

Recursos: `store`, `branding`, `hours`, `delivery`, `profile`, `products`, `categories`, `groups`, `labels`, `orders`, `customers`, `coupons`, `redemptions`.

POSTs de formulário usam multipart/form-data, preservando listas e uploads. Exclusão individual primeiro devolve objetos afetados; somente `?confirm=yes` confirma. Ações destrutivas primeiro devolvem confirmação; o segundo POST exige `confirmed=yes`. A cotação financeira conserva assinatura, vínculo ao tenant, expiração e token de idempotência existentes.

APIs públicas/JWT/webhooks existentes: nenhum contrato alterado. As views de billing e WhatsApp ganharam apresentação JSON exclusivamente quando chamadas pelo adaptador autenticado. Compra financeira inválida pode devolver erros de campo para o React, usando a mesma validação de PurchaseForm.

## Desenvolvimento local

Requisitos: backend existente (Python 3.11, PostgreSQL/Redis do projeto), Node 22 e npm. Manter as variáveis do ambiente de desenvolvimento já usadas pelo projeto. Não usar `test_sqlite.py` como configuração de aplicação ou produção.

```bash
cd frontend
npm ci
npm run build
cd ..
python manage.py collectstatic --noinput
python manage.py runserver 0.0.0.0:8000 --settings=config.settings.dev
```

Abrir `http://SLUG-DA-LOJA.lvh.me:8000/painel/`. A loja precisa existir no banco e o usuário precisa pertencer a ela. Não usar localhost puro para resolver um tenant. Configurações locais de cookie/HTTPS devem seguir o modo de execução existente.

Hot reload opcional, com Django na porta 8000:

```bash
cd frontend
npm run dev
```

Abrir `http://SLUG-DA-LOJA.lvh.me:5173/painel/`. Vite encaminha `/api` e `/media` ao Django preservando o host. Não há CORS novo. Se a configuração local exigir cookies Secure, usar o proxy HTTPS existente ou ajustar somente as configurações locais de cookies para HTTP; nunca alterar o ambiente de produção para resolver desenvolvimento.

## Build, Docker e CI

`npm ci` usa package-lock. `npm run build` executa TypeScript e Vite, gerando `static/merchant/.vite/manifest.json` e assets com hash. O manifest fica na árvore fonte acessada pelo shell Django; collectstatic publica os assets no caminho já atendido pelo proxy. O ZIP inclui o build testado.

Dockerfile ganhou estágio `node:22-alpine`: cópia de package/lock e npm ci em camada cacheável, depois fonte, testes e build. A imagem Python copia somente o resultado para `/app/static/merchant`. Node não é necessário no runtime backend/Celery. Entrypoint, serviços, volumes e proxy existentes foram mantidos.

Homologação monta o checkout sobre `/app`: portanto o build no host/checkout deve existir antes de collectstatic. Um build só dentro da imagem fica oculto pelo bind mount. O ZIP traz assets; após editar o frontend, executar `scripts/test-react.sh` no checkout de homologação antes do deploy.

`merchant-react-checks.yml` adiciona validação de frontend e backend/PostgreSQL em pull requests e push para homolog. Não contém deploy. O workflow de produção preexistente não foi alterado. O CI novo não foi executado em GitHub durante esta entrega.

## Testes e resultados

Resultados locais nesta entrega:

| Verificação | Resultado |
|---|---|
| Django check | Sem problemas |
| Migrations pendentes (`makemigrations --check --dry-run`) | Nenhuma mudança detectada |
| Backend completo, SQLite | 728 testes descobertos, zero falhas, 22 ignorados |
| Novos testes API, incluídos no total | 21 aprovados |
| Módulos da suíte crítica, execução local inicial | 707 testes, zero falhas, 22 ignorados |
| Ferramentas operacionais | 13 aprovados |
| Frontend Vitest | 11 aprovados |
| TypeScript + Vite | Aprovados |
| Chromium local | Login, 17 rotas, criação de categoria, edição de preço e edição rápida em lista, menu mobile e ausência de links Django nas telas verificadas |
| `bash test-critical.sh homolog` | Bloqueado: Docker não encontrado; NÃO aprovado em homolog |
| Integrações reais Asaas/Evolution e concorrência PostgreSQL | Pendentes em homologação |

Os testes ignorados são condicionados ao backend/capacidades existentes. SQLite não comprova locks, concorrência ou comportamento PostgreSQL. Os testes locais usam credenciais fictícias/serviços simulados e não enviaram ações às integrações reais. Evidências resumidas estão em `docs/qa/package-12-validation.txt` e capturas em `docs/qa/`.

Comandos reprodutíveis:

```bash
bash scripts/test-react.sh
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python manage.py test apps.merchant.tests --settings=config.settings.test --noinput
python manage.py test --settings=config.settings.test --noinput
python -m unittest discover -s scripts/tests -p 'test_*.py' -v
bash test-critical.sh homolog
```

Somente como verificação local limitada, sem PostgreSQL: `python manage.py test --settings=config.settings.test_sqlite --noinput`. Essa configuração usa banco de teste em memória e chave exclusiva de teste.

## Deploy e cutover somente em homologação

Usar o checkout/ambiente de homologação já existente; não executar em `/opt/vemdedelivery/app` de produção.

1. Incorporar o ZIP em uma cópia/branch de homolog, preservando as variáveis locais do ambiente.
2. Executar `bash scripts/test-react.sh` para instalar dependências, testar e gerar os assets no checkout.
3. Validar/buildar o Compose de homolog: `docker compose -f docker/dev/docker-compose.yml config --quiet` e `docker compose -f docker/dev/docker-compose.yml build`.
4. Subir somente homolog, conferir plano de migrations e aplicar as migrations já existentes conforme o procedimento da homologação. Este pacote não cria migrations.
5. Rodar collectstatic e checks no backend de homolog, depois `bash test-critical.sh homolog` e os testes frontend/backend completos.
6. Testar `/painel/` com duas lojas. Revisar toda a matriz manual do inventário, incluindo integrações de teste e pagamentos reais de sandbox.
7. Somente depois dos gates, definir `MERCHANT_REACT_ENABLED=true` **no env de homolog** e recriar o backend de homolog. Agora `/admin/` passa a redirecionar para React e POSTs antigos recebem 409. `/painel/` no domínio raiz é servido pelo React; `/superadmin-legacy/` existe somente para fallback técnico durante a homologação. Verificar login, senha inicial, todos os links antigos e a operação completa.
8. Registrar o aceite. Produção continua proibida até autorização explícita posterior.

Rollback técnico em homolog: restaurar `MERCHANT_REACT_ENABLED=false` e recriar backend. Como não há mudança de schema/model, as interfaces usam os mesmos dados; mudanças que o lojista fez são preservadas. Não excluir templates, ModelAdmins ou forms.

## Templates substituídos e legado preservado

Fluxo normal após cutover usa `templates/merchant/shell.html` e React no lugar de:

- `templates/admin/tenant/index.html` e `app_list_collapsible.html`;
- telas genéricas Django/Unfold de models, inlines, ações, exclusão, histórico, login e senha;
- `templates/admin/orders/order/change_list.html` e `confirm_cancel.html`;
- `templates/admin/tenant/whatsapp_agent.html`;
- `templates/billing/dashboard.html`, `setup_required.html`, `invoice.html`, `fiscal_list.html`, `online_fees.html`, `style.html`;
- `templates/dashboard/home.html`, `login.html` e `base.html` no dashboard antigo.

Nenhum template antigo foi apagado. `admin/base.html`, estilos/scripts do admin, ModelAdmins e formulários continuam existindo como dependências do adaptador e fallback de homologação. O painel do lojista e a administração global usam React como interface principal. Views/JWT antigos, emails, scripts, webhooks, Celery e páginas públicas permanecem.

## Pendências, diferenças e riscos

- Homologação real não acessível nesta sessão: sem Docker local e sem conexão autorizada/configurada à VPS. Gates PostgreSQL, Docker, CI externo, integrações reais e aceite manual permanecem abertos.
- Os campos relacionados atualmente usam opções enviadas no schema e selects nativos. Lojas com catálogos/clientes muito grandes precisam validar tamanho/latência; um endpoint de busca paginada de opções pode ser necessário, mantendo escopo e validações.
- O adaptador depende de APIs de ModelAdmin e `_create_formsets`. Upgrades de Django/Unfold precisam repetir testes. As dependências Python originais parcialmente abertas não foram alteradas.
- Popups “adicionar relacionado” do Unfold não são usados. Os recursos relacionados têm telas React próprias, acessíveis no menu; validar o fluxo com o lojista.
- Após erro de formulário, arquivos que o navegador não mantém precisam ser selecionados novamente. O backend continua validando o arquivo e os limites originais.
- A primeira versão não adiciona novos mecanismos de concorrência: mantém os hooks existentes. Não tratar testes SQLite como validação de estoque concorrente.
- Paridade de cada detalhe de UX e de todas as combinações de dados não é garantida apenas por renderização e testes locais; o inventário é a lista de aceite da homologação.

## Arquivos

Lista exata em `docs/package-12-files.json`. Criados: app `apps/merchant/`, `frontend/`, `static/merchant/`, shell, configuração exclusiva de teste SQLite, testes, documentação e workflow de validação. Modificados: Dockerfile, .dockerignore, config/urls.py, config/settings/base.py, apps/billing/views.py, apps/integrations/tenant_views.py e test-critical.sh. Arquivos originais não relacionados são mantidos byte a byte no ZIP.

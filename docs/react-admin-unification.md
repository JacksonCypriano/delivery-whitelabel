# Unificação do front administrativo em React

## Rotas oficiais

A rota é a mesma; o host define o escopo:

- `https://<slug>.<dominio>/painel/`: painel do lojista em React, API em `/api/merchant/`.
- `https://<dominio>/painel/`: administração global em React, API em `/api/superadmin/`.
- `/superadmin-legacy/`: fallback técnico temporário do Django Admin durante homologação.

A mesma aplicação React é reutilizada nos dois contextos. O shell injeta `kind`, `basePath`, `apiBase` e `title`; o cliente HTTP e o React Router usam essa configuração em runtime.

## Segurança e isolamento

O host é parte obrigatória do escopo de autorização, não apenas da navegação. O `TenantMiddleware` resolve tenant somente a partir de `slug.dominio`; a raiz `dominio` nunca é convertida em tenant.

- Credenciais de SuperAdmin são recusadas pelo login do lojista.
- Credenciais de lojista são recusadas pelo login global.
- Um lojista de uma loja é recusado em qualquer outro tenant.
- `/api/merchant/` não existe no domínio raiz sem tenant válido.
- `/api/superadmin/` não existe em subdomínio de tenant.
- Mesmo uma sessão Django já autenticada continua sujeita às mesmas verificações de host, papel e tenant em todas as APIs.

O painel do lojista exige usuário ativo, staff, `is_tenant_admin`, não-superusuário e `user.tenant_id == request.tenant.id`. O painel global exige host raiz configurado, usuário ativo e `is_superuser`. As allowlists de recursos são separadas.

## Vitrine demo

O `TenantMiddleware` aceita os aliases `demo` e `vitrine-demo` para preservar a compatibilidade entre o domínio antigo e o novo domínio da demonstração.

## Containers

O serviço Django passa a ser chamado somente de `backend`. Em produção blue/green os serviços são `backend-blue` e `backend-green`. Scripts de shell, logs, restart, operações, demo, backup/restore e upstream do Nginx foram alinhados com os novos nomes.

# Pacote — Acesso inicial automático do lojista

## O que muda

- O Superadmin não digita mais a senha ao criar uma conta vinculada a uma loja.
- O sistema gera uma senha temporária forte e aleatória.
- O usuário é configurado automaticamente como administrador da loja.
- O e-mail de boas-vindas informa login, senha temporária, link da loja e link do painel.
- No primeiro login, o lojista é redirecionado para a troca obrigatória de senha.
- A troca exige a senha temporária atual, a nova senha e a confirmação da nova senha.
- Enquanto a senha não for trocada, o restante do `/admin/` e o login/refresh JWT do dashboard ficam bloqueados.
- A senha temporária nunca é armazenada em texto puro no banco nem nos logs.
- O Superadmin recebe uma ação para regenerar e reenviar o acesso inicial, caso o primeiro e-mail falhe ou precise ser reemitido.

## Arquivos principais

- `apps/accounts/merchant_onboarding.py`: geração da senha, URLs e e-mail.
- `templates/accounts/merchant_welcome_email.html`: e-mail visual de boas-vindas.
- `templates/accounts/merchant_welcome_email.txt`: fallback texto.
- `apps/tenants/middleware.py`: bloqueio até a troca da senha.
- `apps/accounts/migrations/0007_user_initial_access.py`: campos de controle do primeiro acesso.
- `apps/core/tests_critical/test_merchant_initial_access.py`: testes críticos do fluxo.

## Aplicação

1. Extraia/copiei os arquivos do pacote na raiz do projeto, preservando as pastas.
2. Execute as migrações:

```bash
python manage.py migrate
```

3. Rode a suíte crítica em homologação:

```bash
./test-critical.sh homolog
```

4. Valide manualmente criando um novo usuário no Superadmin e vinculando-o a uma loja.
5. Depois do deploy em produção, rode:

```bash
./test-critical.sh prod
```

## Fluxo esperado

1. Superadmin > Usuários > Adicionar.
2. Informar login, nome, sobrenome, e-mail e loja.
3. Salvar.
4. O sistema gera a senha temporária e envia o e-mail de boas-vindas.
5. O lojista acessa `https://<slug>.vemdedelivery.com.br/admin/`.
6. Informa login e senha temporária.
7. É redirecionado automaticamente para a troca de senha.
8. Informa a senha temporária novamente, cria a nova senha e confirma.
9. Após a troca, o painel é liberado normalmente.

## Recuperação do primeiro acesso

Na lista de usuários do Superadmin existe a ação:

`Gerar novo acesso inicial e reenviar boas-vindas`

Ela invalida a senha anterior, gera outra senha temporária e envia um novo e-mail. Use apenas quando for realmente necessário reemitir o acesso.

# Pacote 8 — cadastro com OTP de e-mail e WhatsApp

## Comportamento entregue

1. `POST /conta/criar-conta/` valida os dados e cria somente um `PendingRegistration`, vinculado à sessão, com senha em hash. Envia o primeiro OTP de e-mail.
2. `GET /conta/criar-conta/validar/` mostra a etapa atual e o destino mascarado.
3. `POST` na mesma URL, com `action=verify`, `channel=email` e `code`, confirma o e-mail e envia o OTP de WhatsApp.
4. O mesmo POST com `channel=whatsapp` confirma a posse, cria `User` global e `Customer` numa transação e autentica o consumidor.
5. `action=send` reenvia somente para a etapa atual. Todos os POSTs exigem CSRF. O identificador da pendência vem da sessão, nunca do formulário.

Regras: códigos de 6 dígitos gerados com `secrets`, hash do Django, 10 minutos, 5 tentativas por código, 60 segundos entre envios, máximo 5 envios por janela móvel de 1 hora por canal e por cada IP/e-mail/telefone separadamente. Trocar sessão ou IP não reinicia o limite do destino. Falhas de envio também consomem limite. Novo envio invalida o código anterior. Pendência expira em 24 horas, sem renovação nos reenvios.

A conclusão e os envios usam bloqueio de linha PostgreSQL; duplicidade de telefone na conclusão desfaz também a criação do usuário. Falhas dos provedores não aprovam a verificação. O redirecionamento final é validado.

## Configuração e implantação

Preencher o `.env` do ambiente, usando os parâmetros de SMTP já existentes:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=seu-servidor-smtp
EMAIL_PORT=587
EMAIL_HOST_USER=seu-usuario
EMAIL_HOST_PASSWORD=sua-senha
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
DEFAULT_FROM_EMAIL=VemDeDelivery <seu-remetente-autorizado>
EVOLUTION_API_URL=https://sua-evolution
EVOLUTION_API_KEY=sua-chave
EVOLUTION_INSTANCE=sua-instancia-conectada
EVOLUTION_API_TIMEOUT=4
```

O envio usa a [Evolution API v2](https://github.com/evolution-foundation/evolution-go/issues/27): `POST /message/sendText/{instance}`, header `apikey`, campos `number` e `text`. A configuração versionada deste projeto usa v2.3.7. A resposta precisa conter `key.id`; isto confirma a aceitação pelo provedor, não a entrega ao aparelho. A confirmação por OTP comprova a posse.

`EVOLUTION_WHATSAPP_VALIDATION_ENABLED` continua controlando apenas a consulta de existência do número. Desativá-la NÃO dispensa OTP. Sem SMTP/Evolution funcionais, o cadastro não conclui.

Em produção atrás do Nginx versionado, que sobrescreve `X-Real-IP`, defina `OTP_TRUST_PROXY_HEADERS=true` somente se o acesso ao Django estiver restrito ao proxy confiável. Sem isso, o limite considera o IP da conexão; atrás de proxy, os clientes compartilharão esse limite. Em acesso direto/dev, deixe `false`.

Na raiz do projeto, para homologação:

```bash
bash dc-homolog.sh deploy
docker compose -f docker/dev/docker-compose.yml exec web python manage.py test apps.accounts apps.core.tests_critical --settings=config.settings.test
```

O script executa build e migrations. Para um ambiente já atualizado, as migrações são:

```bash
python manage.py migrate --noinput
python manage.py check
```

As migrações adicionam as tabelas de pendências/limites, os campos de verificação de e-mail e limpam os antigos indicadores de telefone verificado. Antes do pacote, esses indicadores comprovavam apenas existência no WhatsApp. Nenhuma conta existente é excluída ou bloqueada. O rollback da migração não restaura essas marcações sem prova de posse.

Execute diariamente, via cron/agendador do servidor:

```bash
python manage.py cleanup_registrations
```

Este comando remove pendências expiradas/concluídas e registros antigos de limites. A expiração é aplicada nas requisições mesmo sem executar a limpeza. O comando não foi agendado automaticamente.

## Validação e limites de escopo

- 61 testes passaram localmente: 15 novos testes de OTP e 46 testes existentes, incluindo as expectativas atualizadas de verificação por posse.
- Dois testes adicionais de concorrência ficam no código e exigem PostgreSQL. O ambiente de execução local disponibilizou SQLite; esses dois testes são ignorados nesse banco. Execute o comando acima em homologação para validar os bloqueios reais do PostgreSQL.
- `makemigrations --check --dry-run` não identificou alterações pendentes; verificação do Django sem problemas.
- SMTP e Evolution foram simulados nos testes; não foram enviados códigos reais. Validar recebimento em ambos os canais, reenvio e conclusão em homologação antes de produção.
- A versão recebida não contém `apps.notifications`. O envio é síncrono, com os timeouts já configurados, dentro da operação serializada. Isso simplifica a confirmação de falha e não coloca OTP em texto no broker. A requisição pode aguardar o timeout do provedor. Avaliar fila própria se o volume crescer.
- O fluxo de OTP deste pacote é o cadastro. Alterar e-mail/telefone no perfil limpa a respectiva verificação; este pacote não implementa uma tela de reverificação para contas existentes.

## Arquivos principais

`apps/accounts/otp.py`, modelos/migrations de accounts e customers, formulário de cadastro/perfil, views/URLs, tela de confirmação, comando de limpeza e testes. Os demais arquivos originais são preservados no ZIP.

# VemDeDelivery — atendimento comercial público de entrada

## Escopo

O modo público é **opt-in e desativado por padrão**. Ele permite responder automaticamente a novas mensagens **diretas recebidas** de telefones brasileiros que não estejam no cadastro do piloto. Nunca faz disparos espontâneos. O bloqueio por OTP compartilhado continua prioritário: contatos que recebem código pela instância comercial são excluídos e não podem ser reativados por essa flag. Também são respeitados os limites de mensagens, opt-out, pedido de humano, mensagens de mídia, pausa manual, controle global e verificação do catálogo publicado. Mensagens antigas retidas **não** são reenfileiradas.

Nova variável de ambiente:

```dotenv
COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=false
```

`false` = piloto atual (allowlist), `true` = atendimento receptivo de novos contatos. Nenhum banco, token, credencial, instância ou migração foi alterado. **Mantenha** `COMMERCIAL_OTP_SHARED_ENABLED=true`, `COMMERCIAL_AGENT_MODE=rules`, `WHATSAPP_AGENT_ENABLED=false` conforme a instalação validada.

## Aplicação local / revisão

1. Verifique `git status --short` na raiz do repositório e se está na branch `homolog` (ou sua branch de trabalho). Não aplique sobre alterações conflitantes.
2. Extraia o ZIP **fora** da árvore do projeto, sem sobrescrever código diretamente:

```bash
cd /home/jacksoncypriano/projects/delivery-whitelabel || exit 1
python3 /CAMINHO/EXTRAIDO/aplicar.py "$PWD"
python3 /CAMINHO/EXTRAIDO/aplicar.py "$PWD" --apply

git status --short
git diff --check
git diff -- config/settings/base.py apps/prospecting/commercial_pilot.py \
  apps/prospecting/commercial.py apps/prospecting/commercial_api.py \
  apps/prospecting/management/commands/check_commercial_readiness.py \
  frontend/src/features/superadmin/Commercial.tsx
```

O instalador recusa trechos divergentes e cria backup **fora do projeto**, antes de alterar arquivos.

3. Valide o backend em ambiente **local/de testes**, com a integração Evolution simulada pelos testes. Execute o teste direcionado no serviço `backend` do Compose local (se já estiver ativo):

```bash
docker compose -f docker/dev/docker-compose.yml exec -T backend \
  python manage.py test \
  apps.prospecting.test_commercial_public_inbound \
  apps.prospecting.test_commercial_pilot_otp \
  apps.prospecting.test_commercial_handoff_notifications_p15
./test-critical-front.sh
(cd frontend && npm run build)
```

4. Faça commit e push para `homolog`. Deixe a nova flag **false** em HML e PROD durante a revisão, assim o comportamento pré-existente permanece idêntico. Faça o smoke test em HML e o merge `homolog -> main` seguindo a pipeline atual. Verifique conclusão do deploy e saúde dos workers.

## Liberação controlada em PROD

**Antes de alterar o `.env`:** no painel `/painel/comercial`, clique em **Pausar respostas**. Isso mantém novas mensagens sem resposta automática durante a transição e evita uma abertura inesperada da lista.

Na VPS:

```bash
cd /opt/vemdedelivery/app || exit 1
DC=(docker compose -f docker/prod/docker-compose.bluegreen.yml)
ACTIVE="$(sed -nE 's/.*server (backend-(blue|green)):8000.*/\1/p' docker/prod/nginx/conf.d/active-upstream.conf | head -1)"
case "$ACTIVE" in backend-blue|backend-green) ;; *) echo 'Backend ativo inválido'; exit 1 ;; esac
```

Faça backup do arquivo `docker/prod/.env` em local protegido na VPS. Edite esse `.env` (não o da raiz) e deixe **uma única linha**:

```dotenv
COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=true
```

**Não compartilhe o `.env` nem credenciais.** Confirme que a versão nova já está implantada. Como as variáveis são carregadas na criação dos containers, **`docker restart` não aplica a alteração do `.env`**. Atualize os contêineres vinculados ao Compose atual (curta indisponibilidade do backend ativo ao recriar):

```bash
"${DC[@]}" up -d --no-deps --force-recreate \
  "$ACTIVE" celery celery-prospecting celery-beat
"${DC[@]}" ps "$ACTIVE" celery celery-prospecting celery-beat
for SERVICE in "$ACTIVE" celery celery-beat; do
  echo "--- $SERVICE ---"
  "${DC[@]}" exec -T "$SERVICE" python manage.py shell -c '
from django.conf import settings
print("Public inbound:", settings.COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED)
print("Shared OTP:", settings.COMMERCIAL_OTP_SHARED_ENABLED)
print("Rules:", settings.COMMERCIAL_AGENT_MODE)
'
done
"${DC[@]}" exec -T "$ACTIVE" python manage.py check_commercial_readiness
```

Confirme que os serviços estão saudáveis, a prontidão não reporta bloqueios críticos, o modo público consta como `True` nos serviços e que a instância comercial permanece `open`. Só então, no Superadmin, clique em **Ativar respostas**. Faça uma conversa de teste por **um telefone novo, não cadastrado na allowlist nem utilizado para OTP**, verificando resposta e registro na Inbox. Teste pedido de humano e opt-out por contatos de teste. Monitore pendentes e entregas `submitted` (não significa entrega final).

## Reversão imediata

No painel clique em **Pausar respostas**. Para retornar ao comportamento anterior, mude `COMMERCIAL_AGENT_PUBLIC_INBOUND_ENABLED=false` em `docker/prod/.env` e recrie os mesmos serviços, confirme `False`, e reative o piloto se desejar. Não apague `CommercialOtpExclusion`, não reenvie `sending`/`uncertain` e não refile mensagens `held`.

## Limitações importantes

- O modo público **não** atende números que receberam OTP na instância compartilhada, mensagens de grupos, mensagens enviadas pela própria conta ou contatos que fizeram opt-out; mídia ou pedidos de atendimento humano são encaminhados para a Inbox.
- Não há revisão automática de spam/abuso para além das barreiras existentes. A implantação deve ser monitorada; o limite de saída atualmente é 500 mensagens com resposta em 24h, e há limite por conversa.
- A funcionalidade de **envio humano pelo painel** é independente (`COMMERCIAL_HUMAN_PANEL_SEND_ENABLED=false` atualmente); alertas WhatsApp operacionais também exigem autorização específica. Ao transferir para humano, precisa haver acompanhamento na Inbox.
- A ativação não equivale a campanha de prospecção e não deve ser usada para mensagens não solicitadas.

#!/usr/bin/env bash
# Uso: bash scripts/prod/blue_green_deploy.sh
# Alterna backend-blue/backend-green apenas depois de testes e health checks.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker/prod/docker-compose.bluegreen.yml)
ACTIVE_FILE="docker/prod/nginx/conf.d/active-upstream.conf"
# Este arquivo é estado operacional gerado pelo deploy, não código versionado.
# Mantemos o conteúdo local para a alternância, sem bloquear o próximo pull.
git update-index --assume-unchanged "$ACTIVE_FILE" 2>/dev/null || true
PREVIOUS_UPSTREAM="$(cat "$ACTIVE_FILE")"
SWITCHED=0
# No primeiro deploy migratorio, upstream pode ser web-blue/web-green.
ACTIVE="$(grep -oE '(backend|web)-(blue|green)' "$ACTIVE_FILE" | head -1 || true)"
[[ "$ACTIVE" == *-blue ]] && NEXT=green || NEXT=blue

rollback() {
  local restored=0
  trap - ERR
  if [[ "$SWITCHED" == 1 ]]; then
    printf '%s\n' "$PREVIOUS_UPSTREAM" > "$ACTIVE_FILE"
    if "${COMPOSE[@]}" exec -T nginx nginx -t >/dev/null 2>&1 && \
       "${COMPOSE[@]}" exec -T nginx nginx -s reload >/dev/null 2>&1; then
      restored=1
      echo "Upstream anterior restaurado e recarregado."
    else
      echo "ERRO CRITICO: nao foi possivel confirmar o rollback do Nginx." >&2
      echo "Mantendo backend-$NEXT ligado para evitar corte de trafego." >&2
      return 0
    fi
  else
    restored=1
  fi
  if [[ "$restored" == 1 ]]; then
    # Em falhas posteriores as migracoes, o backend anterior pode nao ser
    # compativel com o banco novo. Preservar o novo backend tambem como fallback.
    echo "Falha de deploy; upstream mantido/restaurado para ${ACTIVE:-anterior}."
    if [[ "$SWITCHED" == 0 ]]; then
      "${COMPOSE[@]}" stop "backend-$NEXT" 2>/dev/null || true
    fi
  fi
}
trap rollback ERR

[[ "$(git branch --show-current)" == "main" ]] || { echo "Produção exige a branch main."; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Há alterações locais; deploy cancelado."; exit 1; }
# Nenhum pull aqui: a action já fez fetch/pull e verificou o SHA do push.
# Exigir o SHA encaminhado pelo workflow evita avançar para outro commit
# entre a validação do checkout e o corte do tráfego.
if [[ -z "${VDD_DEPLOY_SHA:-}" || "$(git rev-parse HEAD)" != "$VDD_DEPLOY_SHA" ]]; then
  echo 'Deploy bloqueado: SHA local não coincide com o push da action.' >&2
  exit 1
fi

# No primeiro corte React, nao executar migrations automaticamente sem
# aprovacao explicita para o SHA revisado. A action pode atualizar arquivos,
# mas nao iniciara containers novos antes desta aprovacao.
if [[ "$ACTIVE" == web-blue || "$ACTIVE" == web-green ]]; then
  APPROVAL="/opt/vemdedelivery/operations/first-react-cutover-approved"
  if [[ ! -f "$APPROVAL" || "$(cat "$APPROVAL")" != "$VDD_DEPLOY_SHA" ]]; then
    echo "Primeiro corte bloqueado: revisar migracoes e aprovar SHA em $APPROVAL" >&2
    exit 1
  fi
fi

# Usar apenas os containers preexistentes: sem recriar PostgreSQL/Redis/Nginx.
for service in db redis nginx; do
  container="$("${COMPOSE[@]}" ps -q "$service")"
  [[ -n "$container" && "$(docker inspect --format='{{.State.Running}}' "$container")" == true ]] || {
    echo "Servico existente indisponivel: $service" >&2
    exit 1
  }
done

echo "▶ Criando e verificando backup antes da publicação..."
# O Nginx tem acesso somente leitura ao mesmo volume de media usado pelos
# backends, inclusive antes de existir a primeira imagem React/Django.
COMPOSE_FILE=docker/prod/docker-compose.bluegreen.yml VDD_MEDIA_BACKUP_SERVICE=nginx bash backup-prod.sh
COMPOSE_FILE=docker/prod/docker-compose.bluegreen.yml bash test-restore-prod.sh

# Suítes críticas executadas em CI/homolog; build compila o TypeScript.
"${COMPOSE[@]}" up -d --no-deps --build --wait public-ssr
"${COMPOSE[@]}" up -d --no-deps --build "backend-$NEXT"

for _ in $(seq 1 30); do
  container="$(${COMPOSE[@]} ps -q "backend-$NEXT" || true)"
  status="$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || true)"
  [[ "$status" == healthy ]] && break
  sleep 2
done
[[ "$status" == healthy ]] || { echo "Nova versão não ficou saudável."; exit 1; }

printf 'upstream vemdedelivery_upstream { server backend-%s:8000; }\n' "$NEXT" > "$ACTIVE_FILE"
# Ativar o rollback antes de validar/recarregar o Nginx.
SWITCHED=1
"${COMPOSE[@]}" exec -T nginx nginx -t
"${COMPOSE[@]}" exec -T nginx nginx -s reload
curl --fail --silent --show-error --resolve vemdedelivery.com.br:443:127.0.0.1 https://vemdedelivery.com.br/health/ready/ >/dev/null
"${COMPOSE[@]}" build celery celery-prospecting celery-beat
"${COMPOSE[@]}" up -d --no-deps celery celery-prospecting celery-beat

prospecting_status=""
for _ in $(seq 1 20); do
  prospecting_container="$(${COMPOSE[@]} ps -q celery-prospecting || true)"
  prospecting_status="$(docker inspect --format='{{.State.Health.Status}}' "$prospecting_container" 2>/dev/null || true)"
  [[ "$prospecting_status" == healthy ]] && break
  sleep 2
done
if [[ "$prospecting_status" != healthy ]]; then
  "${COMPOSE[@]}" logs --tail=100 celery-prospecting || true
  echo "Worker dedicado de prospecção não ficou saudável."
  exit 1
fi

# Os containers web-* antigos nao pertencem ao Compose novo. Preserva-os
# como fallback na primeira migracao; nao tenta parar um servico inexistente.
if [[ "$ACTIVE" == backend-blue || "$ACTIVE" == backend-green ]]; then
  "${COMPOSE[@]}" stop "$ACTIVE" 2>/dev/null || true
fi
legacy="$(docker ps -q --filter name='^prod-backend-1$' || true)"
[[ -z "$legacy" ]] || docker stop "$legacy" >/dev/null
echo "Deploy concluído: tráfego em backend-$NEXT."

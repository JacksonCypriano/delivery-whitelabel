#!/usr/bin/env bash
# Uso: bash scripts/prod/blue_green_deploy.sh
# Alterna web-blue/web-green apenas depois de testes e health checks.
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
ACTIVE="$(grep -oE 'web-(blue|green)' "$ACTIVE_FILE" | head -1 || true)"
[[ "$ACTIVE" == "web-blue" ]] && NEXT=green || NEXT=blue

rollback() {
  if [[ "$SWITCHED" == 1 ]]; then
    printf '%s\n' "$PREVIOUS_UPSTREAM" > "$ACTIVE_FILE"
    "${COMPOSE[@]}" exec -T nginx nginx -t >/dev/null 2>&1 && "${COMPOSE[@]}" exec -T nginx nginx -s reload >/dev/null 2>&1 || true
  fi
  echo "Falha: o tráfego permanece no ambiente ${ACTIVE:-atual}."
  "${COMPOSE[@]}" stop "web-$NEXT" 2>/dev/null || true
}
trap rollback ERR

[[ "$(git branch --show-current)" == "main" ]] || { echo "Produção exige a branch main."; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Há alterações locais; deploy cancelado."; exit 1; }
git pull --ff-only origin main

echo "▶ Criando e verificando backup antes da publicação..."
bash backup-prod.sh
bash test-restore-prod.sh

# Testa o código que será publicado antes de subir a nova cor.
"${COMPOSE[@]}" build "web-$NEXT"
# Use the same isolated critical suite used by homolog/prod deployments,
# against the image that was just built.
"${COMPOSE[@]}" run --rm --no-deps \
  -e DJANGO_SETTINGS_MODULE=config.settings.test \
  -e EVOLUTION_WHATSAPP_VALIDATION_ENABLED=false \
  --entrypoint python "web-$NEXT" manage.py test \
  apps.accounts apps.billing.tests apps.integrations.tests apps.core.tests_critical \
  --settings=config.settings.test --verbosity=2 --noinput
"${COMPOSE[@]}" up -d "web-$NEXT"

for _ in $(seq 1 30); do
  container="$(${COMPOSE[@]} ps -q "web-$NEXT" || true)"
  status="$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || true)"
  [[ "$status" == healthy ]] && break
  sleep 2
done
[[ "$status" == healthy ]] || { echo "Nova versão não ficou saudável."; exit 1; }

printf 'upstream vemdedelivery_upstream { server web-%s:8000; }\n' "$NEXT" > "$ACTIVE_FILE"
"${COMPOSE[@]}" exec -T nginx nginx -t
"${COMPOSE[@]}" exec -T nginx nginx -s reload
SWITCHED=1
curl --fail --silent --show-error --resolve vemdedelivery.com.br:443:127.0.0.1 https://vemdedelivery.com.br/health/ready/ >/dev/null
"${COMPOSE[@]}" build celery celery-beat
"${COMPOSE[@]}" up -d celery celery-beat
"${COMPOSE[@]}" stop "web-$ACTIVE" 2>/dev/null || true
# Remove somente o container legado do compose anterior, sem tocar em volumes.
legacy="$(docker ps -q --filter name='^prod-web-1$' || true)"
[[ -z "$legacy" ]] || docker stop "$legacy" >/dev/null
echo "Deploy concluído: tráfego em web-$NEXT."

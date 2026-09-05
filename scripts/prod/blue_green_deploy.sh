#!/usr/bin/env bash
# Uso: bash scripts/prod/blue_green_deploy.sh
# Alterna web-blue/web-green apenas depois de testes e health checks.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker/prod/docker-compose.bluegreen.yml)
ACTIVE_FILE="docker/prod/nginx/conf.d/active-upstream.conf"
ACTIVE="$(grep -oE 'web-(blue|green)' "$ACTIVE_FILE" | head -1 || true)"
[[ "$ACTIVE" == "web-blue" ]] && NEXT=green || NEXT=blue

rollback() {
  echo "Falha: o tráfego permanece no ambiente ${ACTIVE:-atual}."
  "${COMPOSE[@]}" stop "web-$NEXT" 2>/dev/null || true
}
trap rollback ERR

[[ "$(git branch --show-current)" == "main" ]] || { echo "Produção exige a branch main."; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Há alterações locais; deploy cancelado."; exit 1; }
git pull --ff-only origin main

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
  status="$(${COMPOSE[@]} ps --format json "web-$NEXT" | grep -o 'healthy' || true)"
  [[ "$status" == healthy ]] && break
  sleep 2
done
[[ "$status" == healthy ]] || { echo "Nova versão não ficou saudável."; exit 1; }

printf 'upstream vemdedelivery_upstream { server web-%s:8000; }\n' "$NEXT" > "$ACTIVE_FILE"
"${COMPOSE[@]}" exec -T nginx nginx -t
"${COMPOSE[@]}" exec -T nginx nginx -s reload
curl --fail --silent --show-error --resolve vemdedelivery.com.br:443:127.0.0.1 https://vemdedelivery.com.br/health/ready/ >/dev/null
"${COMPOSE[@]}" stop "web-$ACTIVE" 2>/dev/null || true
echo "Deploy concluído: tráfego em web-$NEXT."

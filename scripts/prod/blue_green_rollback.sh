#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$ROOT"
COMPOSE=(docker compose -f docker/prod/docker-compose.bluegreen.yml)
ACTIVE_FILE="docker/prod/nginx/conf.d/active-upstream.conf"
ACTIVE="$(grep -oE 'backend-(blue|green)' "$ACTIVE_FILE" | head -1)"
[[ "$ACTIVE" == backend-blue ]] && TARGET=green || TARGET=blue
"${COMPOSE[@]}" up -d "backend-$TARGET"
printf 'upstream vemdedelivery_upstream { server backend-%s:8000; }\n' "$TARGET" > "$ACTIVE_FILE"
"${COMPOSE[@]}" exec -T nginx nginx -t && "${COMPOSE[@]}" exec -T nginx nginx -s reload
echo "Rollback concluído: tráfego em backend-$TARGET."

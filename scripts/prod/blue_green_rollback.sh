#!/usr/bin/env bash
# Rollback manual conservador: somente alterna para backend ja existente,
# sem executar migrations nem recriar containers de banco ou Nginx.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker/prod/docker-compose.bluegreen.yml)
ACTIVE_FILE="docker/prod/nginx/conf.d/active-upstream.conf"
CURRENT="$(cat "$ACTIVE_FILE")"
ACTIVE="$(grep -oE 'backend-(blue|green)' "$ACTIVE_FILE" | head -1 || true)"
if [[ "$ACTIVE" != backend-blue && "$ACTIVE" != backend-green ]]; then
  echo "Rollback automatico indisponivel para upstream legado; sem alteracoes." >&2
  exit 1
fi
[[ "$ACTIVE" == backend-blue ]] && TARGET=backend-green || TARGET=backend-blue
container="$("${COMPOSE[@]}" ps -q "$TARGET" || true)"
if [[ -z "$container" || "$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || true)" != healthy ]]; then
  echo "Destino $TARGET nao esta saudavel; rollback cancelado sem iniciar containers." >&2
  exit 1
fi
printf 'upstream vemdedelivery_upstream { server %s:8000; }\n' "$TARGET" > "$ACTIVE_FILE"
if ! "${COMPOSE[@]}" exec -T nginx nginx -t || ! "${COMPOSE[@]}" exec -T nginx nginx -s reload; then
  printf '%s\n' "$CURRENT" > "$ACTIVE_FILE"
  "${COMPOSE[@]}" exec -T nginx nginx -t && "${COMPOSE[@]}" exec -T nginx nginx -s reload || true
  echo "Rollback nao confirmado; conferir o roteamento antes de mexer nos backends." >&2
  exit 1
fi
echo "Rollback de trafego concluido: $TARGET (sem alterar banco ou migracoes)."

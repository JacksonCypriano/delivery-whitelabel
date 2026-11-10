#!/usr/bin/env bash
# Read-only discovery of live production backend (no deployment or configuration).
set -Eeuo pipefail
active=()
for color in blue green; do
    name="prod-backend-${color}-1"
    status="$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || true)"
    if [[ "$status" == running && "$health" == healthy ]]; then
        active+=("$name")
    fi
done
if (( ${#active[@]} != 1 )); then
    printf 'ERRO: esperado exatamente um backend saudável; encontrados: %s\n' "${active[*]:-nenhum}" >&2
    exit 1
fi
printf '%s\n' "${active[0]}"

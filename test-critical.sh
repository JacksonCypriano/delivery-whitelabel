#!/usr/bin/env bash

set -Eeuo pipefail

ENVIRONMENT="${1:-}"

case "$ENVIRONMENT" in
    homolog)
        DEFAULT_COMPOSE_FILE="docker/dev/docker-compose.yml"
        ;;
    prod)
        DEFAULT_COMPOSE_FILE="docker/prod/docker-compose.yml"
        ;;
    "")
        DEFAULT_COMPOSE_FILE="docker/prod/docker-compose.yml"
        ;;
    *)
        echo "❌ Ambiente inválido: $ENVIRONMENT" >&2
        echo "Uso: $0 [homolog|prod]" >&2
        exit 1
        ;;
esac

COMPOSE_FILE="${COMPOSE_FILE:-$DEFAULT_COMPOSE_FILE}"
DC=(docker compose -f "$COMPOSE_FILE")

echo "============================================================"
echo "▶ VemDeDelivery — testes críticos"
echo "▶ Ambiente: ${ENVIRONMENT:-prod}"
echo "▶ Compose: $COMPOSE_FILE"
echo "============================================================"

"${DC[@]}" config --quiet

DB_CONTAINER=$("${DC[@]}" ps -q db)

[[ -n "$DB_CONTAINER" ]] || {
    echo "❌ PostgreSQL não está em execução." >&2
    exit 1
}

DB_HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$DB_CONTAINER")

[[ "$DB_HEALTH" == "healthy" || "$DB_HEALTH" == "running" ]] || {
    echo "❌ PostgreSQL não está saudável: $DB_HEALTH" >&2
    exit 1
}

echo "▶ Executando suíte em banco de teste isolado..."

"${DC[@]}" run --rm --no-deps --entrypoint python web manage.py test apps.core.tests_critical --settings=config.settings.test --verbosity=2 --noinput

echo ""
echo "✅ Suíte crítica concluída sem falhas."

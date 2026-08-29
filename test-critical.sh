#!/usr/bin/env bash
set -Eeuo pipefail

DC=(docker compose -f "${COMPOSE_FILE:-docker/prod/docker-compose.yml}")

echo "============================================================"
echo "▶ VemDeDelivery — testes críticos"
echo "============================================================"

"${DC[@]}" config --quiet

DB_CONTAINER=$("${DC[@]}" ps -q db)
[[ -n "$DB_CONTAINER" ]] || { echo "❌ PostgreSQL não está em execução." >&2; exit 1; }

DB_HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$DB_CONTAINER")
[[ "$DB_HEALTH" == "healthy" || "$DB_HEALTH" == "running" ]] || { echo "❌ PostgreSQL não está saudável: $DB_HEALTH" >&2; exit 1; }

echo "▶ Executando suíte em banco de teste isolado..."
"${DC[@]}" run --rm --no-deps --entrypoint python web manage.py test apps.core.tests_critical --settings=config.settings.test --verbosity=2 --noinput

echo ""
echo "✅ Suíte crítica concluída sem falhas."

#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker/prod/docker-compose.yml}"

echo "== Docker Compose config =="
docker compose -f "$COMPOSE_FILE" config --quiet

echo "== Containers =="
docker compose -f "$COMPOSE_FILE" ps

echo "== Django deployment checks =="
docker compose -f "$COMPOSE_FILE" exec web python manage.py check --deploy

echo "== Django migrations =="
docker compose -f "$COMPOSE_FILE" exec web python manage.py showmigrations --plan | tail -20

echo "== HTTPS principal =="
curl -fsSI https://vemdedelivery.com.br/ | head

echo "✅ Production checks finished."

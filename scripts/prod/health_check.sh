#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vemdedelivery/app}"
COMPOSE_FILE="${COMPOSE_FILE:-docker/prod/docker-compose.yml}"
BASE_URL="${BASE_URL:-https://vemdedelivery.com.br}"

cd "$APP_DIR"

echo "============================================================"
echo "▶ VemDeDelivery — health check"
echo "============================================================"

echo "▶ Containers..."
docker compose -f "$COMPOSE_FILE" ps

echo
echo "▶ Liveness..."
curl --fail --silent --show-error --max-time 10 "$BASE_URL/health/live/"
echo

echo
echo "▶ Readiness (PostgreSQL + Redis)..."
curl --fail --silent --show-error --max-time 10 "$BASE_URL/health/ready/"
echo

echo
echo "✅ Aplicação, PostgreSQL e Redis responderam corretamente."

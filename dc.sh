#!/usr/bin/env bash
set -euo pipefail

COMMAND=${1:-}
ENV=${2:-dev}
SERVICE=${3:-web}

# =========================
# Validações
# =========================
if [[ -z "$COMMAND" ]]; then
  echo "Usage: $0 <command> [dev|prod] [service]"
  exit 1
fi

if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "Environment must be 'dev' or 'prod'"
  exit 1
fi

DC="docker compose -f docker/$ENV/docker-compose.yml"

# =========================
# Commands
# =========================
case "$COMMAND" in

  up)
    echo "Starting containers in $ENV..."
    $DC up -d
    ;;

  down)
    echo "Stopping containers in $ENV..."
    $DC down
    ;;

  rebuild)
    echo "Rebuilding containers in $ENV..."
    $DC up -d --build
    ;;

  logs)
    echo "Showing logs ($SERVICE) in $ENV..."
    $DC logs -f "$SERVICE"
    ;;

  shell)
    echo "Opening shell in $SERVICE ($ENV)..."
    $DC exec "$SERVICE" sh
    ;;

  makemigrations)
    ./scripts/makemigrations.sh "$ENV"
    ;;

  migrate)
    ./scripts/migrate.sh "$ENV"
    ;;

  restart)
    ./scripts/restart.sh "$ENV"
    ;;

  *)
    echo "Unknown command: $COMMAND"
    echo ""
    echo "Available commands:"
    echo "  up            Start containers"
    echo "  down          Stop containers"
    echo "  rebuild       Rebuild and start"
    echo "  logs          Follow logs (default: web)"
    echo "  shell         Open shell in container"
    echo "  makemigrations"
    echo "  migrate"
    echo "  restart"
    exit 1
    ;;

esac
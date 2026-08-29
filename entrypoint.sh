#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-web}"
DB_HOST="${DATABASE_HOST:-db}"
DB_PORT="${DATABASE_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}"

echo "⚙️ DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}"
echo "⚙️ ROLE=${ROLE}"

wait_for_port() {
  local host="$1"
  local port="$2"
  local name="$3"

  echo "⏳ Waiting for ${name} at ${host}:${port}..."

  until python - <<PY
import socket
import sys

host = "${host}"
port = int("${port}")

try:
    with socket.create_connection((host, port), timeout=2):
        pass
except OSError:
    sys.exit(1)
PY
  do
    sleep 1
  done

  echo "✅ ${name} is up!"
}

wait_for_port "$DB_HOST" "$DB_PORT" "database"
wait_for_port "$REDIS_HOST" "$REDIS_PORT" "redis"

case "$ROLE" in
  web)
    echo "📁 Preparing static/media directories..."
    mkdir -p /app/staticfiles /app/media

    if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
      echo "📦 Running migrations..."
      python manage.py migrate --noinput
    fi

    if [ "${COLLECTSTATIC:-true}" = "true" ]; then
      echo "🎯 Collecting static files..."
      python manage.py collectstatic --noinput
    fi

    echo "🔎 Running Django deployment checks..."
    python manage.py check --deploy --fail-level ERROR

    echo "🌐 Starting Gunicorn..."
    exec gunicorn config.asgi:application \
      -k uvicorn.workers.UvicornWorker \
      --bind "0.0.0.0:${PORT:-8000}" \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-120}" \
      --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
      --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-100}" \
      --access-logfile - \
      --error-logfile - \
      --capture-output \
      --log-level info
    ;;

  celery)
    echo "🚀 Starting Celery worker..."
    exec celery -A config worker --loglevel=info
    ;;

  beat)
    echo "⏰ Starting Celery beat..."
    exec celery -A config beat --loglevel=info
    ;;

  *)
    echo "❌ Unknown role: ${ROLE}" >&2
    exit 1
    ;;
esac

#!/usr/bin/env bash
set -e
echo "⚙️ DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
echo "⚙️ DEBUG=$DJANGO_DEBUG"

ROLE="${1:-web}"

DB_HOST="${DATABASE_HOST:-db}"
DB_PORT="${DATABASE_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

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

s = socket.socket()
s.settimeout(2)

try:
    s.connect((host, port))
    s.close()
except Exception:
    sys.exit(1)
PY
  do
    sleep 1
  done

  echo "✅ ${name} is up!"
}

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"

wait_for_port "$DB_HOST" "$DB_PORT" "database"

if [ "$ROLE" = "celery" ] || [ "$ROLE" = "beat" ]; then
  wait_for_port "$REDIS_HOST" "$REDIS_PORT" "redis"
fi

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

    echo "🌐 Starting Gunicorn..."
    exec gunicorn config.asgi:application \
      -k uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:${PORT:-8000} \
      --workers ${GUNICORN_WORKERS:-3} \
      --log-level info \
      --timeout ${GUNICORN_TIMEOUT:-120}
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
    echo "❌ Unknown role: $ROLE"
    exit 1
    ;;
esac
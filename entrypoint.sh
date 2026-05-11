#!/usr/bin/env bash
set -e

host="${DATABASE_HOST:-db}"
port="${DATABASE_PORT:-5432}"

echo "⏳ Waiting for $host:$port..."

until python - << END
import socket
import sys
s = socket.socket()
try:
    s.connect(("$host", int($port)))
    s.close()
except Exception:
    sys.exit(1)
END
do
  sleep 0.5
done

echo "✅ Database is up!"

export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings}

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "📁 Preparing static/media directories..."
mkdir -p /app/staticfiles /app/media

# 🔥 IMPORTANTE: isso resolve problema de volume
chmod -R 775 /app/staticfiles /app/media || true

echo "🎯 Collecting static files..."
python manage.py collectstatic --noinput

# Celery opcional
if [ "${CELERY_WORKER:-false}" = "true" ]; then
  echo "🚀 Starting Celery worker..."
  exec celery -A config worker -l info
fi

if [ "${CELERY_BEAT:-false}" = "true" ]; then
  echo "⏰ Starting Celery beat..."
  exec celery -A config beat -l info
fi

echo "🌐 Starting Gunicorn..."
exec gunicorn config.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${GUNICORN_WORKERS:-3} \
  --log-level info
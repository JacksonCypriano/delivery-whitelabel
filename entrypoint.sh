#!/usr/bin/env bash
set -e

host="$DATABASE_HOST"
port="${DATABASE_PORT:-5432}"

echo "Waiting for $host:$port..."
until python -c "import socket; socket.create_connection(('$host', $port), timeout=1)"; do
  sleep 0.5
done

export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings}

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "${CELERY_WORKER:-false}" = "true" ]; then
  echo "Iniciando Celery worker..."
  exec celery -A config worker -l info
fi

if [ "${CELERY_BEAT:-false}" = "true" ]; then
  echo "Iniciando Celery beat..."
  exec celery -A config beat -l info
fi

exec gunicorn config.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${PORT} \
  --workers ${GUNICORN_WORKERS:-3} \
  --log-level info

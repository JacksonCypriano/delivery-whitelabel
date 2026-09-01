#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-dev}
DC="docker compose -f docker/$ENV/docker-compose.yml"

echo "Running makemigrations in $ENV..."
$DC exec web python manage.py makemigrations
echo "makemigrations finished."
#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-dev}
DC="docker compose -f docker/$ENV/docker-compose.yml"

echo "Running migrate in $ENV..."
$DC exec web python manage.py migrate
echo "migrate finished."
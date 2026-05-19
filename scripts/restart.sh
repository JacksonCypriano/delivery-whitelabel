#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-dev}
DC="docker compose -f docker/$ENV/docker-compose.yml"

echo "Restarting web in $ENV..."
$DC restart web
echo "Restart finished."
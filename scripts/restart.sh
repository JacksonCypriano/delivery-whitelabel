#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-dev}
DC="docker compose -f docker/$ENV/docker-compose.yml"

echo "Restarting backend in $ENV..."
$DC restart backend
echo "Restart finished."
#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-dev}
DC="docker compose -f docker/$ENV/docker-compose.yml"

echo "Rebuilding containers in $ENV..."
$DC up -d --build
echo "Rebuild finished."
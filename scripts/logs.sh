#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-dev}
SERVICE=${2:-web}

DC="docker compose -f docker/$ENV/docker-compose.yml"

echo "Showing logs ($SERVICE) in $ENV..."
$DC logs -f "$SERVICE"
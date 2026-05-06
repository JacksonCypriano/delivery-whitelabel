#!/usr/bin/env bash
set -euo pipefail

DC="docker compose"

echo "Restarting 'web' service with: $DC restart web"
$DC restart web
echo "Restart finished."

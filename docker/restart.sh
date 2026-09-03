#!/usr/bin/env bash
set -euo pipefail

echo "Restarting web..."
$DC restart web
echo "Restart finished."
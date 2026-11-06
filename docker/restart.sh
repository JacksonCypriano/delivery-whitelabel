#!/usr/bin/env bash
set -euo pipefail

echo "Restarting backend..."
$DC restart backend
echo "Restart finished."
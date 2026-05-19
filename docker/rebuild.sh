#!/usr/bin/env bash
set -euo pipefail

echo "Rebuilding and starting containers..."
$DC up -d --build
echo "Rebuild finished."
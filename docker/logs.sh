#!/usr/bin/env bash
set -euo pipefail

echo "Showing logs (backend)..."
$DC logs -f backend
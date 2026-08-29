#!/usr/bin/env bash
set -euo pipefail

echo "Showing logs (web)..."
$DC logs -f web
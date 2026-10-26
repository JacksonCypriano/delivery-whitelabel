#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
exec bash ./scripts/prod/test_restore.sh "$@"

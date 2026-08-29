#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
exec ./scripts/prod/test_restore.sh "$@"

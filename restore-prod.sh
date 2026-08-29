#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
exec ./scripts/prod/restore.sh "$@"

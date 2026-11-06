#!/usr/bin/env bash
set -Eeuo pipefail

# Compatibilidade com os comandos antigos: o novo runner é a fonte única.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/test-critical-front.sh" "$@"

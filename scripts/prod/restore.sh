#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ $# -ge 1 && $# -le 2 ]] || { echo "Uso: restore-prod.sh DIRETORIO [--force]" >&2; exit 1; }
ARGS=(restore "$1")
if [[ "${2:-}" == "--force" ]]; then
    ARGS+=(--confirm)
elif [[ -n "${2:-}" ]]; then
    echo "Opção inválida." >&2
    exit 1
fi
exec python3 "$SCRIPT_DIR/operations.py" "${ARGS[@]}"

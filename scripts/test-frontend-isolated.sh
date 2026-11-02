#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "❌ Node.js e npm precisam estar disponíveis no WSL para testar o frontend." >&2
  exit 1
fi

if [[ ! -x node_modules/.bin/vitest ]]; then
  echo "▶ Instalando dependências do frontend pelo lockfile..."
  npm ci --no-audit --no-fund
fi

# Um Vitest por arquivo: evita que uma suíte herde consumo de memória/estado de
# outro arquivo durante uma execução longa. Nunca ignora falha e nunca pula teste.
mapfile -d '' tests < <(find src -type f   \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \)   -print0 | sort -z)

if (( ${#tests[@]} == 0 )); then
  echo "❌ Nenhum teste Vitest encontrado em frontend/src." >&2
  exit 1
fi

printf '▶ Executando %d arquivos de testes, um processo por arquivo.\n' "${#tests[@]}"
index=0
for test_file in "${tests[@]}"; do
  index=$((index + 1))
  printf '\n▶ [%d/%d] %s\n' "$index" "${#tests[@]}" "$test_file"
  npm run test -- "$test_file" --reporter=dot
done

echo "✅ Todos os testes React passaram isoladamente."

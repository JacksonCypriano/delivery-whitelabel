#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  cat <<'HELP'
Uso: ./test-critical-front.sh [--list] [--filter TEXTO]

Sem argumentos: executa todos os arquivos *.test.ts(x) e *.spec.ts(x),
um por processo Vitest, com apenas um worker e sem repeticoes automaticas.
--list          Mostra os arquivos descobertos sem executar.
--filter TEXTO  Executa somente arquivos com TEXTO no caminho (diagnostico).
HELP
}

FILTER=""
LIST_ONLY=0
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --list) LIST_ONLY=1; shift ;;
    --filter)
      if (($# < 2)) || [[ -z "$2" ]]; then echo '❌ --filter requer texto.' >&2; exit 2; fi
      FILTER="$2"; shift 2 ;;
    *) echo "❌ Argumento desconhecido: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo '❌ Node.js e npm precisam estar disponíveis no WSL.' >&2
  exit 1
fi

cd "$ROOT/frontend"
if [[ ! -f package-lock.json ]]; then
  echo '❌ frontend/package-lock.json não encontrado.' >&2
  exit 1
fi

# Descobre os arquivos em ordem deterministica. Não exclui testes sem avisar.
mapfile -d '' ALL_TESTS < <(find src -type f \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \) -print0 | LC_ALL=C sort -z)
TESTS=()
for file in "${ALL_TESTS[@]}"; do
  if [[ -z "$FILTER" || "$file" == *"$FILTER"* ]]; then
    TESTS+=("$file")
  fi
done
if ((${#TESTS[@]} == 0)); then
  echo '❌ Nenhum teste encontrado para o filtro informado.' >&2
  exit 1
fi

if ((LIST_ONLY)); then
  printf '%s\n' "${TESTS[@]}"
  exit 0
fi

# npm ci apenas quando necessário; sempre respeita o lockfile.
if [[ ! -x node_modules/.bin/vitest ]]; then
  echo '▶ Instalando dependências via npm ci...'
  npm ci --no-audit --no-fund
fi

# Processos distintos impedem vazamento de mocks/timers e GC entre arquivos.
# Um worker reduz contenção de CPU/RAM no WSL. O timeout NÃO é ampliado e
# uma falha continua falhando: não há reruns automáticos ou || true.
export CI=1
export VITEST_MAX_THREADS=1
printf '▶ Frontend/Vitest: %d arquivo(s) isolado(s). Node %s; npm %s.\n' \
  "${#TESTS[@]}" "$(node --version)" "$(npm --version)"

failures=()
index=0
for test_file in "${TESTS[@]}"; do
  index=$((index + 1))
  printf '\n▶ [%d/%d] %s\n' "$index" "${#TESTS[@]}" "$test_file"
  # O script de testes original chama vitest run. Passar caminho como argumento
  # nao modifica configuração das suítes nem mascara erros.
  if npm run test -- "$test_file" --maxWorkers=1 --no-file-parallelism --reporter=dot; then
    printf '✅ %s\n' "$test_file"
  else
    failures+=("$test_file")
    printf '❌ Falha em %s (sem retry automático).\n' "$test_file" >&2
  fi
done

printf '\n============================================================\n'
if ((${#failures[@]})); then
  printf '❌ %d de %d arquivo(s) falharam:\n' "${#failures[@]}" "${#TESTS[@]}" >&2
  printf '  %s\n' "${failures[@]}" >&2
  printf '\nPara diagnosticar um único arquivo: ./test-critical-front.sh --filter PARTE_DO_NOME\n' >&2
  exit 1
fi
printf '✅ Vitest: %d arquivo(s) aprovados.\n' "${#TESTS[@]}"

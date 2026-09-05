#!/usr/bin/env bash

set -Eeuo pipefail

# Permite executar o script a partir de qualquer diretório.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
    echo "Uso: $0 [homolog|prod]"
    echo "Sem argumento: prod (mantém o comportamento anterior)."
}

if [[ $# -gt 1 ]]; then
    usage >&2
    exit 1
fi

ENVIRONMENT="${1:-prod}"

case "$ENVIRONMENT" in
    homolog)
        DEFAULT_COMPOSE_FILE="docker/dev/docker-compose.yml"
        ;;
    prod)
        DEFAULT_COMPOSE_FILE="docker/prod/docker-compose.yml"
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        echo "❌ Ambiente inválido: $ENVIRONMENT" >&2
        usage >&2
        exit 1
        ;;
esac

COMPOSE_FILE="${COMPOSE_FILE:-$DEFAULT_COMPOSE_FILE}"
DC=(docker compose -f "$COMPOSE_FILE")

# Novos testes dentro desses módulos são descobertos automaticamente.
# Ao adicionar testes críticos de outros apps, inclua o módulo nesta lista.
TEST_SUITES=(
    apps.accounts
    apps.billing.tests
    apps.tenants.tests
    apps.integrations.tests
    apps.core.tests_critical
)

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Docker não foi encontrado." >&2
    exit 1
fi

trap 'result=$?; echo "❌ Testes interrompidos ou reprovados (código $result). Confira a saída acima." >&2; exit "$result"' ERR

echo "============================================================"
echo "▶ VemDeDelivery — testes críticos"
echo "▶ Ambiente: $ENVIRONMENT"
echo "▶ Compose: $COMPOSE_FILE"
echo "▶ Suítes: ${TEST_SUITES[*]}"
echo "============================================================"

"${DC[@]}" config --quiet

DB_CONTAINER="$("${DC[@]}" ps -q db)"

if [[ -z "$DB_CONTAINER" ]]; then
    echo "❌ PostgreSQL não está em execução." >&2
    exit 1
fi

DB_HEALTH="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$DB_CONTAINER")"

if [[ "$DB_HEALTH" != "healthy" && "$DB_HEALTH" != "running" ]]; then
    echo "❌ PostgreSQL não está saudável: $DB_HEALTH" >&2
    exit 1
fi

echo "▶ Testando ferramentas operacionais (sem acessar Docker, rede ou produção)..."
python3 -m unittest discover -s scripts/tests -p "test_*.py" -v

echo "▶ Executando em banco de teste isolado, com config.settings.test..."
echo "▶ A consulta externa de WhatsApp fica desativada neste processo de teste."

# Ignora o entrypoint de implantação e usa as configurações próprias de teste.
# Não publica portas nem inicia outros serviços.
"${DC[@]}" run --rm --no-deps \
    -e DJANGO_SETTINGS_MODULE=config.settings.test \
    -e EVOLUTION_WHATSAPP_VALIDATION_ENABLED=false \
    --entrypoint python \
    web manage.py test "${TEST_SUITES[@]}" \
    --settings=config.settings.test \
    --verbosity=2 \
    --noinput

echo ""
echo "✅ Suíte crítica concluída sem falhas em $ENVIRONMENT."

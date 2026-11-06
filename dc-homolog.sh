#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DC=(docker compose -f docker/dev/docker-compose.yml)

COMMAND=${1:-deploy}

info() {
    echo ""
    echo "============================================================"
    echo "▶ $1"
    echo "============================================================"
}

success() {
    echo ""
    echo "✅ $1"
}

test_frontend() {
    info "Executando suite exclusiva de frontend"
    "$SCRIPT_DIR/test-critical-front.sh"
}

build_homolog() {
    # Testes críticos devem ser executados pelo usuário antes do push/deploy.
    # Build não deve reexecutar Vitest.
    info "Construindo imagens locais de homologação (sem reexecutar testes)"
    "${DC[@]}" build --build-arg VDD_RUN_FRONTEND_TESTS=0
    "${DC[@]}" up -d --no-build
}

case "$COMMAND" in

    deploy)
        info "Deploy da homologação"

        build_homolog

        info "Aguardando PostgreSQL"
        until "${DC[@]}" exec -T db pg_isready >/dev/null 2>&1; do
            sleep 2
        done

        info "Executando migrations"
        "${DC[@]}" exec backend python manage.py migrate --noinput

        info "Executando collectstatic"
        "${DC[@]}" exec backend python manage.py collectstatic --noinput

        info "Validando Django"
        "${DC[@]}" exec backend python manage.py check

        info "Reiniciando aplicação"
        "${DC[@]}" restart backend celery celery-prospecting

        info "Recriando Nginx"
        "${DC[@]}" up -d --force-recreate nginx

        "${DC[@]}" ps

        success "Homologação atualizada."
        ;;

    rebuild)
        info "Rebuild da homologação"
        build_homolog

        info "Recriando Nginx"
        "${DC[@]}" up -d --force-recreate nginx
        ;;

    frontend-tests)
        test_frontend
        ;;

    restart)
        info "Restart da homologação"
        "${DC[@]}" restart
        ;;

    migrate)
        "${DC[@]}" exec backend python manage.py migrate
        ;;

    collectstatic)
        "${DC[@]}" exec backend python manage.py collectstatic --noinput
        ;;

    logs)
        "${DC[@]}" logs -f "${2:-backend}"
        ;;

    shell)
        "${DC[@]}" exec backend python manage.py shell
        ;;

    status)
        "${DC[@]}" ps
        ;;

    *)
        echo "Comandos:"
        echo ""
        echo "  ./dc-homolog.sh deploy"
        echo "  ./dc-homolog.sh rebuild"
        echo "  ./dc-homolog.sh frontend-tests"
        echo "  ./test-critical-front.sh"
        echo "  ./dc-homolog.sh restart"
        echo "  ./dc-homolog.sh migrate"
        echo "  ./dc-homolog.sh collectstatic"
        echo "  ./dc-homolog.sh logs"
        echo "  ./dc-homolog.sh shell"
        echo "  ./dc-homolog.sh status"
        exit 1
        ;;
esac

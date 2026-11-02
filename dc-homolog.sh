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
    info "Validando frontend em processos isolados (sem mascarar falhas)"
    "$SCRIPT_DIR/scripts/test-frontend-isolated.sh"
}

build_homolog() {
    # A validação completa acontece ANTES de qualquer build ou alteração nos containers.
    test_frontend
    info "Construindo imagens de homologação (testes React já aprovados)"
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
        echo "  ./dc-homolog.sh restart"
        echo "  ./dc-homolog.sh migrate"
        echo "  ./dc-homolog.sh collectstatic"
        echo "  ./dc-homolog.sh logs"
        echo "  ./dc-homolog.sh shell"
        echo "  ./dc-homolog.sh status"
        exit 1
        ;;
esac

#!/usr/bin/env bash
set -Eeuo pipefail

DC=(docker compose -f docker/prod/docker-compose.yml)

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

error() {
    echo ""
    echo "❌ $1"
    exit 1
}

wait_for_healthy() {
    local service="$1"
    local attempts="${2:-30}"

    for ((i=1; i<=attempts; i++)); do
        container_id=$("${DC[@]}" ps -q "$service" 2>/dev/null || true)

        if [[ -z "$container_id" ]]; then
            sleep 2
            continue
        fi

        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)

        if [[ "$health" == "healthy" || "$health" == "running" ]]; then
            echo "✅ $service: $health"
            return
        fi

        sleep 2
    done

    "${DC[@]}" logs --tail=100 "$service" || true
    error "$service não ficou saudável."
}

info "Verificando alterações locais"

if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    error "Existem alterações locais no servidor."
fi

BRANCH=$(git branch --show-current)

info "Atualizando produção - branch $BRANCH"

git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

info "Validando Docker Compose"
"${DC[@]}" config --quiet

info "Buildando imagens"
"${DC[@]}" build --pull

info "Subindo banco e Redis"
"${DC[@]}" up -d db redis

wait_for_healthy db
wait_for_healthy redis

info "Executando migrations"
"${DC[@]}" run --rm web python manage.py migrate --noinput

info "Executando collectstatic"
"${DC[@]}" run --rm web python manage.py collectstatic --noinput

info "Validando Django"
"${DC[@]}" run --rm web python manage.py check
"${DC[@]}" run --rm web python manage.py check --deploy --fail-level ERROR

info "Subindo aplicação"
"${DC[@]}" up -d web celery nginx

wait_for_healthy web
wait_for_healthy nginx

"${DC[@]}" ps

success "Deploy de produção concluído."


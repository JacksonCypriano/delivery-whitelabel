#!/usr/bin/env bash
set -Eeuo pipefail

DC=(docker compose -f docker/prod/docker-compose.yml)
EXPECTED_BRANCH="main"

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
    local attempts="${2:-40}"
    local sleep_seconds="${3:-2}"

    info "Aguardando $service ficar saudável"

    for ((i=1; i<=attempts; i++)); do
        local container_id
        local health

        container_id=$("${DC[@]}" ps -q "$service" 2>/dev/null || true)

        if [[ -z "$container_id" ]]; then
            echo "⏳ $service ainda não iniciou... ($i/$attempts)"
            sleep "$sleep_seconds"
            continue
        fi

        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)

        case "$health" in
            healthy)
                echo "✅ $service: healthy"
                return 0
                ;;
            running)
                echo "✅ $service: running"
                return 0
                ;;
            unhealthy|exited|dead)
                echo ""
                "${DC[@]}" logs --tail=100 "$service" || true
                error "$service falhou com status: $health"
                ;;
            *)
                echo "⏳ $service: ${health:-iniciando} ($i/$attempts)"
                ;;
        esac

        sleep "$sleep_seconds"
    done

    echo ""
    "${DC[@]}" logs --tail=100 "$service" || true
    error "$service não ficou saudável dentro do tempo esperado."
}

on_error() {
    local exit_code=$?

    echo ""
    echo "============================================================"
    echo "❌ DEPLOY INTERROMPIDO"
    echo "============================================================"
    echo ""
    echo "Código de saída: $exit_code"
    echo ""
    echo "Status atual:"
    "${DC[@]}" ps 2>/dev/null || true
    echo ""
    echo "Use para investigar:"
    echo "  docker compose -f docker/prod/docker-compose.yml logs --tail=200 web"
    echo ""

    exit "$exit_code"
}

trap on_error ERR

# ============================================================
# 1. Validações
# ============================================================

info "Validando ambiente de produção"

if [[ ! -f "docker/prod/docker-compose.yml" ]]; then
    error "docker/prod/docker-compose.yml não encontrado."
fi

if [[ ! -f "entrypoint.sh" ]]; then
    error "entrypoint.sh não encontrado."
fi

if [[ ! -d ".git" ]]; then
    error "Este diretório não é um repositório Git."
fi

BRANCH=$(git branch --show-current)

if [[ -z "$BRANCH" ]]; then
    error "Não foi possível identificar a branch atual."
fi

if [[ "$BRANCH" != "$EXPECTED_BRANCH" ]]; then
    error "Produção deve estar na branch '$EXPECTED_BRANCH'. Branch atual: '$BRANCH'."
fi

# ============================================================
# 2. Working tree
# ============================================================

info "Verificando alterações locais"

if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    error "Existem alterações locais no servidor. Deploy cancelado."
fi

echo "✅ Nenhuma alteração local."

# ============================================================
# 3. Atualização do código
# ============================================================

info "Atualizando produção - branch $BRANCH"

git pull --ff-only origin "$BRANCH"

COMMIT=$(git rev-parse --short HEAD)

echo ""
echo "Branch : $BRANCH"
echo "Commit : $COMMIT"

# ============================================================
# 4. Docker Compose
# ============================================================

info "Validando Docker Compose"

"${DC[@]}" config --quiet

echo "✅ Docker Compose válido."

# ============================================================
# 5. Build
# ============================================================

info "Construindo imagens"

"${DC[@]}" build --pull

# ============================================================
# 6. Banco e Redis
# ============================================================

info "Subindo PostgreSQL e Redis"

"${DC[@]}" up -d db redis

wait_for_healthy db
wait_for_healthy redis

# ============================================================
# 7. Web
# ============================================================
#
# O entrypoint do serviço WEB já executa automaticamente:
#
# 1. Aguarda PostgreSQL
# 2. Aguarda Redis
# 3. python manage.py migrate --noinput
# 4. python manage.py collectstatic --noinput
# 5. python manage.py check --deploy --fail-level ERROR
# 6. Inicia Gunicorn
#
# Não repetimos esses comandos aqui.
# ============================================================

info "Subindo aplicação web"

"${DC[@]}" up -d web

wait_for_healthy web

# ============================================================
# 8. Celery
# ============================================================

info "Subindo Celery Worker"

"${DC[@]}" up -d celery

wait_for_healthy celery

# ============================================================
# 9. Celery Beat
# ============================================================

info "Subindo Celery Beat"

"${DC[@]}" up -d celery-beat

# celery-beat não possui healthcheck no compose.
# Apenas verificamos se o container permaneceu em execução.

sleep 3

BEAT_CONTAINER=$("${DC[@]}" ps -q celery-beat 2>/dev/null || true)

if [[ -z "$BEAT_CONTAINER" ]]; then
    error "Container celery-beat não foi criado."
fi

BEAT_STATUS=$(docker inspect --format='{{.State.Status}}' "$BEAT_CONTAINER" 2>/dev/null || true)

if [[ "$BEAT_STATUS" != "running" ]]; then
    "${DC[@]}" logs --tail=100 celery-beat || true
    error "celery-beat não está rodando. Status: $BEAT_STATUS"
fi

echo "✅ celery-beat: running"

# ============================================================
# 10. Nginx
# ============================================================

info "Subindo Nginx"

"${DC[@]}" up -d nginx

wait_for_healthy nginx

# ============================================================
# 11. Status final
# ============================================================

info "Status final dos containers"

"${DC[@]}" ps

echo ""
echo "============================================================"
echo "🚀 VemDeDelivery"
echo "============================================================"
echo ""
echo "Ambiente : produção"
echo "Branch   : $BRANCH"
echo "Commit   : $COMMIT"
echo "URL      : https://vemdedelivery.com.br"
echo ""

success "Deploy de produção concluído com sucesso."

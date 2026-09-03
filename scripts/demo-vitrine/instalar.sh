#!/usr/bin/env bash
set -Eeuo pipefail
DEMO_ENVIRONMENT="${1:-}"
case "$DEMO_ENVIRONMENT" in
  homolog) DEMO_COMPOSE='docker/dev/docker-compose.yml' ;;
  prod) DEMO_COMPOSE='docker/prod/docker-compose.yml' ;;
  *) echo 'Uso: bash scripts/demo-vitrine/instalar.sh homolog|prod' >&2; exit 1 ;;
esac
DEMO_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEMO_ROOT="$(cd -- "$DEMO_SCRIPT_DIR/../.." && pwd)"
cd "$DEMO_ROOT"
DEMO_DC=(docker compose -f "$DEMO_COMPOSE")
"${DEMO_DC[@]}" config --quiet
DEMO_CID="$("${DEMO_DC[@]}" ps -q web)"
[[ -n "$DEMO_CID" ]] || { echo 'O serviço web não está em execução.' >&2; exit 1; }
DEMO_REMOTE_DIR="$("${DEMO_DC[@]}" exec -T web mktemp -d /tmp/vdd-demo.XXXXXXXX)"
DEMO_REMOTE_DIR="${DEMO_REMOTE_DIR//$'\r'/}"
[[ "$DEMO_REMOTE_DIR" =~ ^/tmp/vdd-demo\.[A-Za-z0-9]+$ ]] || { echo 'Diretório temporário inválido.' >&2; exit 1; }
cleanup_demo() { docker exec "$DEMO_CID" rm -rf -- "$DEMO_REMOTE_DIR" >/dev/null 2>&1 || true; }
trap cleanup_demo EXIT
# Copia apenas scripts e imagens para um diretório temporário; as mídias são
# gravadas pelo Django no MEDIA_ROOT/storage configurado, não nesta pasta.
docker cp "$DEMO_SCRIPT_DIR/." "$DEMO_CID:$DEMO_REMOTE_DIR"
"${DEMO_DC[@]}" exec -T \
  -e DEMO_PHONE="${DEMO_PHONE:-11983491206}" \
  -e DEMO_REUSE_SLUG="${DEMO_REUSE_SLUG:-}" \
  web python manage.py shell -c "import runpy; runpy.run_path('$DEMO_REMOTE_DIR/seed.py', run_name='__main__')"
echo
echo 'Para definir a senha privada do administrador, execute:'
printf 'docker compose -f %s exec web python manage.py changepassword admin_vitrine_demo\n' "$DEMO_COMPOSE"

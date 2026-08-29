#!/usr/bin/env bash
set -Eeuo pipefail
DC=(docker compose -f docker/prod/docker-compose.yml)
BACKUP_ROOT="${BACKUP_ROOT:-/opt/vemdedelivery/backups}"
BACKUP_DIR="${1:-}"
info(){ echo ""; echo "============================================================"; echo "▶ $1"; echo "============================================================"; }
error(){ echo ""; echo "❌ $1" >&2; exit 1; }
if [[ -z "$BACKUP_DIR" ]]; then BACKUP_DIR=$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -exec test -f '{}/COMPLETE' \; -print | sort | tail -n 1); fi
[[ -n "$BACKUP_DIR" ]] || error "Nenhum backup completo encontrado."
BACKUP_DIR="$(readlink -f "$BACKUP_DIR")"
DB_FILE="$BACKUP_DIR/database.dump"; MEDIA_FILE="$BACKUP_DIR/media.tar.gz"
[[ -s "$DB_FILE" && -s "$MEDIA_FILE" ]] || error "Backup incompleto."
DB_USER=$("${DC[@]}" exec -T db sh -c 'printf "%s" "$POSTGRES_USER"')
TEMP_DB="vemdedelivery_restore_test_$(date '+%Y%m%d%H%M%S')"
cleanup(){ "${DC[@]}" exec -T db dropdb -U "$DB_USER" --if-exists "$TEMP_DB" >/dev/null 2>&1 || true; }
trap cleanup EXIT
info "Validando checksums"
(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
gzip -t "$MEDIA_FILE"
info "Criando banco temporário"
"${DC[@]}" exec -T db createdb -U "$DB_USER" "$TEMP_DB"
info "Restaurando dump no banco temporário"
"${DC[@]}" exec -T db pg_restore -U "$DB_USER" -d "$TEMP_DB" --no-owner --no-privileges --exit-on-error < "$DB_FILE"
info "Validando banco restaurado"
"${DC[@]}" exec -T db psql -U "$DB_USER" -d "$TEMP_DB" -v ON_ERROR_STOP=1 -c 'SELECT COUNT(*) AS django_migrations FROM django_migrations;'
echo ""; echo "✅ Backup testado com restauração real em banco temporário."; echo "✅ Produção não foi alterada."; echo "✅ Backup: $BACKUP_DIR"

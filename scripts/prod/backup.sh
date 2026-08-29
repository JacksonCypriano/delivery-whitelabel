#!/usr/bin/env bash
set -Eeuo pipefail
DC=(docker compose -f docker/prod/docker-compose.yml)
BACKUP_ROOT="${BACKUP_ROOT:-/opt/vemdedelivery/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"
DB_FILE="$BACKUP_DIR/database.dump"
MEDIA_FILE="$BACKUP_DIR/media.tar.gz"
MANIFEST_FILE="$BACKUP_DIR/manifest.txt"
LOCK_FILE="${BACKUP_LOCK_FILE:-/tmp/vemdedelivery-backup.lock}"
info(){ echo ""; echo "============================================================"; echo "▶ $1"; echo "============================================================"; }
success(){ echo ""; echo "✅ $1"; }
error(){ echo ""; echo "❌ $1" >&2; exit 1; }
cleanup_failed_backup(){ code=$?; if [[ $code -ne 0 && -d "$BACKUP_DIR" ]]; then touch "$BACKUP_DIR/FAILED" 2>/dev/null || true; echo "Backup incompleto: $BACKUP_DIR" >&2; fi; exit "$code"; }
trap cleanup_failed_backup EXIT
command -v docker >/dev/null 2>&1 || error "Docker não encontrado."
command -v flock >/dev/null 2>&1 || error "flock não encontrado."
command -v sha256sum >/dev/null 2>&1 || error "sha256sum não encontrado."
mkdir -p "$BACKUP_ROOT" && chmod 700 "$BACKUP_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || error "Já existe um backup em execução."
info "Validando ambiente"
"${DC[@]}" config --quiet
DB_CONTAINER=$("${DC[@]}" ps -q db)
[[ -n "$DB_CONTAINER" ]] || error "Container do PostgreSQL não está em execução."
DB_HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$DB_CONTAINER")
[[ "$DB_HEALTH" == "healthy" || "$DB_HEALTH" == "running" ]] || error "PostgreSQL não está saudável: $DB_HEALTH"
DB_USER=$("${DC[@]}" exec -T db sh -c 'printf "%s" "$POSTGRES_USER"')
DB_NAME=$("${DC[@]}" exec -T db sh -c 'printf "%s" "$POSTGRES_DB"')
[[ -n "$DB_USER" && -n "$DB_NAME" ]] || error "POSTGRES_USER/POSTGRES_DB não encontrados."
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
info "Backup do PostgreSQL"
"${DC[@]}" exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$DB_FILE"
[[ -s "$DB_FILE" ]] || error "O dump do PostgreSQL ficou vazio."
"${DC[@]}" exec -T db pg_restore --list < "$DB_FILE" >/dev/null
echo "✅ PostgreSQL: $(du -h "$DB_FILE" | cut -f1)"
info "Backup dos arquivos de mídia"
"${DC[@]}" run --rm --no-deps --entrypoint sh web -c 'tar -C /app/media -czf - .' > "$MEDIA_FILE"
[[ -s "$MEDIA_FILE" ]] || error "O backup de mídia ficou vazio."
gzip -t "$MEDIA_FILE"
echo "✅ Media: $(du -h "$MEDIA_FILE" | cut -f1)"
info "Gerando manifesto e checksums"
{
 echo "project=VemDeDelivery"
 echo "created_at=$(date --iso-8601=seconds)"
 echo "hostname=$(hostname)"
 echo "git_branch=$(git branch --show-current 2>/dev/null || true)"
 echo "git_commit=$(git rev-parse HEAD 2>/dev/null || true)"
 echo "database=$DB_NAME"
 echo "database_user=$DB_USER"
 echo "retention_days=$RETENTION_DAYS"
} > "$MANIFEST_FILE"
(cd "$BACKUP_DIR" && sha256sum database.dump media.tar.gz manifest.txt > SHA256SUMS)
touch "$BACKUP_DIR/COMPLETE"
info "Aplicando retenção"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;
trap - EXIT
echo ""; echo "Backup   : $BACKUP_DIR"; echo "Retenção : $RETENTION_DAYS dias"
success "Backup concluído e validado."

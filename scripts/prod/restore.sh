#!/usr/bin/env bash
set -Eeuo pipefail
DC=(docker compose -f docker/prod/docker-compose.yml)
BACKUP_DIR="${1:-}"
FORCE="${2:-}"
APP_SERVICES=(web celery celery-beat nginx)
info(){ echo ""; echo "============================================================"; echo "▶ $1"; echo "============================================================"; }
success(){ echo ""; echo "✅ $1"; }
error(){ echo ""; echo "❌ $1" >&2; exit 1; }
[[ -n "$BACKUP_DIR" ]] || { echo "Uso: ./restore-prod.sh /opt/vemdedelivery/backups/AAAAMMDD_HHMMSS"; exit 1; }
BACKUP_DIR="$(readlink -f "$BACKUP_DIR")"
DB_FILE="$BACKUP_DIR/database.dump"; MEDIA_FILE="$BACKUP_DIR/media.tar.gz"
[[ -f "$BACKUP_DIR/COMPLETE" ]] || error "Backup não está marcado como COMPLETE."
[[ -s "$DB_FILE" && -s "$MEDIA_FILE" && -s "$BACKUP_DIR/SHA256SUMS" ]] || error "Backup incompleto."
info "Validando integridade do backup"
(cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
gzip -t "$MEDIA_FILE"
DB_USER=$("${DC[@]}" exec -T db sh -c 'printf "%s" "$POSTGRES_USER"')
DB_NAME=$("${DC[@]}" exec -T db sh -c 'printf "%s" "$POSTGRES_DB"')
"${DC[@]}" exec -T db pg_restore --list < "$DB_FILE" >/dev/null
echo ""; echo "ATENÇÃO: esta operação substituirá banco e mídia da PRODUÇÃO."; echo "Banco : $DB_NAME"; echo "Backup: $BACKUP_DIR"; echo ""
if [[ "$FORCE" != "--force" ]]; then read -r -p "Digite RESTAURAR $DB_NAME para continuar: " CONFIRMATION; [[ "$CONFIRMATION" == "RESTAURAR $DB_NAME" ]] || error "Restauração cancelada."; fi
info "Criando backup de segurança antes da restauração"
"$(dirname "$0")/backup.sh"
info "Parando aplicação"
"${DC[@]}" stop "${APP_SERVICES[@]}"
restore_failed(){ code=$?; echo ""; echo "❌ A restauração falhou. PostgreSQL foi mantido em execução para diagnóstico."; exit "$code"; }
trap restore_failed ERR
info "Restaurando PostgreSQL"
"${DC[@]}" exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner --no-privileges --exit-on-error < "$DB_FILE"
info "Restaurando arquivos de mídia"
"${DC[@]}" run --rm --no-deps --entrypoint sh web -c 'find /app/media -mindepth 1 -delete'
"${DC[@]}" run --rm --no-deps --entrypoint sh -T web -c 'tar -C /app/media -xzf -' < "$MEDIA_FILE"
info "Subindo aplicação"
"${DC[@]}" up -d web celery celery-beat nginx
"${DC[@]}" ps
trap - ERR
success "Restauração concluída."

#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/vemdedelivery/app}"
BACKUP_SCRIPT="$APP_DIR/backup-prod.sh"
CRON_FILE="/etc/cron.d/vemdedelivery-backup"
CRON_SCHEDULE="${BACKUP_CRON_SCHEDULE:-30 3 * * *}"
RUN_AS_USER="${BACKUP_CRON_USER:-deploy}"
[[ -x "$BACKUP_SCRIPT" ]] || { echo "❌ Script não encontrado ou sem execução: $BACKUP_SCRIPT"; exit 1; }
TMP_FILE=$(mktemp); trap 'rm -f "$TMP_FILE"' EXIT
cat > "$TMP_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
$CRON_SCHEDULE $RUN_AS_USER cd $APP_DIR && $BACKUP_SCRIPT >> /var/log/vemdedelivery-backup.log 2>&1
EOF
sudo install -m 0644 "$TMP_FILE" "$CRON_FILE"
sudo touch /var/log/vemdedelivery-backup.log
sudo chown "$RUN_AS_USER":"$RUN_AS_USER" /var/log/vemdedelivery-backup.log
echo "✅ Cron instalado: $CRON_SCHEDULE"; echo "✅ Log: /var/log/vemdedelivery-backup.log"

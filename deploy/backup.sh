#!/usr/bin/env bash
# Daily backup of the SQLite database and uploaded photos.
# Installed via cron, e.g.:
#   0 2 * * * /opt/photo-contest/deploy/backup.sh
set -euo pipefail

APP_DIR="/opt/photo-contest"
BACKUP_DIR="/opt/backups"
DATE=$(date +%F)

mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/contest-$DATE.tar.gz" -C "$APP_DIR" data.db uploads

# Keep the last 30 daily backups, delete older ones.
find "$BACKUP_DIR" -name 'contest-*.tar.gz' -mtime +30 -delete

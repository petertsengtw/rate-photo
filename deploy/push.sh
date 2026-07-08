#!/usr/bin/env bash
# Sync local code changes to the Linode host and restart the app.
# Run from your local machine (not on the server).
#
# Usage:
#   ./deploy/push.sh user@host
set -euo pipefail

TARGET="${1:?Usage: push.sh <ssh-user@host>}"
REMOTE_DIR="/opt/photo-contest"

# --no-owner/--no-group: don't propagate the local machine's file ownership
# to the server (the app runs as www-data there; the chown step below
# re-asserts that regardless of what rsync received).
rsync -avz --delete --no-owner --no-group \
  --exclude 'venv/' \
  --exclude 'data.db' \
  --exclude 'data.db.bak*' \
  --exclude '.env' \
  --exclude '.secret_key' \
  --exclude 'uploads/' \
  --exclude '__pycache__/' \
  --exclude '.git/' \
  --exclude '.pytest_cache/' \
  --exclude '.claude/' \
  ./ "$TARGET:$REMOTE_DIR/"

ssh "$TARGET" "cd $REMOTE_DIR && sudo chown -R www-data:www-data $REMOTE_DIR && venv/bin/pip install -q -r requirements.txt && sudo systemctl restart photo-contest"

echo "Deployed. Checking service status..."
ssh "$TARGET" "sudo systemctl status photo-contest --no-pager -l | head -15"

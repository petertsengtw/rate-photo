#!/usr/bin/env bash
# One-time provisioning script for the app itself (no reverse proxy / HTTPS).
# Run as root AFTER the application code has been copied to /opt/photo-contest.
#
# This intentionally does NOT touch port 80/443 or install a reverse proxy,
# since this host may already be running another web server for other sites.
# See deploy/setup_https.sh for wiring up a domain + HTTPS once you have one.
#
# Usage:
#   sudo ./deploy/setup_server.sh
set -euo pipefail

APP_DIR="/opt/photo-contest"

echo "==> Updating system packages"
apt update && apt upgrade -y

echo "==> Installing Python and build tools"
apt install -y python3.12 python3.12-venv python3-pip git

echo "==> Setting up virtualenv and dependencies in $APP_DIR"
cd "$APP_DIR"
python3.12 -m venv venv
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r requirements.txt

echo "==> Creating uploads directory and fixing ownership"
mkdir -p "$APP_DIR/uploads"
id -u www-data &>/dev/null || useradd -r -s /usr/sbin/nologin www-data
chown -R www-data:www-data "$APP_DIR"

echo "==> Installing systemd service"
cp "$APP_DIR/deploy/photo-contest.service" /etc/systemd/system/photo-contest.service
systemctl daemon-reload
systemctl enable --now photo-contest

echo "==> Installing daily backup cron job"
chmod +x "$APP_DIR/deploy/backup.sh"
( crontab -l 2>/dev/null | grep -v 'photo-contest/deploy/backup.sh' ; echo "0 2 * * * $APP_DIR/deploy/backup.sh" ) | crontab -

echo "==> Done."
echo "The app is now running on 127.0.0.1:8000 (not yet exposed to the internet)."
echo "Next steps:"
echo "  1. Create the first admin account:"
echo "     cd $APP_DIR && sudo -u www-data venv/bin/python -m scripts.create_admin <username> <password>"
echo "  2. Expose it (temporarily over plain HTTP via a firewall rule for port 8000,"
echo "     or properly via deploy/setup_https.sh once you have a domain)."

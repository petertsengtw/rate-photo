#!/usr/bin/env bash
# Wire up a domain + HTTPS for the already-running photo-contest app
# (see deploy/setup_server.sh). Run this once your domain's DNS A record
# points at this server's public IP.
#
# Auto-detects the reverse proxy to use:
#   - If Apache is already running on this host (e.g. serving other sites),
#     adds a new name-based VirtualHost for your domain and uses
#     certbot --apache for the certificate. This does not touch any
#     existing Apache site.
#   - Otherwise, installs Caddy, which handles HTTPS automatically.
#
# Usage:
#   sudo ./deploy/setup_https.sh contest.yourclub.org
set -euo pipefail

DOMAIN="${1:?Usage: setup_https.sh <domain>}"
APP_DIR="/opt/photo-contest"

if systemctl is-active --quiet apache2; then
  echo "==> Apache detected. Adding a VirtualHost for $DOMAIN"
  a2enmod proxy proxy_http >/dev/null

  cat > "/etc/apache2/sites-available/${DOMAIN}.conf" <<EOF
<VirtualHost *:80>
    ServerName ${DOMAIN}
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/
    ErrorLog \${APACHE_LOG_DIR}/${DOMAIN}-error.log
    CustomLog \${APACHE_LOG_DIR}/${DOMAIN}-access.log combined
</VirtualHost>
EOF
  a2ensite "${DOMAIN}.conf" >/dev/null
  systemctl reload apache2

  echo "==> Requesting HTTPS certificate via certbot"
  apt install -y certbot python3-certbot-apache
  certbot --apache -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN}" --redirect

else
  echo "==> No Apache found. Installing Caddy for automatic HTTPS."
  if ! command -v caddy &>/dev/null; then
    apt install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt update && apt install -y caddy
  fi
  sed "s/contest.yourclub.org/$DOMAIN/" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
fi

echo "==> Switching cookies back to secure (HTTPS-only) mode"
sed -i '/PHOTO_CONTEST_SECURE_COOKIES/d' "$APP_DIR/.env" 2>/dev/null || true
systemctl restart photo-contest

echo "==> Done. Visit https://$DOMAIN/admin/login to confirm."
echo "Remember to update your Cloud Firewall / router if you had opened a temporary port for plain-HTTP testing."

#!/usr/bin/env bash
# Fresh-VM bootstrap for the Hetzner production deploy.
# Run on Ubuntu 24.04 as root. See README.md "Production deploy".
#
# Usage: bootstrap_vm.sh <git-repo-url>

set -euo pipefail

REPO_URL="${1:?usage: bootstrap_vm.sh <git-repo-url>}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"

if [[ $EUID -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

# non-root user with passwordless sudo + root's SSH key
if ! id "$DEPLOY_USER" &>/dev/null; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
  usermod -aG sudo "$DEPLOY_USER"
  rsync -a --chown="$DEPLOY_USER:$DEPLOY_USER" /root/.ssh "/home/$DEPLOY_USER/"
fi
echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$DEPLOY_USER"
chmod 440 "/etc/sudoers.d/$DEPLOY_USER"

# SSH: key-only, no root login
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# firewall: SSH only — the tunnel is outbound, no inbound HTTP needed
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow OpenSSH
ufw --force enable

# Docker + Compose plugin (official convenience script)
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker "$DEPLOY_USER"

# unattended security updates
DEBIAN_FRONTEND=noninteractive apt-get install -y unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# clone the repo as the deploy user
mkdir -p /opt/ig
chown "$DEPLOY_USER:$DEPLOY_USER" /opt/ig
sudo -u "$DEPLOY_USER" git clone "$REPO_URL" /opt/ig/app

cat <<EOF

Done. Next:
  1. ssh $DEPLOY_USER@<vm-ip>
  2. cd /opt/ig/app && cp .env.example .env
  3. Fill in .env (LIVEKIT_*, OPENAI_API_KEY, WEBAPP_PUBLIC_URL, TUNNEL_TOKEN, COMPOSE_FILE)
  4. docker compose up -d --build

See README.md "Production deploy" for the Cloudflare Tunnel + Access steps.
EOF

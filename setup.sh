#!/bin/bash
# ══════════════════════════════════════════════════════
#  MAFIO Liquidity Scanner — VPS Setup Script
#  Usage: wget -O setup.sh <url> && bash setup.sh
# ══════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════╗"
echo "║   💀 MAFIO Liquidity Scanner v3.1   ║"
echo "║        VPS Setup Script              ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. System dependencies ─────────────────────────────
echo -e "${YELLOW}[1/6] Installing system dependencies...${NC}"
apt-get update -qq
apt-get install -y python3 python3-pip screen curl git -qq
echo -e "${GREEN}✅ System dependencies installed${NC}"

# ── 2. Python packages ────────────────────────────────
echo -e "${YELLOW}[2/6] Installing Python packages...${NC}"
pip3 install requests websocket-client --quiet
echo -e "${GREEN}✅ Python packages installed${NC}"

# ── 3. Download bot ───────────────────────────────────
echo -e "${YELLOW}[3/6] Downloading bot...${NC}"
mkdir -p /root/mafio-bot
cd /root/mafio-bot

curl -sL "https://raw.githubusercontent.com/Said1612/crypto-scanner-bot/claude/initial-setup-DBIke/main.py" -o main.py

if [ ! -f main.py ] || [ ! -s main.py ]; then
    echo -e "${RED}❌ Failed to download main.py — check URL or internet connection${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Bot downloaded to /root/mafio-bot/${NC}"

# ── 4. Environment variables ──────────────────────────
echo -e "${YELLOW}[4/6] Setting up environment variables...${NC}"
echo ""
echo -e "${CYAN}Please enter your configuration:${NC}"

read -p "TELEGRAM_TOKEN: " TELEGRAM_TOKEN
read -p "CHAT_ID: " CHAT_ID
read -p "GROUP_ID (leave blank if none): " GROUP_ID
read -p "REDIS_URL (Upstash REST URL): " REDIS_URL
read -p "UPSTASH_REDIS_REST_TOKEN: " REDIS_TOKEN
read -p "USE_BINANCE [true/false] (default: true): " USE_BINANCE
USE_BINANCE=${USE_BINANCE:-true}
read -p "PROXY_URL (leave blank if none): " PROXY_URL

cat > /root/mafio-bot/.env << EOF
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
CHAT_ID=${CHAT_ID}
GROUP_ID=${GROUP_ID}
REDIS_URL=${REDIS_URL}
UPSTASH_REDIS_REST_TOKEN=${REDIS_TOKEN}
USE_BINANCE=${USE_BINANCE}
PROXY_URL=${PROXY_URL}
EOF

echo -e "${GREEN}✅ Environment saved to /root/mafio-bot/.env${NC}"

# ── 5. Systemd service ────────────────────────────────
echo -e "${YELLOW}[5/6] Creating systemd service...${NC}"

# Load env vars for service file
ENV_VARS=""
while IFS='=' read -r key value; do
    [ -z "$key" ] && continue
    [[ "$key" == \#* ]] && continue
    ENV_VARS="${ENV_VARS}Environment=\"${key}=${value}\"\n"
done < /root/mafio-bot/.env

cat > /etc/systemd/system/mafio-bot.service << EOF
[Unit]
Description=MAFIO Liquidity Scanner Bot
After=network.target
Restart=always

[Service]
Type=simple
WorkingDirectory=/root/mafio-bot
ExecStart=/usr/bin/python3 /root/mafio-bot/main.py
$(echo -e "$ENV_VARS")
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mafio-bot
systemctl start mafio-bot

echo -e "${GREEN}✅ Service installed and started${NC}"

# ── 6. Status check ───────────────────────────────────
echo -e "${YELLOW}[6/6] Checking status...${NC}"
sleep 3
systemctl status mafio-bot --no-pager -l | head -20

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        ✅ Setup Complete!             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "📋 ${CYAN}Useful commands:${NC}"
echo -e "  View logs:    ${YELLOW}journalctl -u mafio-bot -f${NC}"
echo -e "  Stop bot:     ${YELLOW}systemctl stop mafio-bot${NC}"
echo -e "  Restart bot:  ${YELLOW}systemctl restart mafio-bot${NC}"
echo -e "  Update bot:   ${YELLOW}bash /root/mafio-bot/update.sh${NC}"
echo ""

# ── Create update script ──────────────────────────────
cat > /root/mafio-bot/update.sh << 'EOF'
#!/bin/bash
echo "🔄 Updating MAFIO Bot..."
curl -sL "https://raw.githubusercontent.com/Said1612/crypto-scanner-bot/claude/initial-setup-DBIke/main.py" -o /root/mafio-bot/main.py
systemctl restart mafio-bot
echo "✅ Bot updated and restarted"
journalctl -u mafio-bot -n 10 --no-pager
EOF

chmod +x /root/mafio-bot/update.sh
echo -e "  Update bot:   ${YELLOW}bash /root/mafio-bot/update.sh${NC}"

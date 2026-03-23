#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# install.sh — Instalador completo de CineBot para Linux / macOS
# ─────────────────────────────────────────────────────────────────
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
# If not root, use sudo; if root, run directly
SUDO=""
[[ "$EUID" -ne 0 ]] && SUDO="sudo"

ok()    { echo -e "${GREEN}✓ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $1${NC}"; }
err()   { echo -e "${RED}✗ $1${NC}"; exit 1; }
info()  { echo -e "${BLUE}ℹ $1${NC}"; }
ask()   { echo -e "${YELLOW}→ $1${NC}"; }
title() { echo -e "\n${BLUE}━━━ $1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

echo ""
echo -e "${BLUE}🎬  CineBot — Full Installer${NC}"
echo "────────────────────────────────────────────"

OS="linux"
[[ "$OSTYPE" == "darwin"* ]] && OS="mac"
DISTRO=""
command -v lsb_release &>/dev/null && DISTRO=$(lsb_release -si)
ok "System: $OS ${DISTRO:+($DISTRO)}"

# ── 1. Python ─────────────────────────────────────────────────────
title "1. Python 3"
if command -v python3 &>/dev/null; then
    ok "Python $(python3 --version | cut -d' ' -f2) ya instalado"
else
    warn "Installing Python 3..."
    if [[ "$OS" == "linux" ]]; then
        apt update -qq && apt install -y python3 python3-venv python3-pip
    else
        command -v brew &>/dev/null && brew install python3 || err "Instala Homebrew: https://brew.sh"
    fi
    ok "Python installed"
fi

# ── 2. mkvtoolnix ─────────────────────────────────────────────────
title "2. mkvtoolnix"
if command -v mkvmerge &>/dev/null; then
    ok "mkvmerge already installed"
else
    warn "Installing mkvtoolnix..."
    if [[ "$OS" == "linux" ]]; then apt install -y mkvtoolnix
    else brew install mkvtoolnix; fi
    ok "mkvtoolnix installed"
fi

# ── 3. qBittorrent ────────────────────────────────────────────────
title "3. qBittorrent"
if command -v qbittorrent-nox &>/dev/null || command -v qbittorrent &>/dev/null; then
    ok "qBittorrent already installed"
else
    warn "Installing qbittorrent-nox..."
    if [[ "$OS" == "linux" ]]; then
        apt install -y qbittorrent-nox
        cat > /tmp/qbt.service << EOF
[Unit]
Description=qBittorrent-nox
After=network.target
[Service]
Type=simple
User=$USER
ExecStart=/usr/bin/qbittorrent-nox
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
        cp /tmp/qbt.service /etc/systemd/system/qbittorrent.service
        systemctl daemon-reload && systemctl enable qbittorrent && systemctl start qbittorrent
        ok "qbittorrent-nox installed and started"
        info "Web UI: http://localhost:8080  |  usuario: admin  |  pass: adminadmin"
        warn "Change the password before continuing"
        ask "Press Enter when qBittorrent is configured..."; read -r
    else
        warn "Install qBittorrent from: https://www.qbittorrent.org/download"
        ask "Press Enter when ready..."; read -r
    fi
fi

# ── 4. Jackett ────────────────────────────────────────────────────
title "4. Jackett"
if curl -s --max-time 3 http://localhost:9117 &>/dev/null; then
    ok "Jackett is already running"
elif [[ "$OS" == "linux" ]]; then
    warn "Installing Jackett..."
    JTMP=$(mktemp -d)
    JVER=$(curl -s https://api.github.com/repos/Jackett/Jackett/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    curl -sL "https://github.com/Jackett/Jackett/releases/download/${JVER}/Jackett.Binaries.LinuxAMDx64.tar.gz" -o "$JTMP/jackett.tar.gz"
    tar -xzf "$JTMP/jackett.tar.gz" -C /opt/
    mv /opt/Jackett* /opt/Jackett 2>/dev/null || true
    cd /opt/Jackett && $SUDO ./install_service_systemd.sh
    systemctl enable jackett && systemctl start jackett
    ok "Jackett installed — add indexers at http://localhost:9117"
else
    warn "Install Jackett from: https://github.com/Jackett/Jackett/releases"
    ask "Press Enter when ready..."; read -r
fi

# ── 5. Directorio del bot ─────────────────────────────────────────
title "5. Installation directory"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/cine_bot"
[[ "$OS" == "mac" ]] && INSTALL_DIR="$HOME/cine_bot"
ask "Where to install? [Enter = $INSTALL_DIR]:"; read -r INPUT_DIR
[[ -n "$INPUT_DIR" ]] && INSTALL_DIR="$INPUT_DIR"
mkdir -p "$INSTALL_DIR" && chown "$USER":"$USER" "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/" && cd "$INSTALL_DIR"
ok "Files copied to $INSTALL_DIR"

# ── 6. Entorno virtual ────────────────────────────────────────────
title "6. Python dependencies"
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
ok "Dependencies installed"

# ── 7. Configuración ──────────────────────────────────────────────
title "7. Bot configuration"
info "You need a bot from @BotFather and your numeric ID from @userinfobot"
echo ""
ask "Telegram Token (from @BotFather):"; read -r TG_TOKEN
ask "Your numeric Telegram ID (from @userinfobot):"; read -r TG_ID
ask "qBittorrent Web UI username [admin]:"; read -r QB_USER; QB_USER="${QB_USER:-admin}"
ask "qBittorrent Web UI password:"; read -r -s QB_PASS; echo ""
ask "OMDB API Key — free at omdbapi.com/apikey.aspx [Enter to skip]:"; read -r OMDB_KEY
info "Jackett API key at http://localhost:9117 (arriba a la derecha)"
ask "Jackett API Key [Enter to skip]:"; read -r JACKETT_KEY

# ── 8. Carpetas ───────────────────────────────────────────────────
title "8. Your media library folders"
info "Add all paths you want. Leave empty to finish."
echo ""

collect_folders() {
    local label="$1"; local folders=(); local i=1
    while true; do
        ask "Folder for $label #$i (Enter to finish):"; read -r folder
        [[ -z "$folder" ]] && break
        folders+=("$folder")
        mkdir -p "$folder" 2>/dev/null || mkdir -p "$folder" 2>/dev/null || true
        ok "Added: $folder"; ((i++))
    done
    local result=""
    for f in "${folders[@]}"; do
        [[ -n "$result" ]] && result="$result, "
        result="${result}\"$f\""
    done
    echo "$result"
}

echo "── Movies ──"; MOVIE_FOLDERS=$(collect_folders "Movies")
echo ""; echo "── Kids Movies ──"; KIDS_FOLDERS=$(collect_folders "Kids Movies")
echo ""; echo "── TV Shows ──"; SERIES_FOLDERS=$(collect_folders "TV Shows")
echo ""; echo "── Kids TV Shows ──"; SERIES_KIDS_FOLDERS=$(collect_folders "Kids TV Shows")
echo ""
ask "Manual downloads folder [/home/$USER/jdownloader]:"; read -r JDOWNLOADER_DIR
JDOWNLOADER_DIR="${JDOWNLOADER_DIR:-/home/$USER/jdownloader}"
mkdir -p "$JDOWNLOADER_DIR" 2>/dev/null || true

# ── 9. Escribir config.py ─────────────────────────────────────────
title "9. Generating config.py"
cat > "$INSTALL_DIR/config.py" << EOF
# CineBot — Configuración generada el $(date '+%Y-%m-%d %H:%M')

TELEGRAM_TOKEN   = "$TG_TOKEN"
ALLOWED_USER_ID  = $TG_ID

QB_HOST          = "localhost"
QB_PORT          = 8080
QB_USER          = "$QB_USER"
QB_PASS          = "$QB_PASS"

OMDB_KEY         = "$OMDB_KEY"
JACKETT_URL      = "http://localhost:9117/api/v2.0/indexers/all/results"
JACKETT_KEY      = "$JACKETT_KEY"

JDOWNLOADER_DIR  = "$JDOWNLOADER_DIR"
EOF
ok "config.py created"

# ── 10. Systemd service ──────────────────────────────────────────
title "10. Systemd service"
if [[ "$OS" == "linux" ]]; then
    cat > /tmp/cine_bot.service << EOF
[Unit]
Description=CineBot - Telegram to qBittorrent
After=network.target
[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python bot.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF
    cp /tmp/cine_bot.service /etc/systemd/system/cine_bot.service
    systemctl daemon-reload && systemctl enable cine_bot && systemctl start cine_bot
    ok "cine_bot service installed and started"
fi

# ── Resumen ───────────────────────────────────────────────────────
title "✅ Installation complete"
echo ""
ok "CineBot is running"
echo ""
if [[ "$OS" == "linux" ]]; then
    echo "  View logs:    journalctl -u cine_bot -f"
    echo "  Restart:   systemctl restart cine_bot"
else
    echo "  Start:     cd $INSTALL_DIR && venv/bin/python bot.py"
fi
echo ""
echo "  🤖 Open Telegram and write to your bot: menu"
echo ""
warn "Remember to add indexers in Jackett: http://localhost:9117"
warn "Recommended: 1337x, The Pirate Bay, TorrentGalaxy"
echo ""

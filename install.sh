#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# install.sh — Instalador de CineBot para Linux / macOS
# ─────────────────────────────────────────────────────────────────
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
err()  { echo -e "${RED}✗ $1${NC}"; exit 1; }
ask()  { echo -e "${YELLOW}→ $1${NC}"; }

echo ""
echo "🎬  CineBot — Instalador"
echo "────────────────────────────────────────"
echo ""

# ── Detectar OS ───────────────────────────────────────────────────
OS="linux"
if [[ "$OSTYPE" == "darwin"* ]]; then OS="mac"; fi
ok "Sistema detectado: $OS"

# ── Python ────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    err "Python 3 no está instalado. Instálalo primero."
fi
PYVER=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
ok "Python $PYVER encontrado"

# ── Directorio de instalación ─────────────────────────────────────
INSTALL_DIR="/opt/cine_bot"
if [[ "$OS" == "mac" ]]; then INSTALL_DIR="$HOME/cine_bot"; fi

ask "¿Dónde instalar el bot? [Enter = $INSTALL_DIR]:"
read -r INPUT_DIR
if [[ -n "$INPUT_DIR" ]]; then INSTALL_DIR="$INPUT_DIR"; fi

sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER":"$USER" "$INSTALL_DIR"
cp -r . "$INSTALL_DIR/"
ok "Archivos copiados a $INSTALL_DIR"

# ── Entorno virtual ───────────────────────────────────────────────
cd "$INSTALL_DIR"
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
ok "Dependencias Python instaladas"

# ── Configuración interactiva ─────────────────────────────────────
echo ""
echo "────────────────────────────────────────"
echo "  Configuración del bot"
echo "────────────────────────────────────────"
echo ""

ask "Token de Telegram (de @BotFather):"
read -r TG_TOKEN

ask "Tu Telegram ID numérico (de @userinfobot):"
read -r TG_ID

ask "Usuario de qBittorrent Web UI [admin]:"
read -r QB_USER; QB_USER="${QB_USER:-admin}"

ask "Contraseña de qBittorrent Web UI:"
read -r QB_PASS

ask "OMDB API Key (gratis en omdbapi.com/apikey.aspx) [dejar vacío para omitir]:"
read -r OMDB_KEY

ask "Jackett API Key (de http://localhost:9117) [dejar vacío para omitir]:"
read -r JACKETT_KEY

echo ""
echo "── Carpetas de tu biblioteca ────────────────"
warn "Puedes dejar vacío y editar config.py después."
echo ""

ask "Carpeta de Películas (ej: /mnt/disco/Películas):"
read -r FOLDER_MOVIES

ask "Carpeta de Películas Niños [vacío para omitir]:"
read -r FOLDER_KIDS

ask "Carpeta de Series (ej: /mnt/disco/Series):"
read -r FOLDER_SERIES

ask "Carpeta de Series Niños [vacío para omitir]:"
read -r FOLDER_SERIES_KIDS

echo ""
ask "¿Quieres agregar más carpetas de películas? (s/n):"
read -r MORE_MOVIES
EXTRA_MOVIE_FOLDERS=""
while [[ "$MORE_MOVIES" == "s" || "$MORE_MOVIES" == "S" ]]; do
    ask "Ruta de la carpeta adicional:"
    read -r EXTRA
    EXTRA_MOVIE_FOLDERS="$EXTRA_MOVIE_FOLDERS, \"$EXTRA\""
    ask "¿Agregar otra? (s/n):"
    read -r MORE_MOVIES
done

ask "¿Quieres agregar más carpetas de series? (s/n):"
read -r MORE_SERIES
EXTRA_SERIES_FOLDERS=""
while [[ "$MORE_SERIES" == "s" || "$MORE_SERIES" == "S" ]]; do
    ask "Ruta de la carpeta adicional:"
    read -r EXTRA
    EXTRA_SERIES_FOLDERS="$EXTRA_SERIES_FOLDERS, \"$EXTRA\""
    ask "¿Agregar otra? (s/n):"
    read -r MORE_SERIES
done

# Build folder arrays
MOVIE_FOLDERS="\"$FOLDER_MOVIES\""
[[ -n "$FOLDER_KIDS" ]] && MOVIE_FOLDERS="$MOVIE_FOLDERS, \"$FOLDER_KIDS\""
MOVIE_FOLDERS="$MOVIE_FOLDERS$EXTRA_MOVIE_FOLDERS"

SERIES_FOLDERS="\"$FOLDER_SERIES\""
[[ -n "$FOLDER_SERIES_KIDS" ]] && SERIES_FOLDERS="$SERIES_FOLDERS, \"$FOLDER_SERIES_KIDS\""
SERIES_FOLDERS="$SERIES_FOLDERS$EXTRA_SERIES_FOLDERS"

# ── Escribir config.py ────────────────────────────────────────────
cat > "$INSTALL_DIR/config.py" << EOF
TELEGRAM_TOKEN   = "$TG_TOKEN"
ALLOWED_USER_ID  = $TG_ID
QB_HOST          = "localhost"
QB_PORT          = 8080
QB_USER          = "$QB_USER"
QB_PASS          = "$QB_PASS"
OMDB_KEY         = "$OMDB_KEY"
JACKETT_URL      = "http://localhost:9117/api/v2.0/indexers/all/results"
JACKETT_KEY      = "$JACKETT_KEY"
EOF
ok "config.py creado"

# ── Servicio systemd (solo Linux) ─────────────────────────────────
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
    sudo cp /tmp/cine_bot.service /etc/systemd/system/cine_bot.service
    sudo systemctl daemon-reload
    sudo systemctl enable cine_bot
    sudo systemctl start cine_bot
    ok "Servicio instalado y arrancado"

    echo ""
    echo "────────────────────────────────────────"
    ok "¡Instalación completada!"
    echo ""
    echo "  Ver logs:    journalctl -u cine_bot -f"
    echo "  Reiniciar:   sudo systemctl restart cine_bot"
    echo "  Detener:     sudo systemctl stop cine_bot"
else
    # macOS: launchd o ejecución manual
    echo ""
    echo "────────────────────────────────────────"
    ok "¡Instalación completada!"
    echo ""
    echo "  Para iniciar el bot:"
    echo "  cd $INSTALL_DIR && venv/bin/python bot.py"
fi

echo ""
warn "Recuerda agregar indexers en Jackett: http://localhost:9117"
warn "Habilita la Web UI de qBittorrent: Herramientas → Preferencias → Web UI"
echo ""

# ─────────────────────────────────────────────────────────────────
# config.py — Configuración de CineBot
# Copia este archivo como config.py y rellena tus valores.
# NUNCA subas config.py a GitHub (ya está en .gitignore)
# ─────────────────────────────────────────────────────────────────

# ── Telegram ──────────────────────────────────────────────────────
# Token del bot — obtenlo con @BotFather en Telegram
TELEGRAM_TOKEN   = "TU_TOKEN_AQUI"

# Tu Telegram ID numérico — obtenlo con @userinfobot
# Este usuario es el administrador: puede agregar otros usuarios
ALLOWED_USER_ID  = 123456789

# ── qBittorrent Web UI ────────────────────────────────────────────
QB_HOST          = "localhost"
QB_PORT          = 8080
QB_USER          = "admin"
QB_PASS          = "tu_contraseña_qbittorrent"

# ── OMDB API (posters, info de películas) ─────────────────────────
# API key gratuita en: http://www.omdbapi.com/apikey.aspx
OMDB_KEY         = "tu_omdb_api_key"

# ── Jackett (búsqueda de series) ──────────────────────────────────
# Interfaz web en: http://localhost:9117
JACKETT_URL      = "http://localhost:9117/api/v2.0/indexers/all/results"
JACKETT_KEY      = "tu_jackett_api_key"

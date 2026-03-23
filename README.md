# 🎬 CineBot — Telegram Bot para gestión de descargas con Plex

Bot de Telegram para buscar, descargar y gestionar películas y series en un servidor Linux personal con qBittorrent y Plex.

---

## ✨ Funciones principales

- 🎬 Buscar y descargar **películas** desde YTS
- 📺 Buscar y descargar **series** (episodios o temporadas completas) via Jackett
- 🔍 Buscar en tu biblioteca local
- 🕐 Ver últimas descargas por categoría
- 🗑 Borrar películas/series con doble confirmación
- 📊 Status de descargas activas en qBittorrent
- ❌ Cancelar descargas
- ⚠️ Ver torrents atascados
- 👥 Sistema multiusuario (solo el admin puede agregar usuarios)
- 🔔 Notificación cuando termina una descarga
- 📋 Menú contextual con teclado adaptativo

---

## 📋 Requisitos

### Sistema
- Ubuntu 20.04+ (o cualquier Linux con systemd)
- Python 3.10+
- [qBittorrent](https://www.qbittorrent.org/) con Web UI habilitada
- [Jackett](https://github.com/Jackett/Jackett) (para búsqueda de series)
- [Plex Media Server](https://www.plex.tv/) (opcional)

### Cuentas / API Keys necesarias
- **Bot de Telegram**: crear con [@BotFather](https://t.me/BotFather)
- **OMDB API Key** (gratuita): [omdbapi.com/apikey.aspx](http://www.omdbapi.com/apikey.aspx)

---

## 🚀 Instalación rápida

```bash
git clone https://github.com/TU_USUARIO/cinebot.git
cd cinebot
chmod +x install.sh
./install.sh
```

El instalador guiará el proceso completo.

---

## 🛠 Instalación manual

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/cinebot.git
cd cinebot
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Configurar el bot

Copia y edita el archivo de configuración:

```bash
cp config.example.py config.py
nano config.py
```

Rellena todos los valores (ver sección [Configuración](#configuración) abajo).

### 4. Instalar como servicio

```bash
sudo cp cine_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cine_bot
sudo systemctl start cine_bot
```

### 5. Verificar que corre

```bash
sudo systemctl status cine_bot
journalctl -u cine_bot -f
```

---

## ⚙️ Configuración

Edita `config.py`:

```python
# Telegram
TELEGRAM_TOKEN   = "TOKEN_DE_BOTFATHER"
ALLOWED_USER_ID  = 123456789        # Tu Telegram ID numérico

# qBittorrent Web UI
QB_HOST          = "localhost"
QB_PORT          = 8080
QB_USER          = "admin"
QB_PASS          = "tu_contraseña"

# OMDB (para posters e info de películas)
OMDB_KEY         = "tu_api_key"

# Jackett (para series)
JACKETT_URL      = "http://localhost:9117/api/v2.0/indexers/all/results"
JACKETT_KEY      = "tu_jackett_api_key"

# Carpetas de descarga
MOVIE_FOLDERS    = ["/ruta/a/Películas", "/ruta/a/Niños"]
SERIES_FOLDERS   = ["/ruta/a/Series", "/ruta/a/SeriesNiños"]
```

### Obtener tu Telegram ID

Escríbele a [@userinfobot](https://t.me/userinfobot) en Telegram. Te responde con tu ID numérico.

---

## 👥 Gestión de usuarios

Solo el administrador (definido por `ALLOWED_USER_ID` en `config.py`) puede agregar usuarios.

**Para agregar un usuario:**
1. Abre el bot en Telegram
2. Escribe `menú`
3. Elige opción **9. 👥 Agregar usuario**
4. Manda el Telegram ID numérico del nuevo usuario

Los IDs adicionales se guardan en `/opt/cine_bot/allowed_users.txt`.

**Para obtener el ID de alguien:**
Pídele que le escriba a [@userinfobot](https://t.me/userinfobot) — le responde con su ID.

---

## 📱 Uso

Escribe cualquiera de estas palabras para abrir el menú:
`menú` · `menu` · `opciones` · `inicio` · `ayuda`

O escribe directamente el título de una película o serie.

### Buscar una película
```
Inception
→ 1. Película
→ [selecciona de la lista]
→ [selecciona calidad]
→ [confirma]
→ 🚀 ¡Descarga iniciada!
```

### Buscar una serie
```
Breaking Bad
→ 2. Serie
→ [info + poster de la serie]
→ 1. Episodio / 2. Temporada / 3. General / 4. Info detallada
→ S03E07 (si elegiste episodio)
→ [selecciona torrent]
→ [confirma]
```

---

## 📁 Estructura del proyecto

```
cinebot/
├── bot.py              # Lógica principal del bot
├── config.py           # Configuración (NO subir a GitHub)
├── config.example.py   # Plantilla de configuración
├── requirements.txt    # Dependencias Python
├── cine_bot.service    # Servicio systemd
├── install.sh          # Instalador automático (Linux)
├── install_mac.sh      # Instalador para macOS
├── install_windows.ps1 # Instalador para Windows
└── README.md
```

---

## 🔧 Dependencias externas

| Herramienta | Para qué | Instalación |
|---|---|---|
| qBittorrent | Gestor de torrents | `sudo apt install qbittorrent-nox` |
| Jackett | Búsqueda de series | [github.com/Jackett/Jackett](https://github.com/Jackett/Jackett) |
| Plex | Reproductor (opcional) | [plex.tv](https://www.plex.tv) |

---

## 🆘 Solución de problemas

**El bot no responde**
```bash
sudo systemctl status cine_bot
journalctl -u cine_bot -n 20
```

**Error de conexión con qBittorrent**
- Verifica que la Web UI esté habilitada: Herramientas → Preferencias → Web UI
- Confirma usuario/contraseña en `config.py`

**No encuentra series**
- Verifica que Jackett esté corriendo: `http://localhost:9117`
- Agrega indexers en la interfaz web de Jackett

---

## 📄 Licencia

MIT — úsalo como quieras.

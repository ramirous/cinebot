# ─────────────────────────────────────────────────────────────────
# install_windows.ps1 — Instalador de CineBot para Windows
# Ejecutar en PowerShell como Administrador:
#   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#   .\install_windows.ps1
# ─────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

function Ask($prompt, $default = "") {
    $full = if ($default) { "$prompt [$default]" } else { $prompt }
    $val = Read-Host "→ $full"
    if (-not $val -and $default) { return $default }
    return $val
}

Write-Host ""
Write-Host "🎬  CineBot — Instalador Windows" -ForegroundColor Cyan
Write-Host "────────────────────────────────────────"
Write-Host ""

# ── Python ────────────────────────────────────────────────────────
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "✗ Python no encontrado. Instálalo desde https://python.org" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python encontrado" -ForegroundColor Green

# ── Directorio ────────────────────────────────────────────────────
$defaultDir = "$env:USERPROFILE\cine_bot"
$installDir = Ask "¿Dónde instalar?" $defaultDir

New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item -Recurse -Force ".\*" $installDir
Set-Location $installDir
Write-Host "✓ Archivos copiados a $installDir" -ForegroundColor Green

# ── Entorno virtual ───────────────────────────────────────────────
python -m venv venv
.\venv\Scripts\pip install --quiet --upgrade pip
.\venv\Scripts\pip install --quiet -r requirements.txt
Write-Host "✓ Dependencias instaladas" -ForegroundColor Green

# ── Configuración ─────────────────────────────────────────────────
Write-Host ""
Write-Host "────────────────────────────────────────"
Write-Host "  Configuración del bot"
Write-Host "────────────────────────────────────────"
Write-Host ""

$tgToken    = Ask "Token de Telegram (de @BotFather)"
$tgId       = Ask "Tu Telegram ID numérico (de @userinfobot)"
$qbUser     = Ask "Usuario qBittorrent Web UI" "admin"
$qbPass     = Ask "Contraseña qBittorrent Web UI"
$omdbKey    = Ask "OMDB API Key (omdbapi.com/apikey.aspx) [vacío para omitir]"
$jackettKey = Ask "Jackett API Key [vacío para omitir]"

Write-Host ""
Write-Host "── Carpetas de tu biblioteca ────────────────" -ForegroundColor Yellow
$folderMovies     = Ask "Carpeta de Películas (ej: D:\Películas)"
$folderKids       = Ask "Carpeta de Películas Niños [vacío para omitir]"
$folderSeries     = Ask "Carpeta de Series (ej: D:\Series)"
$folderSeriesKids = Ask "Carpeta de Series Niños [vacío para omitir]"

# Build folder lists
$movieFolders  = "`"$folderMovies`""
if ($folderKids)       { $movieFolders  += ", `"$folderKids`"" }
$seriesFolders = "`"$folderSeries`""
if ($folderSeriesKids) { $seriesFolders += ", `"$folderSeriesKids`"" }

# ── Escribir config.py ────────────────────────────────────────────
$config = @"
TELEGRAM_TOKEN   = "$tgToken"
ALLOWED_USER_ID  = $tgId
QB_HOST          = "localhost"
QB_PORT          = 8080
QB_USER          = "$qbUser"
QB_PASS          = "$qbPass"
OMDB_KEY         = "$omdbKey"
JACKETT_URL      = "http://localhost:9117/api/v2.0/indexers/all/results"
JACKETT_KEY      = "$jackettKey"
"@
$config | Out-File -FilePath "$installDir\config.py" -Encoding UTF8
Write-Host "✓ config.py creado" -ForegroundColor Green

# ── Script de inicio ──────────────────────────────────────────────
$startScript = @"
@echo off
cd /d "$installDir"
venv\Scripts\python bot.py
pause
"@
$startScript | Out-File -FilePath "$installDir\start_bot.bat" -Encoding ASCII

Write-Host ""
Write-Host "────────────────────────────────────────"
Write-Host "✓ ¡Instalación completada!" -ForegroundColor Green
Write-Host ""
Write-Host "  Para iniciar el bot, ejecuta: start_bot.bat"
Write-Host "  O desde PowerShell:"
Write-Host "  cd $installDir; .\venv\Scripts\python bot.py"
Write-Host ""
Write-Host "⚠ Recuerda:" -ForegroundColor Yellow
Write-Host "  - Habilitar Web UI en qBittorrent"
Write-Host "  - Agregar indexers en Jackett: http://localhost:9117"
Write-Host ""

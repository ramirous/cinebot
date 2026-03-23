#!/bin/bash
# actualizar_github.sh — Sube los cambios del bot a GitHub

cd /opt/cine_bot

echo "📦 Estado del repositorio:"
git status --short

echo ""
read -p "📝 Mensaje del commit (Enter = 'Actualización bot'): " MSG
MSG="${MSG:-Actualización bot}"

# Agregar todos los archivos relevantes (existentes y nuevos)
git add bot.py config.example.py requirements.txt merge_lat.py \
        install.sh install_en.sh install_windows.ps1 \
        actualizar_github.sh README.md cine_bot.service .gitignore 2>/dev/null

git commit -m "$MSG" || echo "⚠ Sin cambios nuevos que commitear."
git push origin master

echo ""
echo "✅ Subido a GitHub correctamente."

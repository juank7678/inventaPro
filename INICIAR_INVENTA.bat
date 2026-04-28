@echo off
title Inventa — Business Intelligence
color 0B
chcp 65001 > nul
echo.
echo  ╔══════════════════════════════════════╗
echo  ║        INVENTA — Iniciando...        ║
echo  ║   Business Intelligence para PYMEs  ║
echo  ╚══════════════════════════════════════╝
echo.
echo  [1/2] Iniciando servidor Flask...
echo  [2/2] Abre tu navegador en:
echo.
echo       http://localhost:5000
echo.
echo  Para cerrar la app: presiona CTRL+C
echo  ─────────────────────────────────────
echo.

cd /d "%~dp0"

:: Verificar si Python está instalado
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH
    echo Instala Python desde https://python.org
    pause
    exit /b 1
)

:: Verificar si las dependencias están instaladas
python -c "import flask" > nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando dependencias...
    pip install -r requirements.txt
)

:: Iniciar la aplicación
python app.py

:: Si el servidor se cierra, mostrar mensaje
echo.
echo [INFO] Servidor detenido
timeout /t 3 > nul
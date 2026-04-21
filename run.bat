@echo off
:: Launcher for WebGap.exe - runs the built app.
:: If you haven't built yet, run install.bat first.

setlocal

if not exist "dist\WebGap.exe" (
    echo.
    echo  WebGap.exe not found in  dist\
    echo.
    echo  It looks like you haven't built the app yet.
    echo  Run  install.bat  first.
    echo.
    pause
    exit /b 1
)

if not exist "dist\.env" (
    echo.
    echo  Warning: dist\.env is missing. The app needs API keys.
    echo  Copy .env.example to dist\.env and fill in your keys.
    echo.
    pause
)

start "" "dist\WebGap.exe"
endlocal

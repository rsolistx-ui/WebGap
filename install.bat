@echo off
setlocal EnableDelayedExpansion

title WebGap / BizFinder - One-Click Installer

echo ============================================================
echo   WebGap / BizFinder  -  One-Click Installer
echo ============================================================
echo.
echo  This script will:
echo    1. Verify Python 3.11 is installed
echo    2. Install all Python dependencies
echo    3. Build WebGap.exe  (single-file Windows executable)
echo    4. Prepare a .env config file next to the exe
echo    5. Offer to place a shortcut on your Desktop
echo.
echo ============================================================
echo.
pause

:: ────────────────────────────────────────────────────────────
:: Step 1 of 4: Python check
:: ────────────────────────────────────────────────────────────
echo.
echo [1/4] Checking for Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python 3.11 is not installed.
    echo.
    echo  Download it from:  https://www.python.org/downloads/release/python-3119/
    echo  During install, make sure to check "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('py -3.11 --version') do echo    Found: %%v

:: ────────────────────────────────────────────────────────────
:: Step 2 of 4: Dependencies
:: ────────────────────────────────────────────────────────────
echo.
echo [2/4] Installing Python dependencies (this may take a minute)...
py -3.11 -m pip install --upgrade pip --quiet
if errorlevel 1 goto :pip_fail

py -3.11 -m pip install -r requirements.txt --quiet
if errorlevel 1 goto :pip_fail

py -3.11 -m pip install "pywebview>=4.0" "pyinstaller>=6.0" --quiet
if errorlevel 1 goto :pip_fail
echo    Dependencies ready.
goto :build

:pip_fail
echo.
echo  ERROR: pip failed to install dependencies.
echo  Check your internet connection and try again.
echo.
pause
exit /b 1

:: ────────────────────────────────────────────────────────────
:: Step 3 of 4: Build
:: ────────────────────────────────────────────────────────────
:build
echo.
echo [3/4] Building WebGap.exe...
py -3.11 -m PyInstaller BizFinder.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo  ERROR: PyInstaller build failed. Scroll up for details.
    echo.
    pause
    exit /b 1
)

if not exist "dist\WebGap.exe" (
    echo.
    echo  ERROR: Build completed but dist\WebGap.exe is missing.
    echo.
    pause
    exit /b 1
)
echo    Built: dist\WebGap.exe

:: ────────────────────────────────────────────────────────────
:: Step 4 of 4: .env setup
:: ────────────────────────────────────────────────────────────
echo.
echo [4/4] Preparing config file...
if exist "dist\.env" (
    echo    dist\.env already exists - leaving it alone.
) else if exist ".env" (
    copy /y ".env" "dist\.env" >nul
    echo    Copied your existing .env into dist\.
) else if exist ".env.example" (
    copy /y ".env.example" "dist\.env" >nul
    echo    Created dist\.env from the template.
    echo    ^!^! Open dist\.env and paste your API keys before running.
) else (
    echo    Warning: no .env.example found - you'll need to create dist\.env manually.
)

:: ────────────────────────────────────────────────────────────
:: Desktop shortcut (optional)
:: ────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  Install complete.
echo ============================================================
echo.
set /p MAKE_SC="Create a Desktop shortcut to WebGap? (y/n): "
if /i not "%MAKE_SC%"=="y" goto :done

set "EXE_PATH=%CD%\dist\WebGap.exe"
set "ICON_PATH=%CD%\webgap.ico"
set "SHORTCUT=%USERPROFILE%\Desktop\WebGap.lnk"

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%'); ^
   $s.TargetPath = '%EXE_PATH%'; ^
   $s.WorkingDirectory = '%CD%\dist'; ^
   $s.IconLocation = '%ICON_PATH%'; ^
   $s.Description = 'WebGap / BizFinder'; ^
   $s.Save()"

if exist "%SHORTCUT%" (
    echo    Shortcut created at: %SHORTCUT%
) else (
    echo    Could not create shortcut. You can manually run dist\WebGap.exe
)

:done
echo.
echo ============================================================
echo  Next steps:
echo    1. Open  dist\.env  and paste your API keys.
echo    2. Launch the app from your Desktop shortcut
echo       (or double-click  dist\WebGap.exe  directly).
echo ============================================================
echo.
set /p OPEN_DIST="Open the dist folder now? (y/n): "
if /i "%OPEN_DIST%"=="y" explorer dist

endlocal
pause

@echo off
setlocal

echo ============================================================
echo  WebGap: Windows Build Script
echo ============================================================
echo.

:: Check Python is available
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11 not found. Install from python.org
    pause & exit /b 1
)

echo [1/3] Installing / updating dependencies...
py -3.11 -m pip install --upgrade pip --quiet
py -3.11 -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install requirements.txt dependencies.
    pause & exit /b 1
)

py -3.11 -m pip install "pywebview>=4.0" "pyinstaller>=6.0" --quiet
if errorlevel 1 (
    echo ERROR: Failed to install pywebview / pyinstaller.
    pause & exit /b 1
)

echo [2/3] Building WebGap.exe...
py -3.11 -m PyInstaller BizFinder.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. See output above.
    pause & exit /b 1
)

echo [3/3] Build complete!
echo.
echo  Output:  dist\WebGap.exe
echo.

:: Seed dist\.env so the freshly built exe can find a config file
if not exist "dist\.env" (
    if exist ".env" (
        copy /y ".env" "dist\.env" >nul
        echo  Copied your .env into dist\
    ) else if exist ".env.example" (
        copy /y ".env.example" "dist\.env" >nul
        echo  Created dist\.env from .env.example - fill in your keys before running.
    )
)

echo.
echo ============================================================
echo  BEFORE RUNNING:
echo  Open  dist\.env  and add your API keys:
echo.
echo    GOOGLE_API_KEY=your_key_here       (required)
echo    ANTHROPIC_API_KEY=your_key_here    (required for AI features)
echo    YELP_API_KEY=your_key_here         (optional)
echo    STRIPE_SECRET_KEY=your_key_here    (optional)
echo ============================================================
echo.

:: Offer to open the dist folder
set /p OPEN="Open dist folder now? (y/n): "
if /i "%OPEN%"=="y" explorer dist

endlocal
pause

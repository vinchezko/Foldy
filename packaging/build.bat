@echo off
setlocal
title Building Foldy
cd /d "%~dp0.."
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

echo [1/4] Installing build dependencies...
%PY% -m pip install --upgrade -r requirements.txt || goto :fail
%PY% -c "import PyQt6, win32com.shell" || goto :fail

echo [2/4] Building the tiny launcher (fast start for pinned buttons)...
taskkill /f /im Foldy.exe >nul 2>nul
rmdir /s /q dist 2>nul
rmdir /s /q build 2>nul
mkdir build
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyi-fsl packaging\fsl.spec || goto :fail
%PY% packaging\pack_launcher.py || goto :fail

echo [3/4] Compiling the single-file Foldy.exe...
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyi-foldy packaging\foldy.spec || goto :fail
if not exist dist\Foldy.exe goto :fail
rmdir /s /q dist\fsl 2>nul

echo [4/4] Done:  %CD%\dist\Foldy.exe
if /i not "%~1"=="ci" (
    start "" dist\Foldy.exe
    pause
)
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
if /i not "%~1"=="ci" pause
exit /b 1

@echo off
rem Construit DeepSeekStatus.exe (un fichier, sans console) dans dist\
cd /d "%~dp0.."
venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --noconsole --onefile ^
  --name DeepSeekStatus --icon assets\whale.ico ^
  --add-data "web;web" --add-data "assets;assets" ^
  --collect-all webview ^
  --hidden-import pystray._win32 ^
  app.py
echo.
echo Executable : %CD%\dist\DeepSeekStatus.exe
pause

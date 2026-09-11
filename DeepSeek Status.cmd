@echo off
rem Lance DeepSeek Status (exe empaqueté si présent, sinon sources)
if exist "%~dp0dist\DeepSeekStatus.exe" (
  start "" "%~dp0dist\DeepSeekStatus.exe"
) else (
  start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0app.py"
)

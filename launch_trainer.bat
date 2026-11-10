@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0doa6lr_trainer.py"
) else (
  python "%~dp0doa6lr_trainer.py"
  if errorlevel 1 pause
)

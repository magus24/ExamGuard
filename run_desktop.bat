@echo off
setlocal
cd /d "%~dp0"

if exist "Тестировщик.exe" (
    start "" "Тестировщик.exe"
) else if exist "Backend\dist\Тестировщик.exe" (
    start "" "Backend\dist\Тестировщик.exe"
) else (
    echo [INFO] Running ExamGuard from Python source...
    python Frontend\desktop_app.py
)

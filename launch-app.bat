@echo off
rem Side-by-side "app" layout: Claude Code left, narrator panel right.
rem Double-click this, or make a desktop shortcut to it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-app.ps1" %*
if errorlevel 1 pause

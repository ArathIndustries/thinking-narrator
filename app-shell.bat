@echo off
rem Single-window app: Windows Terminal (running claude) + narrator, one frame.
rem Double-click this, or make a desktop shortcut to it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app-shell.ps1" %*
if errorlevel 1 pause

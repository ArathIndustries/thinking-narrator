@echo off
rem Nest the Windows Terminal window you are in alongside the narrator.
rem Close the frame to get the plain terminal back. A toggle, not a mode.
rem
rem   narrate                  nest this terminal + narrator
rem   narrate -NewTerminal     open a fresh terminal instead
rem   narrate -PanelPercent 40 wider narrator column
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app-shell.ps1" %*

@echo off
rem Lance l'application sous Windows :  lancer.bat  [--port 9000]  [--sans-navigateur]
rem Données dans %APPDATA%\roadmap-bancs ; autre dossier : set ROADMAP_DATA=C:\chemin  avant de lancer
cd /d "%~dp0"
if not defined ROADMAP_DATA set "ROADMAP_DATA=%APPDATA%\roadmap-bancs"
rem UTF-8 partout : sinon la sortie de git (accents) est lue en cp1252
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% main.py %*
if errorlevel 1 pause

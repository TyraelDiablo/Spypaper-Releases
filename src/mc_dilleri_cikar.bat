@echo off
cd /d "%~dp0"
uv run python tools\mc_lang_cikar.py %*
pause

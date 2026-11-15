@echo off
cd /d "%~dp0"
uv run --with nbtlib --with pyside6 --with psutil --with pyyaml --with segno python main.py

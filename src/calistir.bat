@echo off
cd /d "%~dp0"
uv run --python 3.12 --with nbtlib --with pyside6 --with psutil --with pyyaml --with segno --with soundfile python main.py

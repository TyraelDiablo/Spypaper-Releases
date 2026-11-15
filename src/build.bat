@echo off
cd /d "%~dp0"
uv run --with pyinstaller --with nbtlib --with pyside6 --with psutil --with pyyaml --with segno pyinstaller --noconsole --onefile --collect-all nbtlib --name Spypaper --add-data "locales;locales" --add-data "legal;legal" --add-data "ui/icons;ui/icons" --add-data "ui/assets;ui/assets" --add-data "remote_web;remote_web" --icon "ui/assets/spypaper.ico" ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts ^
  main.py
echo.
echo Bitti: dist\Spypaper.exe  (config.json, Translation ve Icons ilk kullanimda exenin yaninda olusur)
pause

@echo off
cd /d "%~dp0"

rem Spypaper acikken Windows exe dosyasini kilitler ve yeni exe yazilamaz.
tasklist /fi "imagename eq Spypaper.exe" 2>nul | find /i "Spypaper.exe" >nul
if not errorlevel 1 (
  echo.
  echo HATA: Spypaper su an acik. Once Spypaper'i tamamen kapatin
  echo ^(gorev cubugunda ya da Gorev Yoneticisi'nde Spypaper.exe kalmasin^), sonra tekrar calistirin.
  echo.
  pause
  exit /b 1
)

uv run --python 3.12 --with pyinstaller --with nbtlib --with pyside6 --with psutil --with pyyaml --with segno --with soundfile pyinstaller --clean -y --noconsole --onefile --collect-all nbtlib --collect-all _soundfile_data --collect-binaries numpy --collect-submodules numpy._core --hidden-import numpy._core._multiarray_umath --name Spypaper --add-data "locales;locales" --add-data "legal;legal" --add-data "ui/icons;ui/icons" --add-data "ui/assets;ui/assets" --add-data "remote_web;remote_web" --icon "ui/assets/spypaper.ico" ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts ^
  main.py
if errorlevel 1 (
  echo.
  echo DERLEME BASARISIZ. Yukaridaki son hata satirlarina bakin; exe guncellenmedi.
  echo.
  pause
  exit /b 1
)

echo.
echo Bitti: %~dp0dist\Spypaper.exe
for %%F in ("dist\Spypaper.exe") do echo Olusturulma: %%~tF  Boyut: %%~zF bayt
echo (config.json, Translation ve Icons exenin yaninda durur; eski dist klasorunden kopyalayin.)
pause

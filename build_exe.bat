@echo off
title Build FR Asset Converter EXE
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo Installing PyInstaller...
python -m pip install pyinstaller -q
if errorlevel 1 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo Building standalone EXE...
python -m PyInstaller --onefile --name "FR_Asset_Converter" --add-data "templates;templates" --add-data "models;models" --add-data "ASSET_FORMATS.md;." --hidden-import numpy --hidden-import trimesh --hidden-import pygltflib --hidden-import tkinter --noconsole fr_asset_gui.py

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Built: dist\FR_Asset_Converter.exe
pause

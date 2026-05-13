@echo off
echo Building Hudl Video Downloader...
echo.

:: Install dependencies
pip install pyinstaller requests

:: Build CLI+GUI single exe
pyinstaller build.spec --clean

echo.
echo Build complete! Check dist\HudlDownloader.exe
pause

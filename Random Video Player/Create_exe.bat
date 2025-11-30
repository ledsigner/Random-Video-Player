@echo off
cd /d "%~dp0"

pyinstaller --onefile --noconsole ^
    --icon="RVP.ico" ^
    --add-data "icons;icons" ^
    --add-data "styles.qss;." ^
    "Random_Video_Player.py"

copy ".\dist\Random_Video_Player.exe" "%USERPROFILE%\Desktop\Random_Video_Player.exe"

pause
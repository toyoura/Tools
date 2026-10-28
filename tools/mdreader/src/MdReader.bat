@echo off
rem MdReader - drop a .md file onto this file to read it aloud.
rem Double-click with no file to open the file picker.
chcp 65001 >nul
setlocal
python "%~dp0launcher.py" %*
if errorlevel 1 (
  echo.
  pause
)
endlocal

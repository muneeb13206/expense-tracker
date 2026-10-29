@echo off
title Upload to GitHub
color 0a

echo ========================================
echo   GitHub Auto-Uploader
echo ========================================

:: Navigate to the folder where the script is located
cd /d "%~dp0"

:: Check if git is initialized
if not exist ".git" (
    echo [ERROR] Git is not initialized in this folder!
    pause
    exit
)

:: Ask the user for a commit message/project description
echo.
set /p "commitMsg=Enter your commit message (or press Enter for default): "

:: If the user left it blank, use a default timestamp message
if "%commitMsg%"=="" (
    for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
    set "YY=%dt:~2,2%" & set "YYYY=%dt:~0,4%" & set "MM=%dt:~4,2%" & set "DD=%dt:~6,2%"
    set "HH=%dt:~8,2%" & set "Min=%dt:~10,2%" & set "Sec=%dt:~12,2%"
    set "commitMsg=Update on %YYYY%-%MM%-%DD% %HH%:%Min%:%Sec%"
)

:: Stage all changes
echo.
echo [1/3] Staging files...
git add .

:: Commit with your custom message
echo [2/3] Committing changes...
git commit -m "%commitMsg%"

:: Push to GitHub
echo [3/3] Pushing to GitHub...
git push origin main

echo ========================================
echo   Upload complete!
echo ========================================
pause
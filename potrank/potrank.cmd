@echo off
REM potrank launcher for a Windows PC user.
REM Lets SM fire an immediate potrank2.csv refresh over SSH without waiting for the :25 cron
REM tick. Model: ~/potentials/strategy_grp2/app/report/strategy_grp2.cmd
REM Loops back to the menu after each run so the window stays open for the next choice.

setlocal

:menu
set "CHOICE="
echo.
echo   potrank
echo   1) refresh now         (build + publish potrank2.csv -- the same run cron fires)
echo   2) build only          (write app/output/potrank2.csv, do not publish)
echo   3) check inputs        (preflight table: vintage, ages, row counts)
echo   4) explorer            (open this folder)
echo   0) quit
echo.
set /p CHOICE="Choose 0-4: "

if "%CHOICE%"=="0" goto end
if "%CHOICE%"=="1" goto refresh
if "%CHOICE%"=="2" goto build
if "%CHOICE%"=="3" goto check
if "%CHOICE%"=="4" goto explorer

echo   not a valid choice: %CHOICE%
goto menu

:refresh
REM Deliberately the SAME script cron runs -- see run_potrank.sh's own flock guard for what
REM keeps this safe if it lands close to the :25 tick.
ssh -t -p 2222 sm@innovia.dk "bash -lc '~/potentials/potrank/run_potrank.sh'"
goto held

:build
ssh -t -p 2222 sm@innovia.dk "bash -lc 'source /home/sm/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env && cd ~/potentials/potrank/app/code && python3 -u potrank.py'"
goto held

:check
ssh -t -p 2222 sm@innovia.dk "bash -lc 'source /home/sm/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env && cd ~/potentials/potrank/app/code && python3 -u preflight.py'"
goto held

:explorer
REM %~dp0 is this batch file's own folder -- whatever drive letter or UNC path it was
REM launched from, so nothing here is a hardcoded path.
start "" explorer.exe "%~dp0"
goto menu

:held
REM Hold the window on any non-zero exit, so an error is read rather than scrolled away by
REM the menu redrawing underneath it.
if errorlevel 1 (
  echo.
  echo   *** stopped - read the message above before continuing ***
  pause
)
goto menu

:end

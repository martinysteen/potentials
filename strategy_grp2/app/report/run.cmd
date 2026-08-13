@echo off
REM strategy_grp2 launcher for a Windows PC user.
REM Opens the control board (if not already open) and lets you fire a conductor.py mode over SSH.
REM Loops back to the menu after each run so the window stays open for the next choice.

setlocal

if "%1"=="" goto menu
set MODE=%1
goto run

:menu
set "CHOICE="
set "MODE="
echo.
echo   strategy_grp2
echo   1) development tick   (steps 0-4, writes compare_strategies_*.xlsx)
echo   2) production         (steps 0-2, writes StrategicStocks.xlsx)
echo   3) dry-run             (parse/validate active rows only)
echo   4) check               (step 0 only: universe/groups/data table)
echo   5) make-board          (refresh control_board.xlsx from the schema)
echo   0) quit
echo.
set /p CHOICE="Choose 0-5: "

if "%CHOICE%"=="0" goto end
if "%CHOICE%"=="1" set MODE=
if "%CHOICE%"=="2" set MODE=--production
if "%CHOICE%"=="3" set MODE=--dry-run
if "%CHOICE%"=="4" set MODE=--check
if "%CHOICE%"=="5" set MODE=--make-board

if "%CHOICE%"=="" goto menu
if "%CHOICE%"=="0" goto end
if "%CHOICE%"=="1" goto run
if "%CHOICE%"=="2" goto run
if "%CHOICE%"=="3" goto run
if "%CHOICE%"=="4" goto run
if "%CHOICE%"=="5" goto run
echo   not a valid choice: %CHOICE%
goto menu

:run
ssh -t -p 2222 sm@innovia.dk "bash -lc 'source /home/sm/miniconda3/etc/profile.d/conda.sh && conda activate potsystem_env && cd ~/potentials/strategy_grp2/app/code && python -u conductor.py %MODE%'"
REM Hold the window on any non-zero exit, so a stop (exit 2 = board still open in Excel)
REM is read rather than scrolled away by the menu redrawing underneath it.
if errorlevel 1 (
  echo.
  echo   *** stopped - read the message above before continuing ***
  pause
)
if "%1"=="" goto menu
goto end

:end


@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3.13 -m linkedin_agent web) || (python -m linkedin_agent web)
pause

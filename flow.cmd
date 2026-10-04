@echo off
rem Start Flow ITR and open it in the browser. Needs Python 3.10 or later; nothing to install.
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m server %* & goto :eof)
where python >nul 2>nul && (python -m server %* & goto :eof)
echo Python was not found. Install Python 3.10 or later from https://www.python.org/downloads/ and run this again.
pause

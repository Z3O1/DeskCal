@echo off
rem Starts the widget. If it is already running, the open window is brought to the front.
rem The embedded-core source preview bundles Windows x64 Python 3.14 dependencies.
rem Prefer that interpreter when available; other versions need requirements-anki.txt.
where pyw >nul 2>nul && (py -3.14 -V >nul 2>nul && (start "" pyw -3.14 "%~dp0deskcal.py" & exit /b))
rem Tries the py launcher next: python.org installs it by default, even without PATH.
where pyw >nul 2>nul && (start "" pyw -3 "%~dp0deskcal.py" & exit /b)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0deskcal.py" & exit /b)
echo Python 3 was not found. Install it from https://www.python.org/downloads/windows/
echo and run DeskCal.bat again.
pause

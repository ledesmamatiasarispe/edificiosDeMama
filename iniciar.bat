@echo off
rem Windows: doble clic para arrancar Edificios de Mamá (todo el trabajo lo hace iniciar.py).
rem Cerrar esta ventana apaga la app.
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (py -3 iniciar.py %* & goto fin)
where python >nul 2>nul && (python iniciar.py %* & goto fin)
echo Hace falta Python 3. Se baja gratis de https://www.python.org/downloads/
echo Al instalarlo, marcar la opcion "Add python.exe to PATH".
pause
:fin

@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)

if not exist ".venv\\Scripts\\python.exe" (
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto :fail
)

call ".venv\\Scripts\\activate.bat"
if errorlevel 1 goto :fail

if not exist ".venv\\.medtutor_installed" (
  python -m pip install --upgrade pip
  if errorlevel 1 goto :fail
  python -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  type nul > ".venv\\.medtutor_installed"
)

python -m streamlit run app.py
goto :end

:fail
echo 실행 준비 중 오류가 발생했습니다. Python 설치 상태를 확인해주세요.
pause

:end
endlocal

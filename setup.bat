@echo off
echo ============================================
echo   Mold Analyzer - Setup
echo ============================================

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python이 설치되어 있지 않습니다.
    echo         https://www.python.org/downloads/ 에서 설치하세요.
    pause
    exit /b 1
)

:: conda 확인
conda --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] conda가 없습니다. pip로 설치를 시도합니다...
    echo [INFO] pythonocc-core는 conda로 설치하는 것을 권장합니다.
    echo.
    echo   conda 설치 방법:
    echo     conda install -c conda-forge pythonocc-core numpy
    echo.
    echo   pip 설치 시도 중...
    pip install cadquery numpy
) else (
    echo [INFO] conda로 pythonocc-core를 설치합니다...
    conda install -c conda-forge pythonocc-core numpy -y
)

echo.
echo ============================================
echo   설치 완료! 사용법:
echo     python analyze.py your_part.step
echo ============================================
pause

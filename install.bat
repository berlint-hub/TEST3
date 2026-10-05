@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title TexUp - install

echo ============================================================
echo  TexUp installer  (PyTorch CUDA + spandrel + GUI)
echo ============================================================
echo.

:: ---------------------------------------------------------------- Python
set "PY="
for %%V in (3.12 3.11 3.13) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; assert sys.version_info[:2] in ((3,11),(3,12),(3,13))" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3.11 / 3.12 / 3.13 not found.
    echo         Install it from https://www.python.org/downloads/windows/  (tick "Add python.exe to PATH" and "py launcher")
    pause & exit /b 1
)
echo Using: %PY%
%PY% -c "import sys; print('Python', sys.version.split()[0])"

:: ---------------------------------------------------------------- venv
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    %PY% -m venv .venv || (echo [ERROR] venv creation failed & pause & exit /b 1)
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip wheel >nul

:: ---------------------------------------------------------------- pick CUDA wheel index
:: Override with:  set TEXUP_CUDA=cu128   (before running install.bat)
set "CUDA_TAG=%TEXUP_CUDA%"
if not defined CUDA_TAG (
    set "DRIVER_CUDA="
    for /f "tokens=9 delims= " %%A in ('nvidia-smi 2^>nul ^| findstr /C:"CUDA Version"') do set "DRIVER_CUDA=%%A"
    if defined DRIVER_CUDA (
        echo NVIDIA driver supports CUDA !DRIVER_CUDA!
        for /f "tokens=1 delims=." %%M in ("!DRIVER_CUDA!") do set "CUDA_MAJOR=%%M"
        if !CUDA_MAJOR! GEQ 13 (set "CUDA_TAG=cu130") else (set "CUDA_TAG=cu128")
    ) else (
        echo [WARN] nvidia-smi not found - is the NVIDIA driver installed? Falling back to cu128.
        set "CUDA_TAG=cu128"
    )
)
echo Installing PyTorch (%CUDA_TAG%) - this downloads ~3 GB, be patient ...
"%VPY%" -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_TAG%
if errorlevel 1 (
    if /i "%CUDA_TAG%"=="cu130" (
        echo [WARN] cu130 install failed, retrying with cu128 ...
        set "CUDA_TAG=cu128"
        "%VPY%" -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128 || goto :torch_fail
    ) else (
        goto :torch_fail
    )
)

:: ---------------------------------------------------------------- the rest
echo Installing TexUp dependencies ...
"%VPY%" -m pip install --upgrade -r requirements.txt || (echo [ERROR] pip install failed & pause & exit /b 1)

if not exist "models" mkdir models

echo.
echo ---------------------------------------------------------------- check
"%VPY%" -c "import torch; ok=torch.cuda.is_available(); print('torch', torch.__version__, '| CUDA available:', ok); print('GPU:', torch.cuda.get_device_name(0) if ok else '-- none --')"
"%VPY%" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" || (
    echo.
    echo [WARN] CUDA is NOT available to PyTorch. Update your NVIDIA driver (GeForce Experience / nvidia.com^)
    echo        or rerun with:   set TEXUP_CUDA=cu126 ^&^& install.bat
)
echo.
echo Done. Put your ESRGAN .pth models into the "models" folder and run TexUp.bat
pause
exit /b 0

:torch_fail
echo [ERROR] PyTorch installation failed. Check your internet connection or set TEXUP_CUDA manually.
pause
exit /b 1

@echo off
:: 移除 chcp 65001，因为纯英文不需要更改代码页
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo =======================================================
echo Robot Arm Algorithm Visualization and Evaluation Platform
echo =======================================================
echo.

:: Check if the directory exists
if not exist "backend\algorithms" (
    echo [ERROR] Cannot find backend\algorithms directory! Please run this script from the project root.
    pause
    exit /b 1
)

echo [1/2] Checking and building algorithm environment images...
echo.
cd backend\algorithms

:: Loop through directories and build images
for /d %%D in (*) do (
    if exist "%%D\Dockerfile.algo" (
        echo --- Found algorithm directory: %%D ---
        docker build -t algo_%%D -f "%%D\Dockerfile.algo" .
        
        if !ERRORLEVEL! neq 0 (
            echo [ERROR] Failed to build algo_%%D! Please check if Docker is running.
            pause
            exit /b !ERRORLEVEL!
        )
        echo.
    )
)

:: Return to root directory
cd ..\..

:: Ensure docker compose gets the project path when launched by double-click
set "PWD=%CD%"

echo [2/2] Algorithm images built successfully. Starting main services...
echo.

:: Try new docker compose, fallback to old docker-compose if it fails
docker compose up --build -d || docker-compose up --build -d

echo.
echo =======================================================
echo Services started successfully in the background!
echo Opening your browser...
echo =======================================================

:: Wait for 3 seconds to ensure the frontend service is fully up
timeout /t 3 /nobreak > nul

:: Open the webpage
start http://localhost:8501

pause
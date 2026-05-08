@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo =======================================================
echo RoboStudio
echo =======================================================
echo.

:: Check if the directory exists
if not exist "backend\algorithms" (
    echo [ERROR] Cannot find backend\algorithms directory! Please run this script from the project root.
    pause
    exit /b 1
)

where docker >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker command was not found. Please install Docker Desktop and make sure it is running.
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
            echo [ERROR] Failed to build algo_%%D.
            echo [ERROR] Please check the Docker build log above, Docker Desktop status, network access, and disk space.
            pause
            exit /b !ERRORLEVEL!
        )
        echo.
    )
)

:: Return to root directory
cd ..\..

:: Ensure Docker Compose and backend know the host project path when launched by double-click
set "PWD=%CD%"
set "HOST_EXCHANGE_DIR=%CD%\backend\temp_exchange"
if not exist "%HOST_EXCHANGE_DIR%" mkdir "%HOST_EXCHANGE_DIR%"

echo [2/2] Algorithm images built successfully. Starting main services...
echo.

:: Try new docker compose, fallback to old docker-compose if it fails
docker compose up --build -d
if %ERRORLEVEL% neq 0 (
    echo [WARN] docker compose failed, trying docker-compose...
    docker-compose up --build -d
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to start RoboStudio services.
        echo [ERROR] Please check the Compose log above, port usage for 8000/8501, and Docker Desktop status.
        pause
        exit /b !ERRORLEVEL!
    )
)

echo.
echo =======================================================
echo RoboStudio services started successfully in the background!
echo Opening your browser...
echo =======================================================

:: Wait for 3 seconds to ensure the frontend service is fully up
timeout /t 3 /nobreak > nul

:: Open the webpage
start http://localhost:8501

pause
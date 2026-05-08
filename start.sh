#!/bin/bash

set -o pipefail

# Ensure we are in the directory where the script is located (robust path handling)
cd "$(dirname "$0")" || exit 1
export PWD="$(pwd)"
export HOST_EXCHANGE_DIR="$PWD/backend/temp_exchange"
mkdir -p "$HOST_EXCHANGE_DIR"

echo "======================================================="
echo "RoboStudio"
echo "======================================================="
echo ""

# Check if the directory exists
if [ ! -d "backend/algorithms" ]; then
    echo "[ERROR] Cannot find backend/algorithms directory! Please run this script from the project root."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERROR] Docker command was not found. Please install Docker and make sure it is running."
    exit 1
fi

echo "[1/2] Checking and building algorithm environment images..."
echo ""

cd backend/algorithms || exit 1

# Loop through directories and build images
for dir in */; do
    # Remove trailing slash
    algo_dir="${dir%/}"
    
    if [ -f "$algo_dir/Dockerfile.algo" ]; then
        echo "--- Found algorithm directory: $algo_dir ---"
        
        # Convert to lowercase for docker image name (Docker requirement)
        img_name="algo_$(echo "$algo_dir" | tr '[:upper:]' '[:lower:]')"
        
        docker build -t "$img_name" -f "$algo_dir/Dockerfile.algo" .
        
        if [ $? -ne 0 ]; then
            echo "[ERROR] Failed to build $img_name."
            echo "[ERROR] Please check the Docker build log above, Docker status, network access, and disk space."
            exit 1
        fi
        echo ""
    fi
done

# Return to root directory
cd ../..

echo "[2/2] Algorithm images built successfully. Starting main services..."
echo ""

# Try new docker compose, fallback to old docker-compose if it fails
if ! docker compose up --build -d; then
    echo "[WARN] docker compose failed, trying docker-compose..."
    if ! docker-compose up --build -d; then
        echo "[ERROR] Failed to start RoboStudio services."
        echo "[ERROR] Please check the Compose log above, port usage for 8000/8501, and Docker status."
        exit 1
    fi
fi

echo ""
echo "======================================================="
echo "RoboStudio services started successfully in the background!"
echo "Opening your browser..."
echo "======================================================="

# Wait for 3 seconds to ensure the frontend service is fully up
sleep 3

# Open the webpage depending on the OS
if command -v xdg-open &> /dev/null; then
    # Linux
    xdg-open http://localhost:8501
elif command -v open &> /dev/null; then
    # macOS
    open http://localhost:8501
else
    # Fallback if no browser command is found
    echo "Please open your browser and navigate to: http://localhost:8501"
fi
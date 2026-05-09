# 1. Use the official Python 3.9-slim image as the base
FROM python:3.9-slim

# 2. Replace APT sources with Aliyun mirror for faster downloads in China
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 3. Install system-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 4. Set the main working directory
WORKDIR /app

# 5. Copy and install backend dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 6. Copy the entire backend project into the working directory
COPY . .

# 7. Unzip required asset files
WORKDIR /app/algorithms/code_as_policies
RUN unzip -o robotiq_2f_85.zip -d assets/ && \
    unzip -o bowl.zip -d assets/

# --- Core path structure fix ---
# 8. Adjust the ur5e folder structure to match the asset loading path expected by the algorithm.
#    Use cp (copy) + rm (remove) instead of mv to force-overwrite the target directory.
RUN cp -r /app/algorithms/code_as_policies/assets/ur5e/ur5e/* /app/algorithms/code_as_policies/assets/ur5e/ && \
    rm -rf /app/algorithms/code_as_policies/assets/ur5e/ur5e

# 9. Return to the main working directory
WORKDIR /app

# 10. The startup command is provided by docker-compose.yml

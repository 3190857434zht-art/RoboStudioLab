# 1. 使用官方的Python 3.9-slim镜像作为基础
FROM python:3.9-slim

# 2. 替换APT源为国内镜像 (阿里云)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 3. 安装系统级依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 4. 设置主工作目录
WORKDIR /app

# 5. 复制后端主应用的依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 6. 复制整个后端项目到工作目录
COPY . .

# 7. 解压必要的资源文件
WORKDIR /app/algorithms/code_as_policies
RUN unzip -o robotiq_2f_85.zip -d assets/ && \
    unzip -o bowl.zip -d assets/

# --- 核心路径结构修正 ---
# 8. 调整 ur5e 文件夹结构以匹配算法代码的加载路径
#    使用 cp (copy) 和 rm (remove) 的组合来代替 mv，以强制覆盖目标目录
RUN cp -r /app/algorithms/code_as_policies/assets/ur5e/ur5e/* /app/algorithms/code_as_policies/assets/ur5e/ && \
    rm -rf /app/algorithms/code_as_policies/assets/ur5e/ur5e

# 9. 返回到主工作目录
WORKDIR /app

# 10. 启动命令将由 docker-compose.yml 提供

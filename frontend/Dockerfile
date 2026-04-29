# 1. 使用官方的Python 3.9镜像作为基础
FROM python:3.9-slim

# 2. 设置工作目录
WORKDIR /app

# 3. 复制依赖文件
COPY requirements.txt .

# 4. 安装依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 5. 复制项目文件
COPY . .

# 6. 暴露Streamlit的默认端口8501
EXPOSE 8501

# 7. 容器启动时执行的命令
#    --server.port 8501: 指定端口
#    --server.address 0.0.0.0: 允许从外部访问
#    --server.enableCORS false: 解决一些跨域问题
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableCORS=false"]

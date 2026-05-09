# 1. Use the official Python 3.9 image as base
FROM python:3.9-slim

# 2. Set working directory
WORKDIR /app

# 3. Copy dependency file
COPY requirements.txt .

# 4. Install dependencies
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 5. Copy project files
COPY . .

# 6. Expose Streamlit default port 8501
EXPOSE 8501

# 7. Command to run when the container starts
#    --server.port 8501: specify port
#    --server.address 0.0.0.0: allow external access
#    --server.enableCORS false: resolve CORS issues
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.enableCORS=false"]

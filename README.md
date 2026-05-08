# RoboStudio

RoboStudio 是一个面向机械臂操作算法的 Web 可视化、运行编排和评估平台。项目通过 Streamlit 前端、FastAPI 后端和 Docker 算法容器，把不同机械臂算法统一到同一套运行、调参、查看日志、保存实验历史和代码回放工作流中。

当前仓库内置三个示例算法：

- `code_as_policies`：基于大语言模型生成 Python 控制代码，并在 PyBullet 环境中执行和生成视频。
- `language_planner`：基于大语言模型生成文本任务计划，并映射到预定义动作集合。
- `cliport_agent`：端到端视觉语言操作模型示例，运行 CLIPort 评估流程并展示日志或视频。

## 功能概览

启动后访问 `http://localhost:8501` 进入 RoboStudio 工作台：

- 自动发现已经构建好的 `algo_*` 算法镜像。
- 根据每个算法的 `config.json` 自动生成参数控件。
- 通过后端异步启动独立算法容器，避免依赖冲突。
- 展示算法返回的视频、生成代码、文本计划和运行日志。
- 支持编辑代码后重新模拟。
- 保存运行结果、草稿、分支实验和备注。
- 支持取消正在运行的任务。

## 架构

```text
.
├── docker-compose.yml
├── start.bat
├── start.sh
├── frontend/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
└── backend/
    ├── main.py
    ├── database.py
    ├── Dockerfile
    ├── requirements.txt
    └── algorithms/
        ├── wrapper.py
        ├── code_as_policies/
        ├── language_planner/
        └── cliport_agent/
```

运行流程：

1. 启动脚本遍历 `backend/algorithms/`。
2. 对每个包含 `Dockerfile.algo` 的算法构建镜像，例如 `algo_code_as_policies`。
3. `docker compose up --build -d` 启动前端和后端。
4. 前端请求后端 `/algorithms`，后端从 Docker 镜像列表中发现算法。
5. 用户点击运行后，后端写入 `input.json` 到交换目录。
6. 后端启动对应算法容器，并挂载交换目录到算法容器的 `/exchange`。
7. 算法容器运行 `wrapper.py`，调用 `<algorithm_id>.Interactive_Demo`。
8. 算法写入 `output.json`，后端读取结果并返回前端。

## 环境要求

必须提前安装：

- Docker
- Docker Compose，支持 `docker compose` 或旧版 `docker-compose`
- 可访问基础镜像、PyPI 镜像、PyTorch 镜像和模型下载地址的网络
- 足够磁盘空间，CUDA、PyTorch 和 CLIPort 镜像体积较大，建议预留几十 GB
- 足够内存，Windows Docker Desktop 建议分配 8 GB 以上

Windows 用户还需要：

- WSL2
- Docker Desktop
- Docker Desktop 使用 Linux containers 模式
- Docker Desktop 启用 WSL2 backend / WSL integration

如果运行 `cliport_agent`，建议准备 NVIDIA GPU、匹配驱动和 Docker GPU 支持。`code_as_policies` 和 `language_planner` 不强制要求 GPU。

## 一键启动

### Windows

在项目根目录双击：

```bat
start.bat
```

脚本会自动：

1. 检查 Docker 命令是否可用。
2. 创建 `backend/temp_exchange/` 交换目录。
3. 构建所有算法镜像。
4. 启动 RoboStudio 前端和后端服务。
5. 打开 `http://localhost:8501`。

如果算法镜像构建失败或 Compose 启动失败，脚本会打印错误信息并停止，不会误报启动成功。

### Linux / macOS

在项目根目录执行：

```bash
chmod +x start.sh
./start.sh
```

停止服务：

```bash
docker compose down
```

## 权重文件上传

仓库当前已经允许提交 CLIPort checkpoint，`backend/algorithms/cliport_agent/.gitignore` 不再忽略 `checkpoints/`。如果你希望别人克隆后能直接运行 `cliport_agent`，需要把 `.ckpt` 权重放到代码期望的位置，例如：

```text
backend/algorithms/cliport_agent/exps/<model_task>-cliport-n1000-train/checkpoints/
```

默认配置中 `model_task` 是 `multi-language-conditioned`，常见目录形如：

```text
backend/algorithms/cliport_agent/exps/multi-language-conditioned-cliport-n1000-train/checkpoints/
```

GitHub 对普通 Git 文件有大小限制：

- 单个文件超过 50 MB 会有警告。
- 单个文件超过 100 MB 不能直接推送到 GitHub。
- 如果 `.ckpt` 权重大于 100 MB，应使用 Git LFS。

仓库已包含 `.gitattributes`，会把 `.ckpt`、`.pth`、`.pt`、`.safetensors`、`.onnx` 和 `.bin` 按 Git LFS 文件处理。提交权重前确认本机已安装 Git LFS：

```bash
git lfs install
git add backend/algorithms/cliport_agent/exps/**/checkpoints/*
```

如果你的 GitHub 仓库没有启用或没有足够 LFS 配额，可以把权重放到 Release、网盘或 HuggingFace，并在 README 中写明下载位置和放置路径。

## API 设置

前端右上角提供 API 设置入口，需要填写：

- API Key
- API Base URL
- 模型名

`code_as_policies` 和 `language_planner` 会调用 OpenAI 兼容接口。`cliport_agent` 主要使用本地端到端模型流程，但统一请求结构中也会携带这些字段。

不要把真实 API Key 写入源码、Notebook、运行缓存或提交记录。`backend/temp_exchange/` 是运行交换目录，历史运行可能包含敏感参数，发布或提交前应清理。

## 已集成算法

### Code as Policies

目录：`backend/algorithms/code_as_policies/`

作用：

- 接收自然语言任务，例如“把红色方块放到蓝色碗里”。
- 调用大语言模型生成 Python 控制代码。
- 在 PyBullet 中构造桌面抓取环境。
- 输出可编辑代码、运行日志和 MP4 视频。

注意：该算法会在容器内执行大模型生成或用户编辑后的 Python 代码。虽然运行环境被 Docker 隔离，但仍属于代码执行能力，应仅在可信环境中使用。

### Language Planner

目录：`backend/algorithms/language_planner/`

作用：

- 接收自然语言任务。
- 调用大语言模型生成文本计划。
- 使用 SentenceTransformer 将计划步骤映射到 `available_actions.json`。
- 输出伪代码形式的动作序列。

首次运行时，`SentenceTransformer('all-MiniLM-L6-v2')` 可能需要联网下载模型。

### CLIPort Agent

目录：`backend/algorithms/cliport_agent/`

作用：

- 运行 CLIPort 端到端视觉语言操作模型评估流程。
- 根据任务名生成或复用测试数据。
- 查找本地 checkpoint 并运行 `cliport/eval.py`。
- 尝试读取评估过程中生成的视频。

注意：

- `cliport_agent` 的 `config.json` 标记了 `requires_gpu: true`。
- 缺少 `.ckpt` 权重时，系统不会自动下载完整预训练权重。
- “任务描述”会作为 CLIPort 的 `eval_task` 任务名使用，例如 `stack-block-pyramid-seq-seen-colors`，不是自然语言到任务名的自动映射。

## 新算法接入

新增算法时，在 `backend/algorithms/` 下创建目录，例如：

```text
backend/algorithms/my_new_algo/
```

推荐结构：

```text
backend/algorithms/my_new_algo/
├── __init__.py
├── config.json
├── requirements.txt
├── Dockerfile.algo
├── Interactive_Demo.py
├── assets/
├── models/
└── src/
```

必须遵守：

- 目录名建议只使用小写字母、数字和下划线。
- `Dockerfile.algo` 必须位于算法根目录。
- 构建上下文是 `backend/algorithms/`，因此 Dockerfile 中的 `COPY` 路径要从该目录开始写。
- `Interactive_Demo.py` 至少实现 `run_algorithm(params)` 和 `run_from_code(params)`。
- 算法结果建议包含 `generated_code`、`video` 和 `log`。
- 如果算法不支持视频，返回 `"video": "NO_VIDEO_SUPPORTED"`。
- 如果端到端算法不支持代码编辑回放，返回 `"video": "E2E_NO_CODE_SUPPORTED"`。

示例 `config.json`：

```json
{
  "requires_gpu": false,
  "params": [
    {
      "name": "num_blocks",
      "label": "物体数量",
      "type": "slider",
      "min": 0,
      "max": 10,
      "default": 4
    }
  ]
}
```

示例 `Dockerfile.algo`：

```dockerfile
FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /algorithm

COPY my_new_algo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY my_new_algo/ /algorithm/my_new_algo/
COPY wrapper.py /algorithm/wrapper.py

CMD ["python", "wrapper.py"]
```

## 常见问题

### 前端下拉框没有算法

通常说明算法镜像没有构建成功。检查是否存在镜像：

```bash
docker images
```

镜像名应以 `algo_` 开头，例如 `algo_code_as_policies`。

### 提示找不到 `/exchange/input.json`

通常是 `HOST_EXCHANGE_DIR` 未正确设置或宿主机路径挂载失败。请优先使用 `start.bat` 或 `start.sh` 启动，它们会显式设置该路径。

### CLIPort 无法运行

优先检查：

- 是否有 NVIDIA GPU 和驱动。
- Docker 是否能访问 GPU。
- checkpoint 是否存在且路径正确。
- 镜像构建是否完整。
- Docker Desktop 是否分配了足够内存。

### 构建很慢或失败

可能原因：

- 基础镜像拉取慢。
- PyPI、PyTorch、HuggingFace 网络不可达。
- CUDA 镜像体积大。
- 依赖版本和 Python/CUDA 版本不兼容。
- Docker Desktop 磁盘或内存不足。

## 更新 GitHub 仓库

当前远程仓库：

```text
https://github.com/3190857434zht-art/RoboArmLabPlatform
```

常规更新流程：

```bash
git status
git add .
git commit -m "Rename project to RoboStudio and improve deployment"
git push origin main
```

如果你的默认分支不是 `main`，先运行：

```bash
git branch --show-current
```

然后把 `main` 替换成当前分支名。

如果要提交大权重文件，先配置 Git LFS：

```bash
git lfs install
git add .gitattributes
git add <你的权重文件路径>
git commit -m "Add model checkpoints"
git push origin main
```

## 安全提醒

- 不要提交 `.env`、真实 API Key、运行数据库或 `backend/temp_exchange/`。
- 发布前建议搜索 `sk-`、`openai_api_key`、`api_key`。
- 如果已经提交过真实密钥，应立即作废并重新生成。

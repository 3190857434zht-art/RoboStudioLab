# LLM-ArmSim 机械臂算法可视化与评估平台

LLM-ArmSim 是一个面向机械臂操作算法的 Web 可视化、运行编排和评估平台。平台本身不提供新的底层机械臂控制算法，核心价值在于提供一套标准化的算法接入模板、Docker 隔离运行环境和交互式工作台，让不同类型的算法可以用统一方式接入、运行、调参、编辑代码、查看日志和保存实验历史。

当前仓库已经集成了三个示例算法：

- `code_as_policies`：基于大语言模型生成 Python 控制代码，并在 PyBullet 桌面抓取环境中执行和生成视频。
- `language_planner`：基于大语言模型生成文本任务计划，并将自然语言步骤映射到预定义动作集合。
- `cliport_agent`：端到端视觉语言操作模型示例，运行 CLIPort 评估流程并展示结果日志/视频。

## 系统效果

启动后访问 `http://localhost:8501`，可以进入 Streamlit 工作台。主要效果包括：

- 在网页中选择算法、输入任务描述、配置算法参数和 API 设置。
- 自动发现已经构建好的 `algo_*` 算法镜像，并把算法展示到下拉列表中。
- 根据每个算法的 `config.json` 自动生成参数控件，例如滑块和文本输入框。
- 点击“运行模拟”后，后端异步启动独立算法容器执行任务。
- 展示算法返回的视频、生成代码、文本计划或端到端模型提示信息。
- 提供代码编辑器，可对支持代码回放的算法执行“应用代码并模拟”。
- 保存运行结果、草稿、分支实验、备注和运行日志，便于对比不同方案。
- 支持取消正在运行的任务，后端会尝试终止对应算法容器。
- 支持为每个条目单独添加备注，可以作为人工指导算法进行微调的评论，也可标注各类情况。

## 架构概览

系统由三个层次组成：

- `frontend/`：Streamlit 前端工作台，负责参数 UI、视频/代码/历史记录展示、API 设置和用户操作。
- `backend/`：FastAPI 后端，负责算法发现、任务排队、Docker 容器编排、历史数据库和模型接口代理。
- `backend/algorithms/`：算法插件目录。每个算法拥有自己的源码、依赖、配置文件和算法镜像构建文件。

运行流程如下：

1. 启动脚本遍历 `backend/algorithms/`，为所有包含 `Dockerfile.algo` 的算法构建镜像，镜像名形如 `algo_code_as_policies`。
2. `docker compose up --build -d` 构建并启动前端、后端服务。
3. 前端请求后端 `/algorithms`，后端从 Docker 镜像列表中发现所有 `algo_*` 算法。
4. 用户点击运行后，后端把输入参数写入交换目录中的 `input.json`。
5. 后端启动对应算法容器，并把宿主机交换目录挂载为算法容器内的 `/exchange`。
6. 算法容器运行统一的 `wrapper.py`，动态导入 `<algorithm_id>.Interactive_Demo`。
7. `wrapper.py` 调用算法的 `run_algorithm(params)` 或 `run_from_code(params)`。
8. 算法把结果写入 `/exchange/output.json`，后端读取后返回前端并写入历史数据库。

## 宿主机要求

必须提前安装：

- Docker
- Docker Compose，支持 `docker compose` 或旧版 `docker-compose`
- 可访问基础镜像、PyPI 镜像、PyTorch 镜像和模型下载地址的网络
- 足够磁盘空间，CUDA、PyTorch 和 CLIPort 镜像体积较大，建议预留几十 GB
- 足够内存，Windows Docker Desktop 建议分配 8 GB 以上

Windows 用户还需要：

- WSL2
- Docker Desktop
- Docker Desktop 启用 WSL2 backend / WSL integration
- 使用 Linux containers 模式运行本项目

如果运行 `cliport_agent`，还建议准备：

- NVIDIA GPU
- 匹配的 NVIDIA 驱动
- Docker GPU 支持
- Windows 下的 WSL2 GPU 支持

`code_as_policies` 和 `language_planner` 不强制要求 GPU。`cliport_agent` 的配置中标记了 `requires_gpu: true`，后端会优先尝试以 GPU 模式启动，失败后会尝试 CPU 模式，但 CPU 运行可能非常慢或因环境差异失败。

## 快速启动

### Windows

在项目根目录双击：

```bat
start.bat
```

脚本会自动：

1. 进入 `backend/algorithms/`。
2. 遍历每个算法目录。
3. 对包含 `Dockerfile.algo` 的算法执行 `docker build`。
4. 回到项目根目录执行 `docker compose up --build -d`。
5. 打开 `http://localhost:8501`。

### Linux / macOS

在项目根目录执行：

```bash
chmod +x start.sh
./start.sh
```

也可以手动启动：

```bash
cd backend/algorithms
docker build -t algo_code_as_policies -f code_as_policies/Dockerfile.algo .
docker build -t algo_language_planner -f language_planner/Dockerfile.algo .
docker build -t algo_cliport_agent -f cliport_agent/Dockerfile.algo .
cd ../..
docker compose up --build -d
```

停止服务：

```bash
docker compose down
```

## API 设置

前端右上角提供 API 设置入口，需要填写：

- API Key
- API Base URL
- 模型名

这些参数会随运行请求传给后端和算法容器。`code_as_policies` 和 `language_planner` 会调用 OpenAI 兼容接口；`cliport_agent` 主要使用本地端到端模型流程，但统一请求结构中也会携带这些字段。

注意不要把真实 API Key 写入源码、Notebook、运行缓存或提交记录。`backend/temp_exchange/` 是运行交换目录，历史运行可能包含敏感参数，发布或提交前应清理。

## 已集成算法

### Code as Policies

目录：`backend/algorithms/code_as_policies/`

作用：

- 接收自然语言任务，例如“把红色方块放到蓝色碗里”。
- 调用大语言模型生成 Python 控制代码。
- 在 PyBullet 中构造桌面抓取环境。
- 执行生成代码，输出可编辑代码、运行日志和 MP4 视频。

配置：`config.json` 中提供 `num_blocks` 和 `num_bowls` 两个滑块参数。

返回：

- `generated_code`：模型生成并执行的代码。
- `video`：Base64 编码的 MP4 视频。
- `log`：运行日志。

注意：该算法会在容器内执行大模型生成或用户编辑后的 Python 代码。虽然运行环境被 Docker 隔离，但仍属于代码执行能力，应仅在可信环境中使用。当前实现中部分 LMP 调用路径仍默认使用 `gpt-4-turbo`，部分路径使用前端传入的 `selected_model`，如果切换模型后行为不一致，应优先检查 `Interactive_Demo.py` 中的模型选择逻辑。

### Language Planner

目录：`backend/algorithms/language_planner/`

作用：

- 接收自然语言任务。
- 调用大语言模型生成文本计划。
- 使用 SentenceTransformer 将计划步骤映射到 `available_actions.json` 中的预定义动作。
- 输出伪代码形式的动作序列。

配置：`config.json` 中提供 `model_source` 文本参数。

返回：

- `generated_code`：形如 `robot.execute(...)` 的计划结果。
- `video`：`NO_VIDEO_SUPPORTED`，表示该算法只输出文本计划。
- `log`：规划和映射日志。

首次运行时，`SentenceTransformer('all-MiniLM-L6-v2')` 可能需要联网下载模型。

注意：当前 `config.json` 中的 `model_source` 是预留参数，现有 `Interactive_Demo.py` 主要通过前端传入的 API Key、Base URL 和模型名调用 OpenAI 兼容接口。

### CLIPort Agent

目录：`backend/algorithms/cliport_agent/`

作用：

- 运行 CLIPort 端到端视觉语言操作模型评估流程。
- 根据任务名生成或复用测试数据。
- 查找本地 checkpoint 并运行 `cliport/eval.py`。
- 尝试读取评估过程中生成的视频。

配置：`config.json` 中标记 `requires_gpu: true`，并提供 `model_task` 文本参数，默认值为 `multi-language-conditioned`。

返回：

- `generated_code`：提示该算法为端到端模型，不生成中间代码。
- `video`：评估生成的视频，或 `E2E_NO_CODE_SUPPORTED`。
- `log`：CLIPort 数据生成和评估日志。

注意：CLIPort 依赖本地已有 checkpoint。如果发布包中没有 `.ckpt` 权重，系统不会自动下载完整预训练权重。

注意：该算法的“任务描述”会作为 CLIPort 的 `eval_task` 任务名使用，例如 `stack-block-pyramid-seq-seen-colors`。它不是自然语言到任务名的自动映射，填写普通中文句子可能导致数据生成或评估失败。

## 新算法适配教程

平台的核心设计目标是让算法按模板接入。新增算法时，只需要遵守以下约定。

### 1. 创建算法目录

在 `backend/algorithms/` 下创建算法目录，例如：

```text
backend/algorithms/my_new_algo/
```

建议目录名只使用小写字母、数字和下划线。镜像名会使用 `algo_<algorithm_id>`，例如 `algo_my_new_algo`。

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

如果算法内部有多级 Python 包，需要在相关目录补充 `__init__.py`。

Windows 的 `start.bat` 会直接使用算法文件夹名生成镜像名，建议算法目录统一使用小写字母、数字和下划线，避免大小写导致镜像名和算法 ID 不一致。

### 2. 编写参数配置 `config.json`

`config.json` 决定前端如何为算法生成参数 UI。目前前端支持：

- `slider`
- `text_input`

示例：

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
    },
    {
      "name": "model_task",
      "label": "模型任务类型",
      "type": "text_input",
      "default": "default-task"
    }
  ]
}
```

字段说明：

- `requires_gpu`：是否优先以 GPU 模式启动算法容器。
- `params`：参数列表，会被前端渲染，并随运行请求传入算法。
- `name`：参数键名，算法中通过 `params.get("name")` 读取。
- `label`：前端显示名称。
- `type`：当前支持 `slider` 和 `text_input`。
- `default`：默认值。
- `min` / `max`：`slider` 需要提供。

如需支持下拉框、复选框、文件上传等控件，需要扩展 `frontend/app.py` 中的参数渲染逻辑。

如果希望借助大模型把已有算法脚本整理成平台模板，可以参考 `backend/prompt_templates.py` 中的提示词，生成 `config.json` 和标准化后的 `Interactive_Demo.py` 草稿后再人工校验。

### 3. 实现标准入口 `Interactive_Demo.py`

每个算法必须在根目录提供 `Interactive_Demo.py`，并至少实现：

```python
def run_algorithm(params: dict) -> dict:
    ...

def run_from_code(params: dict) -> dict:
    ...
```

推荐定义算法根路径：

```python
import os

ALGORITHM_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
```

`run_algorithm(params)` 用于“运行模拟”，通常完成：

- 读取 `task_description`、`openai_api_key`、`openai_base_url`、`selected_model` 和自定义参数。
- 初始化模型、仿真环境或规划器。
- 执行算法主流程。
- 捕获日志。
- 返回生成代码、视频或文本结果。

返回格式建议：

```python
return {
    "generated_code": "print('hello')",
    "video": "BASE64_MP4_STRING_OR_PLACEHOLDER",
    "log": "running logs"
}
```

`run_from_code(params)` 用于“应用代码并模拟”，通常完成：

- 读取 `params["code_to_run"]`。
- 初始化和 `run_algorithm` 一致的执行环境。
- 执行用户编辑后的代码。
- 返回视频和日志。

返回格式建议：

```python
return {
    "video": "BASE64_MP4_STRING_OR_PLACEHOLDER",
    "log": "running logs"
}
```

如果算法不支持视频，返回：

```python
"video": "NO_VIDEO_SUPPORTED"
```

如果算法是端到端模型，不支持代码编辑回放，可以在 `run_from_code` 中返回提示日志，并使用：

```python
"video": "E2E_NO_CODE_SUPPORTED"
```

### 4. 编写依赖文件 `requirements.txt`

把算法专属 Python 依赖写入：

```text
backend/algorithms/my_new_algo/requirements.txt
```

建议固定关键依赖版本，尤其是：

- `torch`
- `torchvision`
- `pybullet`
- `opencv-python`
- `transformers`
- `sentence-transformers`
- 与 CUDA 或模型权重强相关的库

### 5. 编写算法镜像 `Dockerfile.algo`

`Dockerfile.algo` 必须位于算法根目录。构建上下文是 `backend/algorithms/`，因此 `COPY` 路径要从 `backend/algorithms/` 开始写。

基础模板：

```dockerfile
FROM python:3.9-slim

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /algorithm

COPY my_new_algo/requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY my_new_algo/ /algorithm/my_new_algo/
COPY wrapper.py /algorithm/wrapper.py

WORKDIR /algorithm
CMD ["python", "wrapper.py"]
```

如果算法需要 CUDA，可参考 `backend/algorithms/cliport_agent/Dockerfile.algo` 使用 NVIDIA CUDA 基础镜像，并在 `config.json` 中设置：

```json
{
  "requires_gpu": true,
  "params": []
}
```

### 6. 构建并启动

推荐直接运行项目启动脚本，它会自动构建所有算法镜像。

也可以手动构建单个算法：

```bash
cd backend/algorithms
docker build -t algo_my_new_algo -f my_new_algo/Dockerfile.algo .
cd ../..
docker compose up --build -d
```

构建成功后，算法会出现在前端算法下拉列表中。

## 适配算法时的输出约定

后端会根据结果判断任务状态：

- 如果结果中有非空 `error` 字段，任务会被标记为失败。
- 如果 `generated_code` 包含 `# No valid code generated.`，任务会被标记为失败。
- 如果没有 `video` 字段或视频为空，任务会被标记为失败。

因此，即使算法不支持真实视频，也应返回占位值：

```python
"video": "NO_VIDEO_SUPPORTED"
```

或：

```python
"video": "E2E_NO_CODE_SUPPORTED"
```

## 注意事项

### Docker 和 WSL2

本项目基于 Linux Docker 容器。Windows 用户需要 Docker Desktop 和 WSL2，不支持切换到 Windows containers 模式运行。

### `HOST_EXCHANGE_DIR`

后端启动算法容器时需要把宿主机交换目录挂载到算法容器的 `/exchange`。当前 `docker-compose.yml` 使用：

```yaml
HOST_EXCHANGE_DIR=${PWD}/backend/temp_exchange
```

在 Linux/macOS 下通常可用，但 Windows 双击 `start.bat` 时 `PWD` 可能为空。更稳妥的做法是在启动脚本中显式设置 `HOST_EXCHANGE_DIR`，再传给 Compose。

Windows 示例：

```bat
set "HOST_EXCHANGE_DIR=%CD%\backend\temp_exchange"
docker compose up --build -d
```

Linux/macOS 示例：

```bash
export HOST_EXCHANGE_DIR="$(pwd)/backend/temp_exchange"
docker compose up --build -d
```

### API Key 和运行缓存

本项目默认面向个人本地使用。大模型 API Key 由使用者在前端 API 设置中自行填写，算法运行时通过前端请求传入后端和算法容器，项目源码不应内置任何真实 Key。

运行请求会包含 `openai_api_key` 和 `openai_base_url`。不要把真实 Key 写进源码、Notebook、`.env` 或示例配置。发布或发包前必须排除本地运行产物：

```text
backend/temp_exchange/
backend/algorithms/backend/temp_exchange/
backend/database/
backend/algorithms/**/.ipynb_checkpoints/
*.db
.env
```

仓库根目录的 `.gitignore` 和 `backend/.dockerignore` 已排除上述路径，避免把本地缓存、数据库或密钥文件提交/打进镜像。若使用压缩软件手动发包，也需要确认这些路径没有被包含。

发包前建议在项目根目录全文搜索 `sk-`、`openai_api_key`、`api_key`。如果已经把真实 Key 提交或发送给他人，应立即作废并重新生成。本项目不提供内置 Key，也不承担使用者自行填写、保存或分发密钥造成的泄露责任。

### 模型和权重

Dockerfile 会安装大多数 Python 依赖，但不保证下载所有运行时模型和权重：

- `language_planner` 首次运行可能下载 SentenceTransformer 模型。
- `cliport_agent` 依赖本地 checkpoint；缺少权重时不会自动下载完整预训练模型。
- 大模型接口由用户在前端配置，不随系统自动提供。

### 算法隔离

每个算法通过独立 Docker 镜像运行，可以避免依赖冲突。但新增算法时也意味着：

- 算法依赖必须写入自己的 `requirements.txt` 和 `Dockerfile.algo`。
- 模型权重、URDF、纹理、配置文件等静态资源必须复制进算法目录或在 Dockerfile 中下载/解压。
- 算法运行必须适配无 GUI 环境，PyBullet 应使用 `DIRECT`，不要依赖 `cv2.imshow()` 或桌面窗口。

### 网络模式

后端启动算法容器时使用 `network_mode="host"`。这在 Linux 上语义明确；在 Docker Desktop 环境中行为可能存在差异。如果算法需要访问宿主机服务，请优先使用外部可访问地址或 Docker Desktop 支持的主机名。

前端服务端访问后端使用容器内地址 `http://backend:8000`。本项目按本机部署设计，前端容器默认设置 `BACKEND_PUBLIC_URL=http://localhost:8000`，浏览器会高频自动轮询任务状态；任务结束后页面会自动加载视频、代码、日志和历史记录。“手动检查并加载结果”按钮仅作为网络异常或长时间等待时的兜底确认。

### 端口

默认端口：

- 前端：`8501`
- 后端：`8000`

如果端口被占用，需要调整 `docker-compose.yml` 和相关访问地址。

## 常见问题

### 前端下拉框没有算法

通常说明算法镜像没有构建成功。检查是否存在镜像：

```bash
docker images
```

镜像名应以 `algo_` 开头，例如 `algo_code_as_policies`。

### 提示找不到 `/exchange/input.json`

通常是 `HOST_EXCHANGE_DIR` 未正确设置或宿主机路径挂载失败。优先检查 `docker-compose.yml` 中的 `HOST_EXCHANGE_DIR`，以及 Windows 下是否使用了 WSL2/Docker Desktop 正确共享路径。

### CLIPort 无法运行

优先检查：

- 是否有 NVIDIA GPU 和驱动。
- Docker 是否能访问 GPU。
- checkpoint 是否存在。
- 镜像构建是否完整。
- Docker Desktop 是否分配了足够内存。

### 构建很慢或失败

可能原因：

- 基础镜像拉取慢。
- PyPI、PyTorch、HuggingFace 网络不可达。
- CUDA 镜像体积大。
- 依赖版本和 Python/CUDA 版本不兼容。

可以根据网络环境替换 Dockerfile 中的 apt/pip 镜像源。

## 目录速览

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

## 项目定位

LLM-ArmSim 的重点不是替代具体机械臂算法，而是把不同算法统一到同一套评估工作流中：

- 用统一 UI 调参和运行。
- 用统一接口传入任务和参数。
- 用统一容器机制隔离依赖。
- 用统一结果格式展示代码、视频和日志。
- 用统一历史记录保存实验过程。

因此，新增算法时应尽量遵守模板约定，把算法自身差异收敛在 `config.json`、`Interactive_Demo.py`、`requirements.txt` 和 `Dockerfile.algo` 中。

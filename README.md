# RoboStudio

RoboStudio is a containerized unified platform for embodied-AI algorithm integration, visualization, and comparison. It brings heterogeneous robot arm manipulation algorithms together under a single Streamlit frontend backed by a FastAPI backend and per-algorithm Docker containers, providing a unified workflow for running experiments, tuning parameters, inspecting logs, saving run history, and performing interactive code editing.

Three example algorithms are bundled in the repository:

- `code_as_policies`: LLM-driven code generation — generates a Python control script and executes it in a PyBullet simulation, producing a video.
- `language_planner`: Text-based task planning — invokes an LLM to produce a step-by-step plan, then maps each step to a predefined action via SentenceTransformer.
- `cliport_agent`: End-to-end visual-action mapping — runs the CLIPort evaluation pipeline and returns a simulation video or log.

## Feature Overview

After startup, open `http://localhost:8501` to enter the RoboStudio workspace:

- Auto-discovers built `algo_*` algorithm images via the host Docker socket.
- Reads each algorithm's `config.json` and automatically renders parameter controls.
- Launches independent per-algorithm sibling containers asynchronously to avoid dependency conflicts.
- Displays algorithm outputs: simulation video, generated code, text plan, and execution log.
- Supports interactive code editing and re-simulation via **Apply Code and Re-simulate**.
- Saves run results, unsimulated drafts, branch experiments, and notes in a SQLite-backed branch-tree store.
- Supports cancelling any in-flight simulation job on demand.

## Architecture

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

Runtime flow:

1. The startup script iterates over `backend/algorithms/`.
2. For each subdirectory containing `Dockerfile.algo`, it builds an algorithm image, e.g. `algo_code_as_policies`.
3. `docker compose up --build -d` starts the frontend and backend services.
4. The frontend requests `/algorithms` from the backend; the backend discovers registered algorithms by querying the host Docker daemon for images prefixed `algo_`.
5. When the user clicks **Run**, the backend writes `input.json` to the exchange directory.
6. The backend launches the corresponding algorithm container and mounts the exchange directory to `/exchange` inside the container.
7. The algorithm container runs `wrapper.py`, which calls `<algorithm_id>.Interactive_Demo`.
8. The algorithm writes `output.json`; the backend reads the result and returns it to the frontend.

## Requirements

The following must be installed in advance:

- Docker
- Docker Compose (supports both `docker compose` and the legacy `docker-compose`)
- Network access to base images, PyPI, PyTorch indexes, and model download endpoints
- Sufficient disk space — CUDA, PyTorch, and CLIPort images are large; reserve at least several tens of GB
- Sufficient RAM — Docker Desktop on Windows is recommended to be allocated 8 GB or more

Windows users additionally require:

- WSL2
- Docker Desktop
- Docker Desktop configured to use Linux containers mode
- Docker Desktop with WSL2 backend / WSL integration enabled

Running `cliport_agent` requires an NVIDIA GPU, compatible drivers, and Docker GPU support. `code_as_policies` and `language_planner` do not require a GPU.

## One-Command Startup

### Windows

Double-click in the project root directory:

```bat
start.bat
```

The script will automatically:

1. Verify that the Docker command is available.
2. Create the `backend/temp_exchange/` exchange directory.
3. Build all algorithm images.
4. Start the RoboStudio frontend and backend services.
5. Open `http://localhost:8501`.

If any algorithm image build or Compose startup fails, the script prints an error message and stops — it will not falsely report a successful launch.

### Linux / macOS

Run in the project root directory:

```bash
chmod +x start.sh
./start.sh
```

To stop services:

```bash
docker compose down
```

## Model Checkpoint Upload

The repository currently allows committing CLIPort checkpoints; `backend/algorithms/cliport_agent/.gitignore` no longer excludes `checkpoints/`. If you want others to run `cliport_agent` directly after cloning, place the `.ckpt` weights at the path expected by the code, for example:

```text
backend/algorithms/cliport_agent/exps/<model_task>-cliport-n1000-train/checkpoints/
```

The default `model_task` is `multi-language-conditioned`, so the typical directory looks like:

```text
backend/algorithms/cliport_agent/exps/multi-language-conditioned-cliport-n1000-train/checkpoints/
```

GitHub enforces size limits on ordinary Git files:

- Files over 50 MB trigger a warning.
- Files over 100 MB cannot be pushed directly to GitHub.
- If a `.ckpt` checkpoint exceeds 100 MB, use Git LFS.

The repository includes a `.gitattributes` file that tracks `.ckpt`, `.pth`, `.pt`, `.safetensors`, `.onnx`, and `.bin` files via Git LFS. Before committing weights, confirm Git LFS is installed locally:

```bash
git lfs install
git add backend/algorithms/cliport_agent/exps/**/checkpoints/*
```

If your GitHub repository does not have Git LFS enabled or has insufficient quota, host the weights on a Release, cloud drive, or HuggingFace and document the download URL and target path in the README.

## API Settings

The top-right corner of the frontend provides an API settings dialog. You need to supply:

- API Key
- API Base URL
- Model name

`code_as_policies` and `language_planner` call an OpenAI-compatible inference endpoint. `cliport_agent` primarily uses a local end-to-end model pipeline, but the unified request structure still carries these fields.

Do not embed real API keys in source code, notebooks, run caches, or commit history. `backend/temp_exchange/` is the runtime exchange directory; historical run files may contain sensitive parameters and should be cleaned before publishing or committing.

## Integrated Algorithms

### Code as Policies

Directory: `backend/algorithms/code_as_policies/`

Function:

- Accepts a natural-language task (e.g., "put the red block in the blue bowl").
- Calls an LLM to generate a Python control script.
- Constructs a tabletop pick-and-place environment in PyBullet.
- Returns the editable generated code, an execution log, and an MP4 simulation video.

Note: this algorithm executes LLM-generated or user-edited Python code inside the container. Although the runtime is isolated by Docker, it is a code-execution capability and should only be used in trusted environments.

### Language Planner

Directory: `backend/algorithms/language_planner/`

Function:

- Accepts a natural-language task.
- Calls an LLM to generate a step-by-step text plan.
- Uses SentenceTransformer (`all-MiniLM-L6-v2`) to map each step to the closest entry in `available_actions.json` by cosine similarity.
- Returns the mapped action sequence in pseudocode form.

On the first run, `SentenceTransformer('all-MiniLM-L6-v2')` may need to download the model weights from the internet.

### CLIPort Agent

Directory: `backend/algorithms/cliport_agent/`

Function:

- Runs the CLIPort end-to-end visual manipulation evaluation pipeline.
- Generates or reuses test data based on the task name.
- Locates a local checkpoint and runs `cliport/eval.py`.
- Attempts to read the video produced during evaluation.

Notes:

- `cliport_agent`'s `config.json` sets `requires_gpu: true`.
- Missing `.ckpt` weights are not downloaded automatically.
- The task-description field is used as the CLIPort `eval_task` identifier (e.g., `stack-block-pyramid-seq-seen-colors`), not as free-form natural language; there is no automatic natural-language-to-task-ID mapping.

## Adding a New Algorithm

To add a new algorithm, create a directory under `backend/algorithms/`, for example:

```text
backend/algorithms/my_new_algo/
```

Recommended layout:

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

Required conventions:

- Directory names should use only lowercase letters, digits, and underscores.
- `Dockerfile.algo` must reside at the algorithm root.
- The Docker build context is `backend/algorithms/`, so `COPY` paths in the Dockerfile must be written relative to that directory.
- `Interactive_Demo.py` must implement at least `run_algorithm(params)` and `run_from_code(params)`.
- Algorithm results should include `generated_code`, `video`, and `log`.
- If the algorithm does not support video, return `"video": "NO_VIDEO_SUPPORTED"`.
- If an end-to-end algorithm does not support code-driven re-simulation, return `"video": "E2E_NO_CODE_SUPPORTED"`.

Example `config.json`:

```json
{
  "requires_gpu": false,
  "params": [
    {
      "name": "num_blocks",
      "label": "Number of Objects",
      "type": "slider",
      "min": 0,
      "max": 10,
      "default": 4
    }
  ]
}
```

Example `Dockerfile.algo`:

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

## Troubleshooting

### No algorithms appear in the frontend dropdown

This usually means the algorithm images were not built successfully. Check whether the images exist:

```bash
docker images
```

Image names should be prefixed with `algo_`, e.g. `algo_code_as_policies`.

### Error: `/exchange/input.json` not found

This usually means `HOST_EXCHANGE_DIR` was not set correctly, or the host path mount failed. Use `start.bat` or `start.sh` to launch — they set this path explicitly.

### CLIPort cannot run

Check first:

- Is an NVIDIA GPU and driver present?
- Can Docker access the GPU?
- Does the checkpoint exist at the correct path?
- Did the image build complete successfully?
- Has Docker Desktop been allocated sufficient memory?

### Build is slow or fails

Possible causes:

- Slow base image pull.
- PyPI, PyTorch, or HuggingFace endpoints unreachable.
- Large CUDA image download.
- Dependency version incompatibility with the Python/CUDA version.
- Insufficient Docker Desktop disk space or memory.

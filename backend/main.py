from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field
import asyncio
import importlib
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional
import database
import json
from datetime import datetime
import traceback
import docker
import requests as _requests  # used only to catch ReadTimeout raised by the docker SDK
import uuid
import shutil

# Initialize the Docker client
try:
    docker_client = docker.from_env()
except Exception as e:
    print(f"Failed to connect to Docker daemon: {e}")
    docker_client = None

# ── Async job tracking table ─────────────────────────────────────────────────
# Structure: job_id -> {
#   "status": "running" | "done" | "failed" | "cancelled",
#   "result": dict | None,
#   "container": docker.Container | None,   # used for force-kill on cancel
#   "cancelled": bool,
# }
active_jobs: dict = {}

# --- FastAPI lifespan events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    # Clean up the exchange directory to avoid residual input.json files with runtime credentials from a previous crash.
    shutil.rmtree("/app/temp_exchange", ignore_errors=True)
    os.makedirs("/app/temp_exchange", exist_ok=True)
    yield

app = FastAPI(title="Robot Arm Algorithm Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)


def get_algorithm_config(algorithm_name: str) -> dict:
    """Load algorithm config; returns an empty dict on missing config to avoid blocking existing algorithms."""
    config_path = os.path.join(os.path.dirname(__file__), "algorithms", algorithm_name, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to read algorithm config {config_path}: {e}")
        return {}


def algorithm_requires_gpu(algorithm_name: str) -> bool:
    return bool(get_algorithm_config(algorithm_name).get("requires_gpu", False))

# --- Pydantic model definitions ---
class UnsimulatedRecordRequest(BaseModel):
    experiment_name: str = ""
    algorithm: str
    task_description: str = ""
    params: dict = {}
    code: str = ""
    notes: str = ""
    record_id: Optional[int] = None  # if provided, update the existing draft by ID
    parent_id: Optional[int] = None  # if provided, save as a branch draft under this root entry

class RunRequest(BaseModel):
    task_description: str = Field(..., description="Natural-language instruction from the user")
    num_blocks: int = Field(4, ge=0, le=10, description="Number of blocks in the scene")
    num_bowls: int = Field(4, ge=0, le=10, description="Number of bowls in the scene")
    openai_api_key: str = Field(..., description="OpenAI API Key")
    openai_base_url: str = Field(..., description="OpenAI API Base URL")
    selected_model: Optional[str] = "gpt-4-turbo"
    draft_id: int = None
    notes: str = None

class ApplyCodeRequest(BaseModel):
    code_to_run: str = Field(..., description="Code edited by the user to be executed")
    num_blocks: int = Field(4, ge=0, le=10, description="Number of blocks in the scene")
    num_bowls: int = Field(4, ge=0, le=10, description="Number of bowls in the scene")
    openai_api_key: str = Field(..., description="OpenAI API Key")
    openai_base_url: str = Field(..., description="OpenAI API Base URL")
    selected_model: Optional[str] = "gpt-4-turbo"
    create_new_record: bool = False
    task_description: str = None
    algorithm: str = None
    parent_id: Optional[int] = None  # if provided, write the new record as a child branch of this node
    notes: Optional[str] = None
    base_record_id: Optional[int] = None  # informational field retained for logging/debugging

class RenameRequest(BaseModel):
    new_name: str

class UpdateDescriptionRequest(BaseModel):
    new_description: str

class NotesRequest(BaseModel):
    notes: str

class CodeRequest(BaseModel):
    code: str = ""

class BranchRequest(BaseModel):
    parent_id: int
    experiment_name: str
    algorithm: str
    task_description: str = ""
    params: dict = {}
    code: str = ""
    notes: str = ""

class FinalizeRequest(BaseModel):
    node_id: int

class MarkFinalRequest(BaseModel):
    root_id: Optional[int] = None

class ModelListRequest(BaseModel):
    api_key: str
    base_url: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    api_key: str
    base_url: str
    model: str
    messages: list[ChatMessage]


SENSITIVE_PARAM_KEYS = {
    "openai_api_key",
    "openai_base_url",
    "api_key",
    "base_url",
}


def sanitize_params_for_history(params: dict) -> dict:
    """Remove credentials and endpoint settings before writing run params to history."""
    safe_params = {}
    for key, value in (params or {}).items():
        if key in SENSITIVE_PARAM_KEYS:
            continue
        safe_params[key] = value
    return safe_params


def preprocess_code_for_algorithm(algorithm_name: str, code_to_run: str) -> str:
    """
    Apply minimal compatibility preprocessing to user code without modifying algorithm internals.
    Currently only injects a robot compatibility shim for CAP (code_as_policies).
    """
    code = code_to_run or ""
    if algorithm_name not in {"code_as_policies", "cap"}:
        return code
    if "robot" not in code:
        return code

    compat_prelude = """
if 'robot' not in globals():
    class _RobotCompat:
        def pick_and_place(self, src, dst):
            return put_first_on_second(src, dst)
        def put_first_on_second(self, src, dst):
            return put_first_on_second(src, dst)
        def get_obj_pos(self, name):
            return get_obj_pos(name)
        def get_position(self, name):
            return get_obj_pos(name)
        def say(self, msg):
            return say(msg)
    robot = _RobotCompat()
""".strip()
    return f"{compat_prelude}\n\n{code}"


# ── Core logic: run an algorithm inside an isolated sibling container (with cancellation support) ─
def _run_in_container_tracked(algorithm_name: str, mode: str, params: dict, job_id: str) -> dict:
    """
    Equivalent to the original run_in_container, but stores the container reference in
    active_jobs[job_id]["container"] and polls a cancellation flag every 2 seconds so the
    frontend can abort the job at any time.
    """
    if not docker_client:
        return {"error": "Docker client not initialized.", "log": ""}

    image_name = f"algo_{algorithm_name.lower()}"

    try:
        docker_client.images.get(image_name)
    except docker.errors.ImageNotFound:
        return {"error": f"Algorithm image not found: {image_name}. Please build it first.", "log": ""}

    run_id = str(uuid.uuid4())
    host_exchange_base = os.environ.get("HOST_EXCHANGE_DIR")
    if not host_exchange_base:
        return {"error": "HOST_EXCHANGE_DIR environment variable not set.", "log": ""}

    host_exchange_dir = os.path.join(host_exchange_base, run_id)
    container_exchange_dir = f"/app/temp_exchange/{run_id}"

    os.makedirs(container_exchange_dir, exist_ok=True)

    input_data = {
        "mode": mode,
        "algorithm_name": algorithm_name,
        "params": params
    }
    with open(os.path.join(container_exchange_dir, "input.json"), "w") as f:
        json.dump(input_data, f)

    print(f"[job={job_id}] Starting container {image_name} for mode={mode}...")
    container = None
    try:
        env_vars = {
            "HF_ENDPOINT": "https://hf-mirror.com",
        }
        requires_gpu = algorithm_requires_gpu(algorithm_name)
        fallback_log = ""

        def _start_container(use_gpu: bool):
            run_kwargs = {
                "image": image_name,
                "volumes": {
                    host_exchange_dir: {'bind': '/exchange', 'mode': 'rw'}
                },
                "environment": env_vars,
                "detach": True,
                "network_mode": "host",
            }
            if use_gpu:
                run_kwargs["device_requests"] = [
                    docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])
                ]
            return docker_client.containers.run(**run_kwargs)

        if requires_gpu:
            try:
                container = _start_container(use_gpu=True)
            except Exception as gpu_err:
                fallback_log = f"GPU container failed to start, retrying in CPU-only mode: {gpu_err}"
                print(f"[job={job_id}] {fallback_log}")
                container = _start_container(use_gpu=False)
        else:
            container = _start_container(use_gpu=False)

        # Store the container reference so a cancel request can kill it
        if job_id in active_jobs:
            active_jobs[job_id]["container"] = container

        # Wait for the container to finish: poll every 2 seconds and check the cancellation flag
        exit_info = None
        while True:
            if active_jobs.get(job_id, {}).get("cancelled"):
                print(f"[job={job_id}] Cancellation signal detected, terminating container...")
                try:
                    container.kill()
                except Exception:
                    pass
                return {"error": "cancelled", "log": "Job cancelled by user."}

            try:
                # container.wait(timeout=2) raises ReadTimeout while the container is still running
                exit_info = container.wait(timeout=2)
                break  # container has finished
            except _requests.exceptions.ReadTimeout:
                continue  # timeout → container still running, keep polling
            except _requests.exceptions.ConnectionError:
                # Some docker SDK versions raise ConnectionError on timeout as well
                continue
            except Exception as wait_err:
                print(f"[job={job_id}] container.wait exception: {wait_err}")
                break

        if exit_info is None:
            exit_info = {"StatusCode": -1}

        exit_code = exit_info.get("StatusCode", -1)
        print(f"[job={job_id}] Container finished with exit code: {exit_code}")

        container_logs = container.logs().decode('utf-8')
        print(f"--- Container logs ---\n{container_logs}\n--- End of logs ---")

        output_file = os.path.join(container_exchange_dir, "output.json")
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                output_data = json.load(f)
            existing_log = output_data.get("log", "")
            if fallback_log:
                existing_log = f"{fallback_log}\n\n{existing_log}".strip()
            output_data["log"] = f"{existing_log}\n\n--- Container stdout ---\n{container_logs}"
        else:
            output_log = f"{fallback_log}\n\n{container_logs}".strip() if fallback_log else container_logs
            output_data = {"error": "Algorithm container did not produce output.json", "log": output_log}

        return output_data

    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"[job={job_id}] Container run error: {error_traceback}")
        logs = ""
        if container:
            try:
                logs = container.logs().decode('utf-8')
            except Exception:
                pass
        return {"error": str(e), "log": f"{error_traceback}\n\nContainer logs:\n{logs}"}
    finally:
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass
        if os.path.exists(container_exchange_dir):
            shutil.rmtree(container_exchange_dir, ignore_errors=True)
        # Clear the container reference to free memory
        if job_id in active_jobs:
            active_jobs[job_id]["container"] = None


def determine_status(result: dict, algorithm_name: Optional[str] = None) -> str:
    if "error" in result and result["error"]:
        return "failed"

    gen_code = result.get("generated_code", "")
    if gen_code and "# No valid code generated." in gen_code:
        result["error"] = "The LLM did not produce valid Python code."
        return "failed"

    video = result.get("video")
    if not video:
        if algorithm_name == "language_planner" and gen_code:
            result["video"] = "NO_VIDEO_SUPPORTED"
            return "success"
        result["error"] = "The simulation did not produce a video or animation."
        return "failed"

    return "success"


def determine_apply_code_status(result: dict, algorithm_name: Optional[str] = None) -> str:
    """Determine status when applying user code.

    Algorithms that support code replay (e.g. CAP) must execute successfully and produce a real video;
    text-planning and end-to-end algorithms may use sentinel values to indicate no video, but a non-empty
    error field still maps to failed.
    """
    if "error" in result and result["error"]:
        return "failed"

    video = result.get("video")
    video_capable_algorithms = {"code_as_policies", "cap"}
    if algorithm_name in video_capable_algorithms:
        if not video or video in {"NO_VIDEO_SUPPORTED", "E2E_NO_CODE_SUPPORTED"}:
            result["error"] = "Code executed but no playable video was generated. Check the run log for details."
            return "failed"
        return "success"

    if not video:
        result["video"] = "NO_VIDEO_SUPPORTED"
    return "success"


# ── Background async task: run the simulation and write to the database when done ──
async def _run_job(job_id: str, algorithm_name: str, mode: str, params: dict, record_data: Optional[dict]):
    """
    Runs the blocking container operation in a thread-pool executor to keep the event loop free.
    Updates active_jobs and writes to the history database when finished.
    """
    loop = asyncio.get_event_loop()

    def _blocking():
        return _run_in_container_tracked(algorithm_name, mode, params, job_id)

    try:
        result = await loop.run_in_executor(None, _blocking)
    except Exception as e:
        result = {"error": str(e), "log": traceback.format_exc()}

    job = active_jobs.get(job_id)
    if job is None:
        return

    # Do not write to the database when the job was cancelled
    if job.get("cancelled") or result.get("error") == "cancelled":
        job["status"] = "cancelled"
        job["result"] = {"error": "cancelled", "log": "Job cancelled by user."}
        return

    final_status = determine_status(result, algorithm_name)

    # Write to the database in the executor to avoid blocking the event loop
    if record_data is not None:
        def _save_db():
            result_for_db = result.copy()
            result_for_db.pop("video", None)
            record_data["status"] = final_status
            record_data["result"] = result_for_db
            return database.add_history_record(record_data)

        try:
            node_id = await loop.run_in_executor(None, _save_db)
            result["node_id"] = node_id
        except Exception as e:
            print(f"[job={job_id}] Database write failed: {e}")

    job["status"] = "done" if final_status == "success" else "failed"
    job["result"] = result
    print(f"[job={job_id}] Job finished with status: {job['status']}")


# --- API endpoints ---

@app.get("/")
def read_root():
    return {"message": "Backend service started successfully."}

@app.get("/algorithms")
def get_algorithms():
    if not docker_client:
        return {"algorithms": []}

    images = docker_client.images.list()
    algo_names = []
    for img in images:
        for tag in img.tags:
            if tag.startswith("algo_"):
                algo_names.append(tag.split(":")[0].replace("algo_", ""))
    return {"algorithms": list(set(algo_names))}


# ── Job status query ──────────────────────────────────────────────────────────
@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    job = active_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response: dict = {"status": job["status"]}
    if job["status"] in ("done", "failed", "cancelled"):
        response["result"] = job.get("result") or {}
    return response


# ── Job cancellation ──────────────────────────────────────────────────────────
@app.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    job = active_jobs.get(job_id)
    if job is None:
        return {"cancelled": False, "reason": "job not found"}

    if job["status"] != "running":
        return {"cancelled": False, "reason": f"job is already {job['status']}"}

    job["cancelled"] = True

    # If the container reference is already registered, kill it immediately
    container = job.get("container")
    if container:
        loop = asyncio.get_event_loop()
        def _kill():
            try:
                container.kill()
            except Exception as kill_err:
                print(f"[cancel] kill failed: {kill_err}")
        await loop.run_in_executor(None, _kill)

    print(f"[cancel] job_id={job_id} marked as cancelled")
    return {"cancelled": True}


# ── Run simulation (non-blocking, returns job_id immediately) ─────────────────
@app.post("/run/{algorithm_name}")
async def run_simulation(algorithm_name: str, request: RunRequest):
    job_id = str(uuid.uuid4())
    active_jobs[job_id] = {
        "status": "running",
        "result": None,
        "container": None,
        "cancelled": False,
    }
    print(
        f"[job={job_id}] Frontend selected: algorithm={algorithm_name}, "
        f"mode=run_algorithm, selected_model={request.selected_model}"
    )

    # Prepare the database record fields up front (excluding video)
    next_id_num = database.get_next_experiment_id()
    experiment_id = f"No.{next_id_num}"
    record_data = {
        "experiment_id": experiment_id,
        "experiment_name": request.task_description if request.task_description else experiment_id,
        "status": "failed",
        "algorithm": algorithm_name,
        "task_description": request.task_description,
        "params": sanitize_params_for_history(request.dict()),
        "result": {},
        "notes": request.notes,
    }

    # Run in the background without blocking the current request
    asyncio.create_task(_run_job(job_id, algorithm_name, "run_algorithm", request.dict(), record_data))

    return {"job_id": job_id, "status": "running"}


# ── Apply code and re-simulate (non-blocking) ──────────────────────────────────
@app.post("/apply_code/{algorithm_name}")
async def apply_code(algorithm_name: str, request: ApplyCodeRequest):
    job_id = str(uuid.uuid4())
    active_jobs[job_id] = {
        "status": "running",
        "result": None,
        "container": None,
        "cancelled": False,
    }
    print(
        f"[job={job_id}] Frontend selected: algorithm={algorithm_name}, "
        f"mode=run_from_code, selected_model={request.selected_model}"
    )

    payload = request.dict()
    payload["code_to_run"] = preprocess_code_for_algorithm(algorithm_name, request.code_to_run)

    record_data = None
    if request.create_new_record:
        algo_name_for_db = request.algorithm if request.algorithm else algorithm_name
        if request.parent_id is not None:
            # Create a simulated Apply-Code branch under an existing root entry.
            branch_name = f"Apply-Code-{database.get_next_apply_code_num(request.parent_id)}"
            record_data = {
                "experiment_id": branch_name,
                "experiment_name": branch_name,
                "status": "failed",
                "algorithm": algo_name_for_db,
                "task_description": request.task_description,
                "params": {
                    "num_blocks": request.num_blocks,
                    "num_bowls": request.num_bowls,
                },
                "result": {},
                "parent_id": request.parent_id,
                "node_type": "branch",
                "notes": request.notes or "",
            }
        else:
            # No root entry to attach to: create a standalone simulated Apply-Code root entry.
            experiment_id = f"Apply-Code-{database.get_next_apply_code_num()}"
            record_data = {
                "experiment_id": experiment_id,
                "experiment_name": experiment_id,
                "status": "failed",
                "algorithm": algo_name_for_db,
                "task_description": request.task_description,
                "params": {
                    "num_blocks": request.num_blocks,
                    "num_bowls": request.num_bowls,
                },
                "result": {},
                "notes": request.notes or "",
            }

    async def _apply_job(jid: str, algo: str, pl: dict, rd):
        """Background task for apply_code: writes the user code back into the result."""
        loop = asyncio.get_event_loop()

        def _blocking():
            return _run_in_container_tracked(algo, "run_from_code", pl, jid)

        try:
            result = await loop.run_in_executor(None, _blocking)
        except Exception as e:
            result = {"error": str(e), "log": traceback.format_exc()}

        job = active_jobs.get(jid)
        if job is None:
            return

        if job.get("cancelled") or result.get("error") == "cancelled":
            job["status"] = "cancelled"
            job["result"] = {"error": "cancelled", "log": "Job cancelled by user."}
            return

        # Write the user code back into the result envelope
        result["generated_code"] = request.code_to_run

        final_status = determine_apply_code_status(result, algo)

        if rd is not None:
            def _save_db():
                result_for_db = result.copy()
                result_for_db.pop("video", None)
                rd["status"] = final_status
                rd["result"] = result_for_db
                return database.add_history_record(rd)

            try:
                node_id = await loop.run_in_executor(None, _save_db)
                result["node_id"] = node_id
            except Exception as e:
                print(f"[job={jid}] Database write failed: {e}")

        job["status"] = "done" if final_status == "success" else "failed"
        job["result"] = result
        print(f"[job={jid}] apply_code finished with status: {job['status']}")

    asyncio.create_task(_apply_job(job_id, algorithm_name, payload, record_data))

    return {"job_id": job_id, "status": "running"}


# --- History record API ---
@app.get("/history")
def get_history():
    conn = database.get_db_connection()
    history_records = conn.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(row) for row in history_records]

@app.get("/history/{record_id:int}")
def get_history_record(record_id: int):
    conn = database.get_db_connection()
    record = conn.execute("SELECT * FROM history WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    if record is None:
        raise HTTPException(status_code=404, detail="History record not found")
    return dict(record)

@app.delete("/history/{record_id:int}")
def delete_history_record(record_id: int):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return {"message": f"Record {record_id} deleted successfully"}

@app.delete("/history")
def delete_all_history():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    conn.commit()
    conn.close()
    return {"message": "All history records deleted successfully"}

@app.put("/history/{record_id:int}/rename")
def rename_history_record(record_id: int, request: RenameRequest):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE history SET experiment_name = ? WHERE id = ?", (request.new_name, record_id))
    conn.commit()
    conn.close()
    return {"message": "Rename successful"}

@app.put("/history/{record_id:int}/description")
def update_history_description(record_id: int, request: UpdateDescriptionRequest):
    conn = database.get_db_connection()
    conn.execute(
        "UPDATE history SET task_description = ? WHERE id = ?",
        (request.new_description, record_id)
    )
    conn.commit()
    conn.close()
    return {"message": "Description updated successfully"}

@app.put("/history/{record_id:int}/notes")
def update_history_notes(record_id: int, request: NotesRequest):
    database.update_notes(record_id, request.notes)
    return {"message": "Notes updated successfully"}

@app.post("/history/{record_id:int}/code")
def update_history_code(record_id: int, request: CodeRequest):
    conn = database.get_db_connection()
    row = conn.execute("SELECT result FROM history WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="History record not found")

    try:
        result = json.loads(row["result"] or "{}")
    except Exception:
        result = {}
    result["generated_code"] = request.code or ""
    result["code"] = request.code or ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE history SET result = ?, timestamp = ? WHERE id = ?",
        (json.dumps(result), now, record_id),
    )
    conn.commit()
    conn.close()
    return {"message": "Code updated successfully", "id": record_id}

@app.get("/algorithms/{algorithm_name}/params")
def get_algorithm_params(algorithm_name: str):
    config_path = os.path.join("/app/algorithms", algorithm_name, "config.json")
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail="Algorithm config file not found.")
    with open(config_path, 'r') as f:
        return json.load(f)

@app.post("/history/draft")
def save_draft_record(request: UnsimulatedRecordRequest):
    conn = database.get_db_connection()
    params_str = json.dumps(request.params)
    result_str = json.dumps({"generated_code": request.code, "log": "This is a draft and has not been run yet."})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update by record_id if provided
    if request.record_id is not None:
        row = conn.execute("SELECT id, experiment_name FROM history WHERE id = ?", (request.record_id,)).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Draft record not found")
        node_type = "branch" if request.parent_id else "root"
        conn.execute(
            """
            UPDATE history
            SET task_description = ?, params = ?, result = ?, timestamp = ?,
                notes = ?, parent_id = ?, node_type = ?
            WHERE id = ?
            """,
            (
                request.task_description,
                params_str,
                result_str,
                now,
                request.notes,
                request.parent_id,
                node_type,
                request.record_id,
            ),
        )
        conn.commit()
        record_name = row["experiment_name"]
        conn.close()
        return {"message": "Draft updated successfully", "id": request.record_id, "name": record_name}

    # Deduplicate by name (legacy compatibility)
    existing = conn.execute(
        "SELECT id FROM history WHERE experiment_name = ?",
        (request.experiment_name,)
    ).fetchone()

    if existing:
        node_type = "branch" if request.parent_id else "root"
        conn.execute(
            """
            UPDATE history
            SET task_description = ?, params = ?, result = ?, timestamp = ?,
                notes = ?, parent_id = ?, node_type = ?
            WHERE id = ?
            """,
            (
                request.task_description,
                params_str,
                result_str,
                now,
                request.notes,
                request.parent_id,
                node_type,
                existing["id"],
            ),
        )
        record_id = existing["id"]
    else:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO history
                (experiment_id, experiment_name, status, algorithm, task_description,
                 timestamp, params, result, notes, parent_id, node_type, is_final)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.experiment_name,
                request.experiment_name,
                "unsimulated",
                request.algorithm,
                request.task_description,
                now,
                params_str,
                result_str,
                request.notes,
                request.parent_id,
                "branch" if request.parent_id else "root",
                0,
            ),
        )
        record_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return {"message": "Draft saved successfully", "id": record_id, "name": request.experiment_name}


@app.get("/history/tree")
def get_history_tree():
    """Return history records as a tree structure with child-node lists."""
    conn = database.get_db_connection()
    rows = conn.execute("SELECT * FROM history ORDER BY id ASC").fetchall()
    conn.close()

    nodes: dict[int, dict] = {}
    for row in rows:
        node = dict(row)
        node["children"] = []
        nodes[node["id"]] = node

    attached_ids: set[int] = set()
    for node in nodes.values():
        pid = node.get("parent_id")
        if pid and pid in nodes:
            nodes[pid]["children"].append(node)
            attached_ids.add(node["id"])

    for node in nodes.values():
        node["children"].sort(key=lambda child: child["id"])

    roots = [node for node in nodes.values() if node["id"] not in attached_ids]
    roots.sort(key=lambda node: node["id"], reverse=True)
    return roots


@app.post("/history/branch")
def create_branch(request: BranchRequest):
    """Create a branch draft record under the specified parent node."""
    conn = database.get_db_connection()

    parent = conn.execute("SELECT id FROM history WHERE id = ?", (request.parent_id,)).fetchone()
    if parent is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Parent node not found")

    params_str = json.dumps(request.params)
    result_str = json.dumps({"generated_code": request.code, "log": "This is a branch draft and has not been run yet."})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO history
            (experiment_id, experiment_name, status, algorithm, task_description,
             timestamp, params, result, notes, parent_id, node_type, is_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.experiment_name,
            request.experiment_name,
            "unsimulated",
            request.algorithm,
            request.task_description,
            now,
            params_str,
            result_str,
            request.notes,
            request.parent_id,
            "branch",
            0,
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return {"message": "Branch created", "id": new_id, "name": request.experiment_name}


@app.post("/history/finalize")
def finalize_node(request: FinalizeRequest):
    """Mark the specified node as the final version (★)."""
    conn = database.get_db_connection()
    row = conn.execute("SELECT id FROM history WHERE id = ?", (request.node_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Node not found")
    conn.execute("UPDATE history SET is_final = 1 WHERE id = ?", (request.node_id,))
    conn.commit()
    conn.close()
    return {"message": "Node finalized", "id": request.node_id}


@app.post("/history/{record_id:int}/mark-final")
def mark_branch_final(record_id: int, request: MarkFinalRequest):
    """Mark a branch node as final and overwrite the root entry code with its code."""
    conn = database.get_db_connection()
    branch = conn.execute("SELECT * FROM history WHERE id = ?", (record_id,)).fetchone()
    if branch is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Branch node not found")
    if not branch["parent_id"] and branch["node_type"] != "branch":
        conn.close()
        raise HTTPException(status_code=400, detail="Only branch nodes can be marked as final")

    root_id = request.root_id or branch["parent_id"]
    visited = set()
    while root_id:
        if root_id in visited:
            conn.close()
            raise HTTPException(status_code=400, detail="History tree has a circular parent reference")
        visited.add(root_id)
        root_row = conn.execute("SELECT id, parent_id FROM history WHERE id = ?", (root_id,)).fetchone()
        if root_row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="Root entry not found")
        if not root_row["parent_id"]:
            break
        root_id = root_row["parent_id"]

    if not root_id or root_id == record_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot determine the owning root entry")

    root = conn.execute("SELECT * FROM history WHERE id = ?", (root_id,)).fetchone()
    branch_result = json.loads(branch["result"] or "{}")
    root_result = json.loads(root["result"] or "{}")
    final_code = branch_result.get("generated_code") or branch_result.get("code") or ""
    root_result["generated_code"] = final_code
    if "code" in root_result or branch_result.get("code"):
        root_result["code"] = final_code

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE history SET is_final = 0 WHERE id = ? OR parent_id = ?", (root_id, root_id))
    conn.execute(
        """
        UPDATE history
        SET result = ?, algorithm = ?, task_description = ?, params = ?, notes = ?, timestamp = ?
        WHERE id = ?
        """,
        (
            json.dumps(root_result),
            branch["algorithm"],
            branch["task_description"],
            branch["params"],
            branch["notes"],
            now,
            root_id,
        ),
    )
    conn.execute("UPDATE history SET is_final = 1, parent_id = ?, node_type = 'branch' WHERE id = ?", (root_id, record_id))
    conn.commit()
    conn.close()
    return {"message": "Branch marked final and merged", "id": record_id, "root_id": root_id}


@app.post("/history/{record_id:int}/promote-main")
def promote_to_main(record_id: int):
    """Promote a branch node to a root entry (clears parent_id and sets node_type to root)."""
    conn = database.get_db_connection()
    row = conn.execute("SELECT id FROM history WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Node not found")
    conn.execute(
        "UPDATE history SET parent_id = NULL, node_type = 'root' WHERE id = ?",
        (record_id,),
    )
    conn.commit()
    conn.close()
    return {"message": "Promoted to main", "id": record_id}


@app.get("/next_id")
def get_next_id():
    next_id = database.get_next_experiment_id()
    return {"next_id": next_id}

@app.get("/next_draft_id")
def get_next_draft_id(parent_id: Optional[int] = None):
    next_num = database.get_next_draft_num(parent_id)
    return {"next_draft_name": f"Draft-{next_num}"}

@app.post("/models")
async def get_available_models(request: ModelListRequest):
    if not request.api_key or not request.base_url:
        return {"models": [], "error": "Missing API Key or Base URL"}

    try:
        print(f"Fetching model list, Base URL: {request.base_url}")
        loop = asyncio.get_event_loop()
        def _list_models():
            client = OpenAI(api_key=request.api_key, base_url=request.base_url, timeout=30)
            return client.models.list()
        models_response = await loop.run_in_executor(None, _list_models)
        model_ids = sorted([m.id for m in models_response.data])
        print(f"Successfully retrieved {len(model_ids)} models.")
        return {"models": model_ids}
    except Exception as e:
        import traceback
        print(f"Failed to fetch model list:\n{traceback.format_exc()}")
        return {"models": [], "error": str(e)}


@app.post("/chat")
async def chat_completion(request: ChatRequest):
    if not request.api_key or not request.base_url:
        return JSONResponse(status_code=400, content={"detail": "Missing API Key or Base URL"})
    if not request.model:
        return JSONResponse(status_code=400, content={"detail": "Missing model name"})
    if not request.messages:
        return JSONResponse(status_code=400, content={"detail": "Messages cannot be empty"})

    try:
        loop = asyncio.get_event_loop()
        def _chat():
            client = OpenAI(api_key=request.api_key, base_url=request.base_url, timeout=90)
            return client.chat.completions.create(
                model=request.model,
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
            )
        completion = await loop.run_in_executor(None, _chat)
        reply = ""
        if completion.choices and completion.choices[0].message:
            reply = completion.choices[0].message.content or ""
        return {"reply": reply}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Chat request failed: {e}"})

import os
import sys
import io
import base64
import traceback
import subprocess
import glob
import shutil

ALGORITHM_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
VIDEO_PLACEHOLDER = "E2E_NO_CODE_SUPPORTED"

def run_algorithm(params: dict):
    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"generated_code": "", "video": "", "log": ""}

    try:
        print("--- CLIPort starting ---")
        
        eval_task = params.get('task_description', 'stack-block-pyramid-seq-seen-colors')
        model_task = params.get('model_task', 'multi-language-conditioned')
        n_demos = params.get('n_demos', 1)
        
        exp_folder = "exps" 
        
        print(f"Eval task: {eval_task}")
        print(f"Model task: {model_task}")
        print(f"Number of demos: {n_demos}")

        # Environment variables setup
        env = os.environ.copy()
        if "CUDA_VISIBLE_DEVICES" in env:
            del env["CUDA_VISIBLE_DEVICES"]
            
        # Fix cuSOLVER initialization failure on WSL2
        env["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:32"
        # ==========================================
        # 1. Auto-generate test dataset
        # ==========================================
        dataset_dir = os.path.join(ALGORITHM_ROOT_PATH, "data", f"{eval_task}-test")
        if not os.path.exists(dataset_dir) or len(os.listdir(dataset_dir)) < n_demos:
            print(f"\n>>> No sufficient test data found. Generating {n_demos} test scene(s) for {eval_task}...")
            demo_command = [
                "python3", "cliport/demos.py",
                f"n={n_demos}",
                f"task={eval_task}",
                "mode=test",
                "disp=False"
            ]
            demo_process = subprocess.run(
                demo_command,
                cwd=ALGORITHM_ROOT_PATH,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                env=env
            )
            print(demo_process.stdout)
            if demo_process.returncode != 0:
                raise RuntimeError(f"Test data generation failed, exit code: {demo_process.returncode}")
            print(">>> Test data generation complete.\n")
        else:
            print(f">>> Existing test dataset found, skipping generation.\n")

        # ==========================================
        # 2. Fix missing last.ckpt (for other tasks)
        # ==========================================
        ckpt_dir = os.path.join(ALGORITHM_ROOT_PATH, exp_folder, f"{model_task}-cliport-n1000-train", "checkpoints")
        last_ckpt_path = os.path.join(ckpt_dir, "last.ckpt")
        
        if os.path.exists(ckpt_dir) and not os.path.exists(last_ckpt_path):
            # Find any .ckpt file in the directory
            existing_ckpts = glob.glob(os.path.join(ckpt_dir, "*.ckpt"))
            if existing_ckpts:
                source_ckpt = existing_ckpts[0]
                print(f">>> Copying {os.path.basename(source_ckpt)} as last.ckpt for task {eval_task} compatibility")
                shutil.copy(source_ckpt, last_ckpt_path)

        # ==========================================
        # 3. Run evaluation script
        # ==========================================
        print(">>> Starting model evaluation and video recording, please wait...")
        command = [
            "python3", "cliport/eval.py",
            f"model_task={model_task}",
            f"eval_task={eval_task}",
            "agent=cliport",
            "mode=test",
            f"n_demos={n_demos}",
            "train_demos=1000",
            f"exp_folder={exp_folder}",
            "checkpoint_type=test_best",
            "update_results=True",
            "disp=False",
            "record.save_video=True"
        ]

        process = subprocess.Popen(
            command,
            cwd=ALGORITHM_ROOT_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            env=env
        )

        for line in process.stdout:
            print(line, end='')
            sys.stdout.flush()

        process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"CLIPort evaluation script failed, exit code: {process.returncode}")

        print("Evaluation script finished.")

        # ==========================================
        # 4. Locate generated video file
        # ==========================================
        expected_video_dir = os.path.join(ALGORITHM_ROOT_PATH, exp_folder, f"{eval_task}-cliport-n1000-train", "videos")
        candidate_patterns = [
            os.path.join(expected_video_dir, "*.mp4"),
            os.path.join(ALGORITHM_ROOT_PATH, exp_folder, "**", "videos", "*.mp4"),
            os.path.join(ALGORITHM_ROOT_PATH, "data", "**", "videos", "*.mp4"),
        ]
        mp4_files = []
        for pattern in candidate_patterns:
            mp4_files.extend(glob.glob(pattern, recursive=True))

        if mp4_files:
            latest_video = max(set(mp4_files), key=os.path.getctime)
            print(f"Video found: {latest_video}")
            with open(latest_video, "rb") as f:
                result["video"] = base64.b64encode(f.read()).decode('utf-8')
        else:
            print(f"Warning: no video file found. Primary search directory: {expected_video_dir}")

        algo_name = os.path.basename(ALGORITHM_ROOT_PATH)
        result["generated_code"] = f"# {algo_name} is an end-to-end model; no intermediate code is generated.\n# See the run log for evaluation details."

    except Exception as e:
        print(f"!!! Algorithm execution error !!!\n{traceback.format_exc()}")
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
        print("--- Run finished ---")
    
    return result

# ==========================================
# run_from_code: not supported for end-to-end models
# ==========================================
def run_from_code(params: dict):
    algo_name = os.path.basename(ALGORITHM_ROOT_PATH)
    return {
        "video": VIDEO_PLACEHOLDER,
        "log": (
            f"--- Intercept notice ---\n"
            f"{algo_name} is an end-to-end model that directly outputs low-level actions "
            f"and does not support re-execution via code modification.\n"
            f'Please adjust parameters in the left panel and click "Run Simulation".'
        )
    }

import os
import sys
import io
import base64
import traceback
import subprocess
import glob
import shutil  # 新增：用于复制文件

ALGORITHM_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
VIDEO_PLACEHOLDER = "E2E_NO_CODE_SUPPORTED"

def run_algorithm(params: dict):
    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"generated_code": "", "video": "", "log": ""}

    try:
        print("--- CLIPort 开始运行 ---")
        
        eval_task = params.get('task_description', 'stack-block-pyramid-seq-seen-colors')
        model_task = params.get('model_task', 'multi-language-conditioned')
        n_demos = params.get('n_demos', 1)
        
        exp_folder = "exps" 
        
        print(f"评估任务 (eval_task): {eval_task}")
        print(f"模型类型 (model_task): {model_task}")
        print(f"评估数量 (n_demos): {n_demos}")

        # 强制使用 CPU 的环境变量设置
        env = os.environ.copy()
        if "CUDA_VISIBLE_DEVICES" in env:
            del env["CUDA_VISIBLE_DEVICES"]
            
        # --- 核心修正：修复 WSL2 下 cuSOLVER 初始化失败的 Bug ---
        env["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:32"
        # ==========================================
        # 1. 自动生成测试数据集
        # ==========================================
        dataset_dir = os.path.join(ALGORITHM_ROOT_PATH, "data", f"{eval_task}-test")
        if not os.path.exists(dataset_dir) or len(os.listdir(dataset_dir)) < n_demos:
            print(f"\n>>> 未找到足够的测试数据，正在动态生成 {n_demos} 个 {eval_task} 的测试场景...")
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
                raise RuntimeError(f"测试数据生成失败，退出码: {demo_process.returncode}")
            print(">>> 测试数据生成完毕！\n")
        else:
            print(f">>> 发现已存在的测试数据集，跳过生成步骤。\n")

        # ==========================================
        # 2. 修复缺失 last.ckpt 的问题 (适配其他任务)
        # ==========================================
        ckpt_dir = os.path.join(ALGORITHM_ROOT_PATH, exp_folder, f"{model_task}-cliport-n1000-train", "checkpoints")
        last_ckpt_path = os.path.join(ckpt_dir, "last.ckpt")
        
        if os.path.exists(ckpt_dir) and not os.path.exists(last_ckpt_path):
            # 找到目录下任意一个 .ckpt 文件
            existing_ckpts = glob.glob(os.path.join(ckpt_dir, "*.ckpt"))
            if existing_ckpts:
                source_ckpt = existing_ckpts[0]
                print(f">>> 为兼容 {eval_task} 任务，自动将 {os.path.basename(source_ckpt)} 复制为 last.ckpt")
                shutil.copy(source_ckpt, last_ckpt_path)

        # ==========================================
        # 3. 运行评估脚本
        # ==========================================
        print(">>> 开始执行模型评估并录制视频，请耐心等待...")
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
            raise RuntimeError(f"CLIPort 评估脚本执行失败，退出码: {process.returncode}")

        print("评估脚本执行完成。")

        # ==========================================
        # 4. 寻找生成的视频文件
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
            print(f"找到生成的视频: {latest_video}")
            with open(latest_video, "rb") as f:
                result["video"] = base64.b64encode(f.read()).decode('utf-8')
        else:
            print(f"警告: 未找到视频文件。优先检查目录: {expected_video_dir}")

        # 自动获取当前算法的文件夹名称
        algo_name = os.path.basename(ALGORITHM_ROOT_PATH)
        result["generated_code"] = f"# {algo_name} 是端到端模型，不生成中间代码。\n# 请查看日志了解评估详情。"

    except Exception as e:
        print(f"!!! 算法执行出错 !!!\n{traceback.format_exc()}")
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
        print("--- 运行结束 ---")
    
    return result

# ==========================================
# 补齐缺失的 run_from_code 函数
# ==========================================
def run_from_code(params: dict):
    algo_name = os.path.basename(ALGORITHM_ROOT_PATH)
    return {
        "video": VIDEO_PLACEHOLDER, 
        "log": f"--- 拦截提示 ---\n{algo_name} 是端到端模型，直接输出底层动作，不支持通过修改代码来重新执行。\n请在左侧修改参数后点击“运行模拟”。"
    }
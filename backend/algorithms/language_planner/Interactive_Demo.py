#Interactive_Demo.py(language_planner)
import sys
import os
import io
import json
import traceback
import time
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from sentence_transformers import util as st_utils
from openai import OpenAI

# --- 路径设置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.append(src_dir)

# --- 视频占位符 (Base64编码的一张图片，显示"No Video Available") ---
# 这里为了简洁，使用一个简单的文本提示代替图片Base64，前端会处理
VIDEO_PLACEHOLDER = "NO_VIDEO_SUPPORTED"

# --- 全局缓存 ---
translation_lm = None
action_list = None
action_list_embedding = None
available_examples = None
example_task_list = None
example_task_embedding = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def initialize_resources():
    """初始化 SentenceTransformer 和本地数据"""
    global translation_lm, action_list, action_list_embedding
    global available_examples, example_task_list, example_task_embedding
    
    if translation_lm is not None:
        return

    print("正在初始化 Translation LM (用于语义匹配)...")
    # 使用一个较小的模型以加快加载速度
    translation_lm_id = 'all-MiniLM-L6-v2' 
    translation_lm = SentenceTransformer(translation_lm_id).to(device)

    print("正在加载动作列表和示例库...")
    with open(os.path.join(src_dir, 'available_actions.json'), 'r') as f:
        action_list = json.load(f)
    action_list_embedding = translation_lm.encode(action_list, batch_size=512, convert_to_tensor=True, device=device)

    with open(os.path.join(src_dir, 'available_examples.json'), 'r') as f:
        available_examples = json.load(f)
    example_task_list = [example.split('\n')[0] for example in available_examples]
    example_task_embedding = translation_lm.encode(example_task_list, batch_size=512, convert_to_tensor=True, device=device)
    print("资源初始化完成。")

def find_most_similar(query_str, corpus_embedding):
    query_embedding = translation_lm.encode(query_str, convert_to_tensor=True, device=device)
    cos_scores = st_utils.pytorch_cos_sim(query_embedding, corpus_embedding)[0].detach().cpu().numpy()
    most_similar_idx, matching_score = np.argmax(cos_scores), np.max(cos_scores)
    return most_similar_idx, matching_score

def run_algorithm(params: dict):
    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"generated_code": "", "video": "", "log": ""}

    try:
        # 1. 获取参数和API凭证
        task = params.get('task_description', 'Make breakfast')
        api_key = params.get('openai_api_key')
        base_url = params.get('openai_base_url')
        selected_model = params.get('selected_model', 'gpt-4-turbo') # 获取选择的模型

        if not api_key or not base_url:
            raise ValueError("需要提供 API Key 和 Base URL 来运行此算法。")

        # 初始化新版 OpenAI 客户端
        client = OpenAI(api_key=api_key, base_url=base_url)

        print(f"--- Language Planner 开始运行 ---")
        print(f"任务: {task}")
        print(f"使用模型: {selected_model}")

        # 2. 初始化本地资源
        initialize_resources()

        # 3. 寻找最相似示例 (In-Context Learning)
        example_idx, _ = find_most_similar(task, example_task_embedding)
        example = available_examples[example_idx]
        
        # 构建 Prompt
        # 注意：原算法是自回归生成的(一步一步生成)，为了适配 Chat 接口，
        # 我们将其简化为一次性生成整个计划，或者需要在一个循环中调用 Chat API。
        # 这里为了效率和稳定性，我们采用一次性生成，并让模型遵循格式。
        
        system_prompt = """
        You are a robot planning agent. 
        Your task is to generate a step-by-step action plan for a household task.
        Use the provided example as a guide for the format.
        Each step should be a simple action description.
        """
        
        user_prompt = f"""
        Example Task and Plan:
        {example}

        Now, generate a plan for the following task:
        Task: {task}
        """

        print("正在调用大模型生成计划...")
        response = client.chat.completions.create(
            model=selected_model, # 使用用户选择的模型
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=256
        )
        
        raw_plan = response.choices[0].message.content
        print("大模型返回原始计划。")

        # 4. 将生成的文本映射到可用动作 (Translation)
        # 原算法的核心步骤：确保生成的每一步都在 available_actions.json 中
        print("正在将计划映射到可执行动作...")
        final_plan_lines = []
        for line in raw_plan.split('\n'):
            line = line.strip()
            if not line or line.startswith('Task:'): continue
            
            # 去掉 "Step 1: " 这样的前缀
            action_text = line.split(': ')[-1] if ': ' in line else line
            
            # 找到最相似的预定义动作
            idx, score = find_most_similar(action_text, action_list_embedding)
            matched_action = action_list[idx]
            
            final_plan_lines.append(f"# Original: {action_text} -> Mapped: {matched_action}")
            # 这里我们生成伪代码形式
            final_plan_lines.append(f"robot.execute('{matched_action}')")

        result["generated_code"] = "\n".join(final_plan_lines)
        print("规划完成。")
        
        # 5. 设置视频状态
        result["video"] = VIDEO_PLACEHOLDER

    except Exception as e:
        print(f"!!! 算法执行出错 !!!")
        print(traceback.format_exc())
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
        print("--- 运行结束 ---")
    
    return result

def run_from_code(params: dict):
    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"video": "", "log": ""}
    
    try:
        code_to_run = params.get('code_to_run')
        print("--- 执行生成的计划 ---")
        print("正在解析并执行指令...")
        
        # 模拟执行过程
        for line in code_to_run.split('\n'):
            if line.startswith("robot.execute"):
                action = line.split("'")[1]
                print(f"Executing: {action}")
                time.sleep(0.5) # 模拟耗时
        
        print("执行完毕。")
        result["video"] = VIDEO_PLACEHOLDER
        
    except Exception as e:
        print(f"执行出错: {e}")
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
    
    return result

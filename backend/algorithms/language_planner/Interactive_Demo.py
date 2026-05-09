#Interactive_Demo.py (language_planner)
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

# --- Path setup ---
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.append(src_dir)

# --- Video placeholder (signals to the frontend that this algorithm produces no video) ---
# The frontend detects the NO_VIDEO_SUPPORTED sentinel and suppresses the video panel.
VIDEO_PLACEHOLDER = "NO_VIDEO_SUPPORTED"

# --- Global cache ---
translation_lm = None
action_list = None
action_list_embedding = None
available_examples = None
example_task_list = None
example_task_embedding = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def initialize_resources():
    """Initialize SentenceTransformer and local data."""
    global translation_lm, action_list, action_list_embedding
    global available_examples, example_task_list, example_task_embedding
    
    if translation_lm is not None:
        return

    print("Initializing Translation LM (for semantic matching)...")
    # Use a small model to speed up loading
    translation_lm_id = 'all-MiniLM-L6-v2' 
    translation_lm = SentenceTransformer(translation_lm_id).to(device)

    print("Loading action list and example library...")
    with open(os.path.join(src_dir, 'available_actions.json'), 'r') as f:
        action_list = json.load(f)
    action_list_embedding = translation_lm.encode(action_list, batch_size=512, convert_to_tensor=True, device=device)

    with open(os.path.join(src_dir, 'available_examples.json'), 'r') as f:
        available_examples = json.load(f)
    example_task_list = [example.split('\n')[0] for example in available_examples]
    example_task_embedding = translation_lm.encode(example_task_list, batch_size=512, convert_to_tensor=True, device=device)
    print("Resource initialization complete.")

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
        # 1. Get parameters and API credentials
        task = params.get('task_description', 'Make breakfast')
        api_key = params.get('openai_api_key')
        base_url = params.get('openai_base_url')
        selected_model = params.get('selected_model', 'gpt-4-turbo')

        if not api_key or not base_url:
            raise ValueError("API Key and Base URL are required to run this algorithm.")

        # Initialize OpenAI client
        client = OpenAI(api_key=api_key, base_url=base_url)

        print(f"--- Language Planner starting ---")
        print(f"Task: {task}")
        print(f"Model: {selected_model}")

        # 2. Initialize local resources
        initialize_resources()

        # 3. Find the most similar in-context example (In-Context Learning)
        example_idx, _ = find_most_similar(task, example_task_embedding)
        example = available_examples[example_idx]
        
        # Build prompt.
        # The original algorithm generates plans auto-regressively (step by step).
        # Here we simplify to a single LLM call that generates the entire plan at once,
        # with the model instructed to follow the example format.
        
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

        print("Calling LLM to generate plan...")
        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=256
        )
        
        raw_plan = response.choices[0].message.content
        print("LLM returned raw plan.")

        # 4. Map generated text to available actions (Translation step)
        # Core step of the original algorithm: ensure each generated step is in available_actions.json.
        print("Mapping plan to executable actions...")
        final_plan_lines = []
        for line in raw_plan.split('\n'):
            line = line.strip()
            if not line or line.startswith('Task:'): continue
            
            # Strip "Step 1: " style prefixes
            action_text = line.split(': ')[-1] if ': ' in line else line
            
            # Find the most similar predefined action via cosine similarity
            idx, score = find_most_similar(action_text, action_list_embedding)
            matched_action = action_list[idx]
            
            final_plan_lines.append(f"# Original: {action_text} -> Mapped: {matched_action}")
            # Generate pseudocode form
            final_plan_lines.append(f"robot.execute('{matched_action}')")

        result["generated_code"] = "\n".join(final_plan_lines)
        print("Planning complete.")
        
        # 5. Set video status (no video for text-planning algorithms)
        result["video"] = VIDEO_PLACEHOLDER

    except Exception as e:
        print(f"!!! Algorithm execution error !!!")
        print(traceback.format_exc())
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
        print("--- Run finished ---")
    
    return result

def run_from_code(params: dict):
    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"video": "", "log": ""}
    
    try:
        code_to_run = params.get('code_to_run')
        print("--- Executing generated plan ---")
        print("Parsing and executing instructions...")
        
        # Simulate execution
        for line in code_to_run.split('\n'):
            if line.startswith("robot.execute"):
                action = line.split("'")[1]
                print(f"Executing: {action}")
                time.sleep(0.5)
        
        print("Execution complete.")
        result["video"] = VIDEO_PLACEHOLDER
        
    except Exception as e:
        print(f"Execution error: {e}")
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
    
    return result

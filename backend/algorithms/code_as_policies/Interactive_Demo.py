# -*- coding: utf-8 -*-
#Interactive_Demo.py（code as policies)
import os
import sys
import io
import base64
import copy
from time import sleep
import traceback
import ast
import astunparse

from sim_env.setup import PickPlaceEnv
from Robotics.arm import Robotiq2F85
from config.constants import ALL_BLOCKS, ALL_BOWLS
from LMP.LMP_config import cfg_tabletop, lmp_tabletop_coords
from LMP.LMP_Wrapper import LMP_wrapper
from LMP.FunctionParser import FunctionParser, var_exists

import numpy as np
import pybullet
import pybullet_data
from moviepy.editor import ImageSequenceClip
import shapely
from shapely.geometry import *
from shapely.affinity import *
from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

# --- Global variable: currently active model name ---
CURRENT_MODEL_NAME = "gpt-4-turbo"

# ==============================================================================
# --- Core class definitions ---
# ==============================================================================

class LMP:
    def __init__(self, name, cfg, lmp_fgen, fixed_vars, variable_vars, client):
        self._name = name; self._cfg = cfg; self.client = client
        self._base_prompt = self._cfg['prompt_text']; self._stop_tokens = list(self._cfg['stop'])
        self._lmp_fgen = lmp_fgen; self._fixed_vars = fixed_vars
        self._variable_vars = variable_vars; self.exec_hist = ''

    def __call__(self, query, context='', **kwargs):
        prompt, use_query = self._build_prompt(query, context)
        while True:
            try:
                if client is None: raise ValueError("OpenAI client not initialized.")
                code_str = client.chat.completions.create(
                    model='gpt-4-turbo', # or use the globally configured model variable
                    messages=[{"role": "user", "content": prompt}],
                    stop=self._stop_tokens, temperature=self._cfg['temperature'],
                    max_tokens=self._cfg['max_tokens'], timeout=30.0
                ).choices[0].message.content
                break
            except APITimeoutError as e: raise e
            except (RateLimitError, APIConnectionError) as e: print(f'API Error: {e}, retrying...'); sleep(10)
        
        # Strip markdown fences and filter non-code lines from the model reply
        import re
        # Try to extract a Markdown code block
        match = re.search(r'```(?:python)?(.*?)```', code_str, re.DOTALL)
        if match:
            clean_code = match.group(1).strip()
        else:
            # Fall back to a simple line-by-line filter
            lines = code_str.split('\n')
            clean_lines = []
            for line in lines:
                stripped_line = line.strip()
                if stripped_line.lower().startswith(("here is", "sure", "ok", "the code", "this script")):
                    continue
                if '=' in line or '(' in line or line.startswith(('def ', 'import ', 'from ', 'print', 'say', 'put_', 'objects', '#', '    ', '\t')) or not stripped_line:
                    clean_lines.append(line)
            clean_code = '\n'.join(clean_lines).strip()
            if not clean_code:
                print("Warning: no valid code could be extracted from the model reply!")
                clean_code = "# No valid code generated."

        print(f"--- Raw reply ---\n{code_str}\n--- Cleaned code ---\n{clean_code}\n----------------")
        
        # Proceed with the cleaned code
        to_exec = f'{context}\n{clean_code}' if self._cfg['include_context'] and context else clean_code
        new_fs = self._lmp_fgen.create_new_fs_from_code(clean_code) 
        self._variable_vars.update(new_fs)
        gvars = merge_dicts([self._fixed_vars, self._variable_vars])
        
        # Catch execution errors before propagating
        try:
            exec_safe(to_exec, gvars, kwargs)
        except Exception as e:
            print(f"Error executing generated code: {e}")
            print(f"Code attempted:\n{to_exec}")
            raise e

        self.exec_hist += f'\n{to_exec}'
        if self._cfg['maintain_session']: self._variable_vars.update(kwargs)
        if self._cfg['has_return']: return kwargs[self._cfg['return_val_name']]

    def _build_prompt(self, query, context=''):
        prompt = self._cfg['prompt_text']
        if self._cfg['maintain_session']: prompt += f'\n{self.exec_hist}'
        if context: prompt += f'\n{context}'
        use_query = f'{self._cfg["query_prefix"]}{query}{self._cfg["query_suffix"]}'
        prompt += f'\n{use_query}'
        return prompt, use_query

class LMPFGen:
    def __init__(self, cfg, fixed_vars, variable_vars, client):
        self._cfg = cfg; self.client = client; self._stop_tokens = list(self._cfg['stop'])
        self._fixed_vars = fixed_vars; self._variable_vars = variable_vars
        self._base_prompt = self._cfg['prompt_text']

    def create_f_from_sig(self, f_name, f_sig, other_vars=None, fix_bugs=False, return_src=False):
        prompt = f'{self._base_prompt}\n{self._cfg["query_prefix"]}{f_sig}{self._cfg["query_suffix"]}'
        while True:
            try:
                if self.client is None: raise ValueError("OpenAI client not initialized.")
                f_src = self.client.chat.completions.create(
                    model=CURRENT_MODEL_NAME, messages=[{"role": "user", "content": prompt}],
                    stop=self._stop_tokens, temperature=self._cfg['temperature'],
                    max_tokens=self._cfg['max_tokens'], timeout=30.0
                ).choices[0].message.content
                break
            except APITimeoutError as e: raise e    
            except (RateLimitError, APIConnectionError) as e: print(f'API Error: {e}, retrying...'); sleep(10)
        
        if other_vars is None: other_vars = {}
        gvars = merge_dicts([self._fixed_vars, self._variable_vars, other_vars])
        lvars = {}
        exec_safe(f_src, gvars, lvars)
        f = lvars[f_name]
        if return_src: return f, f_src
        return f

    def create_new_fs_from_code(self, code_str, other_vars=None, fix_bugs=False, return_src=False):
        fs, f_assigns = {}, {}
        try:
            parsed_code = ast.parse(code_str)
        except SyntaxError:
            print("Warning: model reply is not valid Python code; cannot parse functions.")
            return {}
        FunctionParser(fs, f_assigns).visit(parsed_code)
        for f_name, f_assign in f_assigns.items():
            if f_name in fs: fs[f_name] = f_assign
        if other_vars is None: other_vars = {}
        new_fs, srcs = {}, {}
        for f_name, f_sig in fs.items():
            all_vars = merge_dicts([self._fixed_vars, self._variable_vars, new_fs, other_vars])
            if not var_exists(f_name, all_vars):
                f, f_src = self.create_f_from_sig(f_name, f_sig, new_fs, fix_bugs=fix_bugs, return_src=True)
                try:
                    f_def_body = astunparse.unparse(ast.parse(f_src).body[0].body)
                    child_fs, child_f_srcs = self.create_new_fs_from_code(f_def_body, other_vars=all_vars, fix_bugs=fix_bugs, return_src=True)
                    if child_fs:
                        new_fs.update(child_fs); srcs.update(child_f_srcs)
                        gvars = merge_dicts([self._fixed_vars, self._variable_vars, new_fs, other_vars])
                        lvars = {}
                        exec_safe(f_src, gvars, lvars)
                        f = lvars[f_name]
                except (SyntaxError, IndexError):
                    pass # Ignore if the generated function body is not valid python
                new_fs[f_name], srcs[f_name] = f, f_src
        if return_src: return new_fs, srcs
        return new_fs

# ==============================================================================
# --- Global variables and helper functions ---
# ==============================================================================
ALGORITHM_ROOT_PATH = os.path.dirname(os.path.abspath(__file__))

def merge_dicts(dicts): return {k: v for d in dicts for k, v in d.items()}
def exec_safe(code_str, gvars=None, lvars=None):
    if gvars is None: gvars = {}
    if lvars is None: lvars = {}
    custom_gvars = merge_dicts([gvars, {'exec': lambda: None, 'eval': lambda: None}])
    exec(code_str, custom_gvars, lvars)

def setup_exec_env(env, cfg, client_instance):
    cfg_copy = copy.deepcopy(cfg)
    cfg_copy['env'] = {'init_objs': list(env.obj_name_to_id.keys()), 'coords': lmp_tabletop_coords}
    LMP_env = LMP_wrapper(env, cfg_copy)
    fixed_vars = {'np': np, **{name: eval(name) for name in shapely.geometry.__all__ + shapely.affinity.__all__}}
    variable_vars = {k: getattr(LMP_env, k) for k in ['get_bbox', 'get_obj_pos', 'get_color', 'is_obj_visible', 'denormalize_xy', 'put_first_on_second', 'get_obj_names', 'get_corner_name', 'get_side_name']}
    variable_vars['say'] = lambda msg: print(f'robot says: {msg}')
    lmp_fgen = LMPFGen(cfg_copy['lmps']['fgen'], fixed_vars, variable_vars, client_instance)
    for lmp_name in ['parse_obj_name', 'parse_position', 'parse_question', 'transform_shape_pts']:
        variable_vars[lmp_name] = LMP(lmp_name, cfg_copy['lmps'][lmp_name], lmp_fgen, fixed_vars, variable_vars, client_instance)
    return merge_dicts([fixed_vars, variable_vars])

def setup_LMP(env, cfg, client_instance):
    gvars = setup_exec_env(env, cfg, client_instance)
    # Retrieve the already-initialized lmp_fgen from gvars
    lmp_fgen = gvars['parse_obj_name']._lmp_fgen
    lmp_tabletop_ui = LMP('tabletop_ui', cfg['lmps']['tabletop_ui'], lmp_fgen, gvars, gvars, client_instance)
    return lmp_tabletop_ui

# ==============================================================================
# --- API functions ---
# ==============================================================================
def run_algorithm(params: dict):
    global CURRENT_MODEL_NAME
    CURRENT_MODEL_NAME = params.get('selected_model', 'gpt-4-turbo')
    
    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"generated_code": "", "video": "", "log": ""}
    env = None
    try:
        api_key = params.get('openai_api_key')
        base_url = params.get('openai_base_url')
        if not (api_key and base_url): raise ValueError("API Key or Base URL not provided.")
        local_client = OpenAI(api_key=api_key, base_url=base_url)
        
        print("--- [New Simulation] Starting ---")
        user_input = params.get('task_description')
        num_blocks = params.get('num_blocks', 4)
        num_bowls = params.get('num_bowls', 3)

        if pybullet.isConnected():
            try: pybullet.disconnect()
            except pybullet.error: pass
        pybullet.connect(pybullet.DIRECT)
        pybullet.setAdditionalSearchPath(pybullet_data.getDataPath())
        pybullet.setAdditionalSearchPath(ALGORITHM_ROOT_PATH)

        env = PickPlaceEnv(asset_path=ALGORITHM_ROOT_PATH, render=True)
        
        np.random.seed(42) 
        obj_list = np.random.choice(ALL_BLOCKS, size=num_blocks, replace=False).tolist() + \
                   np.random.choice(ALL_BOWLS, size=num_bowls, replace=False).tolist()
        env.reset(obj_list)
        
        lmp_tabletop_ui = setup_LMP(env, cfg_tabletop, local_client)

        print('Available objects:', obj_list)
        lmp_tabletop_ui(user_input, f'objects = {env.object_list}')
        
        if hasattr(lmp_tabletop_ui, 'exec_hist') and lmp_tabletop_ui.exec_hist:
            result["generated_code"] = lmp_tabletop_ui.exec_hist.split(user_input + '.')[-1].strip()

        if env.cache_video:
            video_path = "/tmp/simulation_video.mp4"
            ImageSequenceClip(env.cache_video, fps=25).write_videofile(video_path, codec='libx264', logger=None)
            with open(video_path, "rb") as f:
                result["video"] = base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"!!! Algorithm execution error !!!\n{traceback.format_exc()}")
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
        if env is not None and pybullet.isConnected(): pybullet.disconnect()
    return result

def run_from_code(params: dict):
    global CURRENT_MODEL_NAME
    CURRENT_MODEL_NAME = params.get('selected_model', 'gpt-4-turbo')

    log_stream = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = log_stream
    result = {"video": "", "log": ""}
    env = None
    try:
        print("--- [Apply Code] Starting ---")
        code_to_run = params.get('code_to_run')
        num_blocks = params.get('num_blocks', 4)
        num_bowls = params.get('num_bowls', 3)
        api_key = params.get('openai_api_key')
        base_url = params.get('openai_base_url')
        if not code_to_run or not code_to_run.strip(): raise ValueError("Code to execute cannot be empty.")
        if not (api_key and base_url): raise ValueError("API Key and Base URL are required when executing code that uses LMP helper functions.")
        
        local_client = OpenAI(api_key=api_key, base_url=base_url)

        if pybullet.isConnected():
            try: pybullet.disconnect()
            except pybullet.error: pass
        pybullet.connect(pybullet.DIRECT)
        pybullet.setAdditionalSearchPath(pybullet_data.getDataPath())
        pybullet.setAdditionalSearchPath(ALGORITHM_ROOT_PATH)

        env = PickPlaceEnv(asset_path=ALGORITHM_ROOT_PATH, render=True)
        
        np.random.seed(42)
        obj_list = np.random.choice(ALL_BLOCKS, size=num_blocks, replace=False).tolist() + \
                   np.random.choice(ALL_BOWLS, size=num_bowls, replace=False).tolist()
        env.reset(obj_list)
        
        gvars = setup_exec_env(env, cfg_tabletop, local_client)
        
        print('Available objects:', obj_list)
        print("--- [Apply Code] Syntax check ---")
        compile(code_to_run, "<user_code>", "exec")
        print("--- [Apply Code] Syntax OK, executing ---")
        exec_safe(code_to_run, gvars, {})
        print("--- [Apply Code] Execution complete ---")

        if env.cache_video:
            print(f"--- [Apply Code] {len(env.cache_video)} frames captured, generating video ---")
            video_path = "/tmp/simulation_video_from_code.mp4"
            ImageSequenceClip(env.cache_video, fps=25).write_videofile(video_path, codec='libx264', logger=None)
            with open(video_path, "rb") as f:
                result["video"] = base64.b64encode(f.read()).decode('utf-8')
            print("--- [Apply Code] Video generation complete ---")
        else:
            print("--- [Apply Code] Execution finished but no video frames were captured ---")
    except Exception as e:
        print(f"!!! Code execution error !!!\n{traceback.format_exc()}")
        result['error'] = str(e)
    finally:
        result["log"] = log_stream.getvalue()
        sys.stdout = original_stdout
        log_stream.close()
        if env is not None and pybullet.isConnected(): pybullet.disconnect()
    return result



# ==============================================================================
# --- Original algorithm code (LMP, Prompts, etc.) ---
# ==============================================================================

class LMP:
    def __init__(self, name, cfg, lmp_fgen, fixed_vars, variable_vars, client):
        self._name = name
        self._cfg = cfg
        self.client = client
        self._base_prompt = self._cfg['prompt_text']
        self._stop_tokens = list(self._cfg['stop'])
        self._lmp_fgen = lmp_fgen
        self._fixed_vars = fixed_vars
        self._variable_vars = variable_vars
        self.exec_hist = ''
    def clear_exec_hist(self):
        self.exec_hist = ''
    def build_prompt(self, query, context=''):
        if len(self._variable_vars) > 0:
            variable_vars_imports_str = f"from utils import {', '.join(self._variable_vars.keys())}"
        else:
            variable_vars_imports_str = ''
        prompt = self._base_prompt.replace('{variable_vars_imports}', variable_vars_imports_str)
        if self._cfg['maintain_session']:
            prompt += f'\n{self.exec_hist}'
        if context != '':
            prompt += f'\n{context}'
        use_query = f'{self._cfg["query_prefix"]}{query}{self._cfg["query_suffix"]}'
        prompt += f'\n{use_query}'
        return prompt, use_query
    def __call__(self, query, context='', **kwargs):
        prompt, use_query = self.build_prompt(query, context=context)
        
        while True:
            try:
                if self.client is None:
                    raise ValueError("OpenAI client not initialized. Please provide API key and base URL.")
                
                code_str = self.client.chat.completions.create(
                    model=CURRENT_MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    stop=self._stop_tokens,
                    temperature=self._cfg['temperature'],
                    max_tokens=self._cfg['max_tokens'],
                    timeout=30.0
                ).choices[0].message.content
                break
            except APITimeoutError as e:
                raise e
            except (RateLimitError, APIConnectionError) as e:
                print(f'API Error: {e}, retrying...'); sleep(10)
        
        # Strip markdown fences and filter non-code lines
        import re
        match = re.search(r'```(?:python)?(.*?)```', code_str, re.DOTALL)
        if match:
            clean_code = match.group(1).strip()
        else:
            lines = code_str.split('\n')
            clean_lines = []
            for line in lines:
                stripped_line = line.strip()
                if stripped_line.lower().startswith(("here is", "sure", "ok", "the code", "this script")):
                    continue
                if '=' in line or '(' in line or line.startswith(('def ', 'import ', 'from ', 'print', 'say', 'put_', 'objects', '#', '    ', '\t')) or not stripped_line:
                    clean_lines.append(line)
            clean_code = '\n'.join(clean_lines).strip()
            if not clean_code:
                print("Warning: no valid code could be extracted from the model reply!")
                clean_code = "# No valid code generated."
        print(f"--- Raw reply ---\n{code_str}\n--- Cleaned code ---\n{clean_code}\n----------------")
        
        to_exec = f'{context}\n{clean_code}' if self._cfg['include_context'] and context else clean_code
        
        new_fs = self._lmp_fgen.create_new_fs_from_code(clean_code)
        self._variable_vars.update(new_fs)
        gvars = merge_dicts([self._fixed_vars, self._variable_vars])
        
        try:
            exec_safe(to_exec, gvars, kwargs)
        except Exception as e:
            print(f"Error executing generated code: {e}")
            print(f"Code attempted:\n{to_exec}")
            raise e
        self.exec_hist += f'\n{to_exec}'
        if self._cfg['maintain_session']: self._variable_vars.update(kwargs)
        if self._cfg['has_return']: return kwargs[self._cfg['return_val_name']]
def merge_dicts(dicts):
    return { k : v for d in dicts for k, v in d.items() }
def exec_safe(code_str, gvars=None, lvars=None):
    banned_phrases = ['import', '__']
    for phrase in banned_phrases:
        if phrase in code_str:
            raise ValueError(f"Banned phrase '{phrase}' found in code.")
    if gvars is None: gvars = {}
    if lvars is None: lvars = {}
    empty_fn = lambda *args, **kwargs: None
    custom_gvars = merge_dicts([ gvars, {'exec': empty_fn, 'eval': empty_fn} ])
    exec(code_str, custom_gvars, lvars)


class LMP_wrapper():
  def __init__(self, env, cfg, render=False):
    self.env = env; self._cfg = cfg; self.object_names = list(self._cfg['env']['init_objs'])
    self._min_xy = np.array(self._cfg['env']['coords']['bottom_left']); self._max_xy = np.array(self._cfg['env']['coords']['top_right'])
    self._range_xy = self._max_xy - self._min_xy; self._table_z = self._cfg['env']['coords']['table_z']; self.render = render
  def is_obj_visible(self, obj_name): return obj_name in self.object_names
  def get_obj_names(self): return self.object_names[::]
  def denormalize_xy(self, pos_normalized): return pos_normalized * self._range_xy + self._min_xy
  def get_corner_positions(self):
    unit_square = box(0, 0, 1, 1); normalized_corners = np.array(list(unit_square.exterior.coords))[:4]
    return np.array(([self.denormalize_xy(corner) for corner in normalized_corners]))
  def get_side_positions(self):
    side_xs = np.array([0, 0.5, 0.5, 1]); side_ys = np.array([0.5, 0, 1, 0.5])
    normalized_side_positions = np.c_[side_xs, side_ys]
    return np.array(([self.denormalize_xy(corner) for corner in normalized_side_positions]))
  def get_obj_pos(self, obj_name): return self.env.get_obj_pos(obj_name)[:2]
  def get_obj_position_np(self, obj_name): return self.get_pos(obj_name)
  def get_bbox(self, obj_name): return self.env.get_bounding_box(obj_name)
  def get_color(self, obj_name):
    for color, rgb in COLORS.items():
      if color in obj_name: return rgb
  def pick_place(self, pick_pos, place_pos):
    pick_pos_xyz = np.r_[pick_pos, [self._table_z]]; place_pos_xyz = np.r_[place_pos, [self._table_z]]
  def put_first_on_second(self, arg1, arg2):
    pick_pos = self.get_obj_pos(arg1) if isinstance(arg1, str) else arg1
    place_pos = self.get_obj_pos(arg2) if isinstance(arg2, str) else arg2
    self.env.step(action={'pick': pick_pos, 'place': place_pos})
  def get_robot_pos(self): return self.env.get_ee_pos()
  def goto_pos(self, position_xy):
    ee_xyz = self.env.get_ee_pos(); position_xyz = np.concatenate([position_xy, ee_xyz[-1]])
    while np.linalg.norm(position_xyz - ee_xyz) > 0.01:
      self.env.movep(position_xyz); self.env.step_sim_and_render(); ee_xyz = self.env.get_ee_pos()
  def follow_traj(self, traj):
    for pos in traj: self.goto_pos(pos)
  def get_corner_name(self, pos):
    corner_positions = self.get_corner_positions()
    corner_idx = np.argmin(np.linalg.norm(corner_positions - pos, axis=1))
    return ['top left corner', 'top right corner', 'bottom left corner', 'botom right corner'][corner_idx]
  def get_side_name(self, pos):
    side_positions = self.get_side_positions()
    side_idx = np.argmin(np.linalg.norm(side_positions - pos, axis=1))
    return ['top side', 'right side', 'bottom side', 'left side'][side_idx]

prompt_tabletop_ui = '''
# Python 2D robot control script
import numpy as np
from env_utils import put_first_on_second, get_obj_pos, get_obj_names, say, get_corner_name, get_side_name, is_obj_visible, stack_objects_in_order
from plan_utils import parse_obj_name, parse_position, parse_question, transform_shape_pts

objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# the yellow block on the yellow bowl.
say('Ok - putting the yellow block on the yellow bowl')
put_first_on_second('yellow block', 'yellow bowl')
objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# which block did you move.
say('I moved the yellow block')
objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# move the green block to the top right corner.
say('Got it - putting the green block on the top right corner')
corner_pos = parse_position('top right corner')
put_first_on_second('green block', corner_pos)
objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# stack the blue bowl on the yellow bowl on the green block.
order_bottom_to_top = ['green block', 'yellow block', 'blue bowl']
say(f'Sure - stacking from top to bottom: {", ".join(order_bottom_to_top)}')
stack_objects_in_order(object_names=order_bottom_to_top)
objects = ['cyan block', 'white block', 'cyan bowl', 'blue block', 'blue bowl', 'white bowl']
# move the cyan block into its corresponding bowl.
matches = {'cyan block': 'cyan bowl'}
say('Got it - placing the cyan block on the cyan bowl')
for first, second in matches.items():
  put_first_on_second(first, get_obj_pos(second))
objects = ['cyan block', 'white block', 'cyan bowl', 'blue block', 'blue bowl', 'white bowl']
# make a line of blocks on the right side.
say('No problem! Making a line of blocks on the right side')
block_names = parse_obj_name('the blocks', f'objects = {get_obj_names()}')
line_pts = parse_position(f'a 30cm vertical line on the right with {len(block_names)} points')
for block_name, pt in zip(block_names, line_pts):
  put_first_on_second(block_name, pt)
objects = ['yellow block', 'red block', 'yellow bowl', 'gray block', 'gray bowl', 'red bowl']
# put the small banana colored thing in between the blue bowl and green block.
say('Sure thing - putting the yellow block between the blue bowl and the green block')
target_pos = parse_position('a point in the middle betweeen the blue bowl and the green block')
put_first_on_second('yellow block', target_pos)
objects = ['yellow block', 'red block', 'yellow bowl', 'gray block', 'gray bowl', 'red bowl']
# can you cut the bowls in half.
say('no, I can only move objects around')
objects = ['yellow block', 'green block', 'yellow bowl', 'gray block', 'gray bowl', 'green bowl']
# stack the blocks on the right side with the gray one on the bottom.
say('Ok. stacking the blocks on the right side with the gray block on the bottom')
right_side = parse_position('the right side')
put_first_on_second('gray block', right_side)
order_bottom_to_top = ['gray block', 'green block', 'yellow block']
stack_objects_in_order(object_names=order_bottom_to_top)
objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# hide the blue bowl.
bowl_name = np.random.choice(['yellow bowl', 'green bowl'])
say(f'Sounds good! Hiding the blue bowl under the {bowl_name}')
put_first_on_second(bowl_name, 'blue bowl')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# stack everything with the green block on top.
say('Ok! Stacking everything with the green block on the top')
order_bottom_to_top = ['blue bowl', 'pink bowl', 'green bowl', 'pink block', 'blue block', 'green block']
stack_objects_in_order(object_names=order_bottom_to_top)
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# move the grass-colored bowl to the left.
say('Sure - moving the green bowl left by 10 centimeters')
left_pos = parse_position('a point 10cm left of the green bowl')
put_first_on_second('green bowl', left_pos)
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# why did you move the red bowl.
say(f'I did not move the red bowl')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# undo that.
say('Sure - moving the green bowl right by 10 centimeters')
left_pos = parse_position('a point 10cm right of the green bowl')
put_first_on_second('green bowl', left_pos)
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# place the top most block to the corner closest to the bottom most block.
top_block_name = parse_obj_name('top most block', f'objects = {get_obj_names()}')
bottom_block_name = parse_obj_name('bottom most block', f'objects = {get_obj_names()}')
closest_corner_pos = parse_position(f'the corner closest to the {bottom_block_name}', f'objects = {get_obj_names()}')
say(f'Putting the {top_block_name} on the {get_corner_name(closest_corner_pos)}')
put_first_on_second(top_block_name, closest_corner_pos)
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# move the brown bowl to the side closest to the green block.
closest_side_position = parse_position('the side closest to the green block')
say(f'Got it - putting the brown bowl on the {get_side_name(closest_side_position)}')
put_first_on_second('brown bowl', closest_side_position)
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# place the green block to the right of the bowl that has the blue block.
bowl_name = parse_obj_name('the bowl that has the blue block', f'objects = {get_obj_names()}')
if bowl_name:
  target_pos = parse_position(f'a point 10cm to the right of the {bowl_name}')
  say(f'No problem - placing the green block to the right of the {bowl_name}')
  put_first_on_second('green block', target_pos)
else:
  say('There are no bowls that has the blue block')
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# place the blue block in the empty bowl.
empty_bowl_name = parse_obj_name('the empty bowl', f'objects = {get_obj_names()}')
if empty_bowl_name:
  say(f'Ok! Putting the blue block on the {empty_bowl_name}')
  put_first_on_second('blue block', empty_bowl_name)
else:
  say('There are no empty bowls')
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# move the other blocks to the bottom corners.
block_names = parse_obj_name('blocks other than the blue block', f'objects = {get_obj_names()}')
corners = parse_position('the bottom corners')
for block_name, pos in zip(block_names, corners):
  put_first_on_second(block_name, pos)
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# move the red bowl a lot to the left of the blocks.
say('Sure! Moving the red bowl to a point left of the blocks')
left_pos = parse_position('a point 20cm left of the blocks')
put_first_on_second('red bowl', left_pos)
objects = ['pink block', 'gray block', 'orange block']
# move the pinkish colored block on the bottom side.
say('Ok - putting the pink block on the bottom side')
bottom_side_pos = parse_position('the bottom side')
put_first_on_second('pink block', bottom_side_pos)
objects = ['yellow bowl', 'blue block', 'yellow block', 'blue bowl']
# is the blue block to the right of the yellow bowl?
if parse_question('is the blue block to the right of the yellow bowl?', f'objects = {get_obj_names()}'):
  say('yes, there is a blue block to the right of the yellow bow')
else:
  say('no, there is\\'t a blue block to the right of the yellow bow')
objects = ['yellow bowl', 'blue block', 'yellow block', 'blue bowl']
# how many yellow objects are there?
n_yellow_objs = parse_question('how many yellow objects are there', f'objects = {get_obj_names()}')
say(f'there are {n_yellow_objs} yellow object')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# move the left most block to the green bowl.
left_block_name = parse_obj_name('left most block', f'objects = {get_obj_names()}')
say(f'Moving the {left_block_name} on the green bowl')
put_first_on_second(left_block_name, 'green bowl')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# move the other blocks to different corners.
block_names = parse_obj_name(f'blocks other than the {left_block_name}', f'objects = {get_obj_names()}')
corners = parse_position('the corners')
say(f'Ok - moving the other {len(block_names)} blocks to different corners')
for block_name, pos in zip(block_names, corners):
  put_first_on_second(block_name, pos)
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# is the pink block on the green bowl.
if parse_question('is the pink block on the green bowl', f'objects = {get_obj_names()}'):
  say('Yes - the pink block is on the green bowl.')
else:
  say('No - the pink block is not on the green bowl.')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# what are the blocks left of the green bowl.
left_block_names =  parse_question('what are the blocks left of the green bowl', f'objects = {get_obj_names()}')
if len(left_block_names) > 0:
  say(f'These blocks are left of the green bowl: {", ".join(left_block_names)}')
else:
  say('There are no blocks left of the green bowl')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# if you see a purple bowl put it on the blue bowl
if is_obj_visible('purple bowl'):
  say('Putting the purple bowl on the pink bowl')
  put_first_on_second('purple bowl', 'pink bowl')
else:
  say('I don\\'t see a purple bowl')
objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# imagine that the bowls are different biomes on earth and imagine that the blocks are parts of a building.
say('ok')
objects = ['yellow block', 'green block', 'yellow bowl', 'blue block', 'blue bowl', 'green bowl']
# now build a tower in the grasslands.
order_bottom_to_top = ['green bowl', 'blue block', 'green block', 'yellow block']
say('stacking the blocks on the green bowl')
stack_objects_in_order(object_names=order_bottom_to_top)
objects = ['yellow block', 'green block', 'yellow bowl', 'gray block', 'gray bowl', 'green bowl']
# show me what happens when the desert gets flooded by the ocean.
say('putting the yellow bowl on the blue bowl')
put_first_on_second('yellow bowl', 'blue bowl')
objects = ['pink block', 'gray block', 'orange block']
# move all blocks 5cm toward the top.
say('Ok - moving all blocks 5cm toward the top')
block_names = parse_obj_name('the blocks', f'objects = {get_obj_names()}')
for block_name in block_names:
  target_pos = parse_position(f'a point 5cm above the {block_name}')
  put_first_on_second(block_name, target_pos)
objects = ['cyan block', 'white block', 'purple bowl', 'blue block', 'blue bowl', 'white bowl']
# make a triangle of blocks in the middle.
block_names = parse_obj_name('the blocks', f'objects = {get_obj_names()}')
triangle_pts = parse_position(f'a triangle with size 10cm around the middle with {len(block_names)} points')
say('Making a triangle of blocks around the middle of the workspace')
for block_name, pt in zip(block_names, triangle_pts):
  put_first_on_second(block_name, pt)
objects = ['cyan block', 'white block', 'purple bowl', 'blue block', 'blue bowl', 'white bowl']
# make the triangle smaller.
triangle_pts = transform_shape_pts('scale it by 0.5x', shape_pts=triangle_pts)
say('Making the triangle smaller')
block_names = parse_obj_name('the blocks', f'objects = {get_obj_names()}')
for block_name, pt in zip(block_names, triangle_pts):
  put_first_on_second(block_name, pt)
objects = ['brown bowl', 'red block', 'brown block', 'red bowl', 'pink bowl', 'pink block']
# put the red block on the farthest bowl.
farthest_bowl_name = parse_obj_name('the bowl farthest from the red block', f'objects = {get_obj_names()}')
say(f'Putting the red block on the {farthest_bowl_name}')
put_first_on_second('red block', farthest_bowl_name)
'''.strip()

prompt_parse_obj_name = '''
import numpy as np
from env_utils import get_obj_pos, parse_position
from utils import get_obj_positions_np

objects = ['blue block', 'cyan block', 'purple bowl', 'gray bowl', 'brown bowl', 'pink block', 'purple block']
# the block closest to the purple bowl.
block_names = ['blue block', 'cyan block', 'purple block']
block_positions = get_obj_positions_np(block_names)
closest_block_idx = get_closest_idx(points=block_positions, point=get_obj_pos('purple bowl'))
closest_block_name = block_names[closest_block_idx]
ret_val = closest_block_name
objects = ['brown bowl', 'banana', 'brown block', 'apple', 'blue bowl', 'blue block']
# the blocks.
ret_val = ['brown block', 'blue block']
objects = ['brown bowl', 'banana', 'brown block', 'apple', 'blue bowl', 'blue block']
# the brown objects.
ret_val = ['brown bowl', 'brown block']
objects = ['brown bowl', 'banana', 'brown block', 'apple', 'blue bowl', 'blue block']
# a fruit that's not the apple
fruit_names = ['banana', 'apple']
for fruit_name in fruit_names:
    if fruit_name != 'apple':
        ret_val = fruit_name
objects = ['blue block', 'cyan block', 'purple bowl', 'brown bowl', 'purple block']
# blocks above the brown bowl.
block_names = ['blue block', 'cyan block', 'purple block']
brown_bowl_pos = get_obj_pos('brown bowl')
use_block_names = []
for block_name in block_names:
    if get_obj_pos(block_name)[1] > brown_bowl_pos[1]:
        use_block_names.append(block_name)
ret_val = use_block_names
objects = ['blue block', 'cyan block', 'purple bowl', 'brown bowl', 'purple block']
# the blue block.
ret_val = 'blue block'
objects = ['blue block', 'cyan block', 'purple bowl', 'brown bowl', 'purple block']
# the block closest to the bottom right corner.
corner_pos = parse_position('bottom right corner')
block_names = ['blue block', 'cyan block', 'purple block']
block_positions = get_obj_positions_np(block_names)
closest_block_idx = get_closest_idx(points=block_positions, point=corner_pos)
closest_block_name = block_names[closest_block_idx]
ret_val = closest_block_name
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# the left most block.
block_names = ['green block', 'brown block', 'blue block']
block_positions = get_obj_positions_np(block_names)
left_block_idx = np.argsort(block_positions[:, 0])[0]
left_block_name = block_names[left_block_idx]
ret_val = left_block_name
objects = ['brown bowl', 'green block', 'brown block', 'green bowl', 'blue bowl', 'blue block']
# the bowl on near the top.
bowl_names = ['brown bowl', 'green bowl', 'blue bowl']
bowl_positions = get_obj_positions_np(bowl_names)
top_bowl_idx = np.argsort(block_positions[:, 1])[-1]
top_bowl_name = bowl_names[top_bowl_idx]
ret_val = top_bowl_name
objects = ['yellow bowl', 'purple block', 'yellow block', 'purple bowl', 'pink bowl', 'pink block']
# the third bowl from the right.
bowl_names = ['yellow bowl', 'purple bowl', 'pink bowl']
bowl_positions = get_obj_positions_np(bowl_names)
bowl_idx = np.argsort(block_positions[:, 0])[-3]
bowl_name = bowl_names[bowl_idx]
ret_val = bowl_name
'''.strip()

prompt_parse_position = '''
import numpy as np
from shapely.geometry import *
from shapely.affinity import *
from env_utils import denormalize_xy, parse_obj_name, get_obj_names, get_obj_pos

# a 30cm horizontal line in the middle with 3 points.
middle_pos = denormalize_xy([0.5, 0.5])
start_pos = middle_pos + [-0.3/2, 0]
end_pos = middle_pos + [0.3/2, 0]
line = make_line(start=start_pos, end=end_pos)
points = interpolate_pts_on_line(line=line, n=3)
ret_val = points
# a 20cm vertical line near the right with 4 points.
middle_pos = denormalize_xy([1, 0.5])
start_pos = middle_pos + [0, -0.2/2]
end_pos = middle_pos + [0, 0.2/2]
line = make_line(start=start_pos, end=end_pos)
points = interpolate_pts_on_line(line=line, n=4)
ret_val = points
# a diagonal line from the top left to the bottom right corner with 5 points.
top_left_corner = denormalize_xy([0, 1])
bottom_right_corner = denormalize_xy([1, 0])
line = make_line(start=top_left_corner, end=bottom_right_corner)
points = interpolate_pts_on_line(line=line, n=5)
ret_val = points
# a triangle with size 10cm with 3 points.
polygon = make_triangle(size=0.1, center=denormalize_xy([0.5, 0.5]))
points = get_points_from_polygon(polygon)
ret_val = points
# the corner closest to the sun colored block.
block_name = parse_obj_name('the sun colored block', f'objects = {get_obj_names()}')
corner_positions = np.array([denormalize_xy(pos) for pos in [[0, 0], [0, 1], [1, 1], [1, 0]]])
closest_corner_pos = get_closest_point(points=corner_positions, point=get_obj_pos(block_name))
ret_val = closest_corner_pos
# the side farthest from the right most bowl.
bowl_name = parse_obj_name('the right most bowl', f'objects = {get_obj_names()}')
side_positions = np.array([denormalize_xy(pos) for pos in [[0.5, 0], [0.5, 1], [1, 0.5], [0, 0.5]]])
farthest_side_pos = get_farthest_point(points=side_positions, point=get_obj_pos(bowl_name))
ret_val = farthest_side_pos
# a point above the third block from the bottom.
block_name = parse_obj_name('the third block from the bottom', f'objects = {get_obj_names()}')
ret_val = get_obj_pos(block_name) + [0.1, 0]
# a point 10cm left of the bowls.
bowl_names = parse_obj_name('the bowls', f'objects = {get_obj_names()}')
bowl_positions = get_all_object_positions_np(obj_names=bowl_names)
left_obj_pos = bowl_positions[np.argmin(bowl_positions[:, 0])] + [-0.1, 0]
ret_val = left_obj_pos
# the bottom side.
bottom_pos = denormalize_xy([0.5, 0])
ret_val = bottom_pos
# the top corners.
top_left_pos = denormalize_xy([0, 1])
top_right_pos = denormalize_xy([1, 1])
ret_val = [top_left_pos, top_right_pos]
'''.strip()

prompt_parse_question = '''
from utils import get_obj_pos, get_obj_names, parse_obj_name, bbox_contains_pt, is_obj_visible

objects = ['yellow bowl', 'blue block', 'yellow block', 'blue bowl', 'fruit', 'green block', 'black bowl']
# is the blue block to the right of the yellow bowl?
ret_val = get_obj_pos('blue block')[0] > get_obj_pos('yellow bowl')[0]
objects = ['yellow bowl', 'blue block', 'yellow block', 'blue bowl', 'fruit', 'green block', 'black bowl']
# how many yellow objects are there?
yellow_object_names = parse_obj_name('the yellow objects', f'objects = {get_obj_names()}')
ret_val = len(yellow_object_names)
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# is the pink block on the green bowl?
ret_val = bbox_contains_pt(container_name='green bowl', obj_name='pink block')
objects = ['pink block', 'green block', 'pink bowl', 'blue block', 'blue bowl', 'green bowl']
# what are the blocks left of the green bowl?
block_names = parse_obj_name('the blocks', f'objects = {get_obj_names()}')
green_bowl_pos = get_obj_pos('green bowl')
left_block_names = []
for block_name in block_names:
  if get_obj_pos(block_name)[0] < green_bowl_pos[0]:
    left_block_names.append(block_name)
ret_val = left_block_names
objects = ['pink block', 'yellow block', 'pink bowl', 'blue block', 'blue bowl', 'yellow bowl']
# is the sun colored block above the blue bowl?
sun_block_name = parse_obj_name('sun colored block', f'objects = {get_obj_names()}')
sun_block_pos = get_obj_pos(sun_block_name)
blue_bowl_pos = get_obj_pos('blue bowl')
ret_val = sun_block_pos[1] > blue_bowl_pos[1]
objects = ['pink block', 'yellow block', 'pink bowl', 'blue block', 'blue bowl', 'yellow bowl']
# is the green block below the blue bowl?
ret_val = get_obj_pos('green block')[1] < get_obj_pos('blue bowl')[1]
'''.strip()

prompt_transform_shape_pts = '''
import numpy as np
from utils import get_obj_pos, get_obj_names, parse_position, parse_obj_name

# make it bigger by 1.5.
new_shape_pts = scale_pts_around_centroid_np(shape_pts, scale_x=1.5, scale_y=1.5)
# move it to the right by 10cm.
new_shape_pts = translate_pts_np(shape_pts, delta=[0.1, 0])
# move it to the top by 20cm.
new_shape_pts = translate_pts_np(shape_pts, delta=[0, 0.2])
# rotate it clockwise by 40 degrees.
new_shape_pts = rotate_pts_around_centroid_np(shape_pts, angle=-np.deg2rad(40))
# rotate by 30 degrees and make it slightly smaller
new_shape_pts = rotate_pts_around_centroid_np(shape_pts, angle=np.deg2rad(30))
new_shape_pts = scale_pts_around_centroid_np(new_shape_pts, scale_x=0.7, scale_y=0.7)
# move it toward the blue block.
block_name = parse_obj_name('the blue block', f'objects = {get_obj_names()}')
block_pos = get_obj_pos(block_name)
mean_delta = np.mean(block_pos - shape_pts, axis=1)
new_shape_pts = translate_pts_np(shape_pts, mean_delta)
'''.strip()

prompt_fgen = '''
import numpy as np
from shapely.geometry import *
from shapely.affinity import *

from env_utils import get_obj_pos, get_obj_names
from ctrl_utils import put_first_on_second

# define function: total = get_total(xs=numbers).
def get_total(xs):
    return np.sum(xs)

# define function: y = eval_line(x, slope, y_intercept=0).
def eval_line(x, slope, y_intercept):
    return x * slope + y_intercept

# define function: pt = get_pt_to_the_left(pt, dist).
def get_pt_to_the_left(pt, dist):
    return pt + [-dist, 0]

# define function: pt = get_pt_to_the_top(pt, dist).
def get_pt_to_the_top(pt, dist):
    return pt + [0, dist]

# define function line = make_line_by_length(length=x).
def make_line_by_length(length):
  line = LineString([[0, 0], [length, 0]])
  return line

# define function: line = make_vertical_line_by_length(length=x).
def make_vertical_line_by_length(length):
  line = make_line_by_length(length)
  vertical_line = rotate(line, 90)
  return vertical_line

# define function: pt = interpolate_line(line, t=0.5).
def interpolate_line(line, t):
  pt = line.interpolate(t, normalized=True)
  return np.array(pt.coords[0])

# example: scale a line by 2.
line = make_line_by_length(1)
new_shape = scale(line, xfact=2, yfact=2)

# example: put object1 on top of object0.
put_first_on_second('object1', 'object0')

# example: get the position of the first object.
obj_names = get_obj_names()
pos_2d = get_obj_pos(obj_names[0])
'''.strip()

model_name='gpt-4-turbo'
cfg_tabletop = {
  'lmps': {
    'tabletop_ui': {
      'prompt_text': prompt_tabletop_ui,
      'engine': model_name,
      'max_tokens': 512,
      'temperature': 0,
      'query_prefix': '# ',
      'query_suffix': '.',
      'stop': ['#', 'objects = ['],
      'maintain_session': True,
      'debug_mode': False,
      'include_context': True,
      'has_return': False,
      'return_val_name': 'ret_val',
    },
    'parse_obj_name': {
      'prompt_text': prompt_parse_obj_name,
      'engine': model_name,
      'max_tokens': 512,
      'temperature': 0,
      'query_prefix': '# ',
      'query_suffix': '.',
      'stop': ['#', 'objects = ['],
      'maintain_session': False,
      'debug_mode': False,
      'include_context': True,
      'has_return': True,
      'return_val_name': 'ret_val',
    },
    'parse_position': {
      'prompt_text': prompt_parse_position,
      'engine': model_name,
      'max_tokens': 512,
      'temperature': 0,
      'query_prefix': '# ',
      'query_suffix': '.',
      'stop': ['#'],
      'maintain_session': False,
      'debug_mode': False,
      'include_context': True,
      'has_return': True,
      'return_val_name': 'ret_val',
    },
    'parse_question': {
      'prompt_text': prompt_parse_question,
      'engine': model_name,
      'max_tokens': 512,
      'temperature': 0,
      'query_prefix': '# ',
      'query_suffix': '.',
      'stop': ['#', 'objects = ['],
      'maintain_session': False,
      'debug_mode': False,
      'include_context': True,
      'has_return': True,
      'return_val_name': 'ret_val',
    },
    'transform_shape_pts': {
      'prompt_text': prompt_transform_shape_pts,
      'engine': model_name,
      'max_tokens': 512,
      'temperature': 0,
      'query_prefix': '# ',
      'query_suffix': '.',
      'stop': ['#'],
      'maintain_session': False,
      'debug_mode': False,
      'include_context': True,
      'has_return': True,
      'return_val_name': 'new_shape_pts',
    },
    'fgen': {
      'prompt_text': prompt_fgen,
      'engine': model_name,
      'max_tokens': 512,
      'temperature': 0,
      'query_prefix': '# define function: ',
      'query_suffix': '.',
      'stop': ['# define', '# example'],
      'maintain_session': False,
      'debug_mode': False,
      'include_context': True,
    }
  }
}

lmp_tabletop_coords = {
        'top_left':     (-0.3 + 0.05, -0.2 - 0.05),
        'top_side':     (0,           -0.2 - 0.05),
        'top_right':    (0.3 - 0.05,  -0.2 - 0.05),
        'left_side':    (-0.3 + 0.05, -0.5,      ),
        'middle':       (0,           -0.5,      ),
        'right_side':   (0.3 - 0.05,  -0.5,      ),
        'bottom_left':  (-0.3 + 0.05, -0.8 + 0.05),
        'bottom_side':  (0,           -0.8 + 0.05),
        'bottom_right': (0.3 - 0.05,  -0.8 + 0.05),
        'table_z':       0.0,
      }

def setup_LMP(env, cfg, client):
  cfg = copy.deepcopy(cfg)
  cfg['env'] = dict()
  cfg['env']['init_objs'] = list(env.obj_name_to_id.keys())
  cfg['env']['coords'] = lmp_tabletop_coords
  LMP_env = LMP_wrapper(env, cfg)
  fixed_vars = {'np': np}
  fixed_vars.update({name: eval(name) for name in shapely.geometry.__all__ + shapely.affinity.__all__})
  variable_vars = {k: getattr(LMP_env, k) for k in ['get_bbox', 'get_obj_pos', 'get_color', 'is_obj_visible', 'denormalize_xy', 'put_first_on_second', 'get_obj_names', 'get_corner_name', 'get_side_name']}
  variable_vars['say'] = lambda msg: print(f'robot says: {msg}')
  
  # Pass the received client to all LMP instances
  lmp_fgen = LMPFGen(cfg['lmps']['fgen'], fixed_vars, variable_vars, client)
  variable_vars.update({
      k: LMP(k, cfg['lmps'][k], lmp_fgen, fixed_vars, variable_vars, client)
      for k in ['parse_obj_name', 'parse_position', 'parse_question', 'transform_shape_pts']
  })
  lmp_tabletop_ui = LMP(
      'tabletop_ui', cfg['lmps']['tabletop_ui'], lmp_fgen, fixed_vars, variable_vars, client
  )
  return lmp_tabletop_ui

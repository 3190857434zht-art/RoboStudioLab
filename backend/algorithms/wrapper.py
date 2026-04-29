import json
import sys
import os
import traceback
import importlib

def main():
    input_file = '/exchange/input.json'
    output_file = '/exchange/output.json'
    
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
            
        mode = data.get('mode')
        params = data.get('params', {})
        algorithm_name = data.get('algorithm_name')

        # --- 核心修正：将算法的根目录添加到 sys.path ---
        # 这样算法内部的绝对导入 (如 from sim_env import ...) 就能正常工作了
        algo_root_path = os.path.join('/algorithm', algorithm_name)
        if algo_root_path not in sys.path:
            sys.path.insert(0, algo_root_path)

        # 动态导入算法模块
        module_name = f"{algorithm_name}.Interactive_Demo"
        algorithm_module = importlib.import_module(module_name)

        # 3. 执行对应的函数
        if mode == 'run_algorithm':
            if not hasattr(algorithm_module, 'run_algorithm'):
                raise ImportError(f"模块 {module_name} 中未找到 'run_algorithm' 函数。")
            result = algorithm_module.run_algorithm(params)
        elif mode == 'run_from_code':
            if not hasattr(algorithm_module, 'run_from_code'):
                raise ImportError(f"模块 {module_name} 中未找到 'run_from_code' 函数。")
            result = algorithm_module.run_from_code(params)
        else:
            raise ValueError(f"未知的运行模式: {mode}")

        # 4. 将结果写入共享目录
        with open(output_file, 'w') as f:
            json.dump(result, f)

    except Exception as e:
        error_result = {
            "error": str(e),
            "log": traceback.format_exc()
        }
        with open(output_file, 'w') as f:
            json.dump(error_result, f)

if __name__ == "__main__":
    main()
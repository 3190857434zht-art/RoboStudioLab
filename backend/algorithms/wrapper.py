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

        # Add the algorithm root directory to sys.path so that
        # absolute imports inside the algorithm (e.g. from sim_env import ...) work correctly.
        algo_root_path = os.path.join('/algorithm', algorithm_name)
        if algo_root_path not in sys.path:
            sys.path.insert(0, algo_root_path)

        # Dynamically import the algorithm module
        module_name = f"{algorithm_name}.Interactive_Demo"
        algorithm_module = importlib.import_module(module_name)

        # Execute the corresponding function
        if mode == 'run_algorithm':
            if not hasattr(algorithm_module, 'run_algorithm'):
                raise ImportError(f"Function 'run_algorithm' not found in module {module_name}.")
            result = algorithm_module.run_algorithm(params)
        elif mode == 'run_from_code':
            if not hasattr(algorithm_module, 'run_from_code'):
                raise ImportError(f"Function 'run_from_code' not found in module {module_name}.")
            result = algorithm_module.run_from_code(params)
        else:
            raise ValueError(f"Unknown run mode: {mode}")

        # Write result to the shared exchange directory
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

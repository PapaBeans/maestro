import importlib.util
import os
import requests
import time

loaded_module = None

def load_module(module_name):
    """
    Dynamically load a module with a hyphen in its name.
    """
    global loaded_module
    current_file_path = os.path.abspath(__file__)
    maestro_dir = os.path.dirname(current_file_path)
    module_file_path = os.path.join(maestro_dir, f'{module_name}')

    spec = importlib.util.spec_from_file_location(module_name, module_file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loaded_module = module
    return module

def run_maestro(objective, **kwargs):
    """
    Runs the 'run_maestro' function from the specified module.
    
    Args:
        objective (str): The primary objective to pass to the LLM
        kwargs (dict): Arguments to pass depending on the loaded module
    """
    global loaded_module
    if loaded_module is None:
        raise ValueError("Module not loaded. Please load a module first.")
    
    # Ensure the run_maestro function exists in the module
    if hasattr(loaded_module, 'run_maestro'):
        return loaded_module.run_maestro(objective, **kwargs)
    else:
        raise AttributeError(f"The loaded module does not have a 'run_maestro' function.")

def get_ui_elements(module_name):
    """
    Gets the UI elements from the specified module.
    
    Args:
        module_name (str): The name of the maestro module to get UI elements from (Ex: maestro-anyapi)
    """
    module = load_module(module_name)
    if hasattr(module, 'get_ui_elements'):
        return module.get_ui_elements()
    else:
        return [
            {'type': 'checkbox', 'label': 'Unable to find get_ui_elements function in the loaded module.', 'id': 'failed_get_ui_elements'}
        ]

def get_required_args(module_name):
    """
    Gets the required arguments from the specified module.
    
    Args:
        module_name (str): The name of the maestro module to get required arguments from (Ex: maestro-anyapi)
    """
    module = load_module(module_name)
    if hasattr(module, 'get_required_args'):
        return module.get_required_args()
    else:
        return ['objective']

def send_progress_update(message, title='', footer='', color="blue"):
    progress = {
        'color': color,
        'time': time.localtime(),
        'title': title,
        'content': message,
        'footer': footer
    }
    try:
        response = requests.post('http://localhost:5000/update_progress', json=progress)
        if response.status_code != 200:
            print(f"Failed to send progress update: {response.status_code}")
    except Exception as e:
        print(f"Error sending progress update: {str(e)}")
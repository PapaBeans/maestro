import sys
import os

# Add the `./maestro` path to our sys.path for imports
current_file_path = os.path.dirname(os.path.abspath(__file__))
maestro_dir = os.path.dirname(current_file_path)
sys.path.append(maestro_dir)

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import maestro_api_router as maestro

app = Flask(__name__)
socketio = SocketIO(app)

# Grab all maestro*.py files for selection in the UI
maestro_files = [f for f in os.listdir(maestro_dir) if f.endswith('.py') and f.startswith('maestro') and not f.startswith('maestro_')]
progress_data = []

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        selected_file = request.form.get('selected_file')
        objective = request.form.get('objective')
        additional_args = {}
        
        # Get the required arguments for the selected maestro-module
        # required arguments are defined in the individual maestro*.py file
        try:
            required_args = maestro.get_required_args(selected_file)
            for arg in required_args:
                arg_name = arg['name']
                arg_default = arg['default']
                if arg_name != 'objective':
                    additional_args[arg_name] = request.form.get(arg_name, str(arg_default))

            # Call the run_maestro function with all dynamic arguments added
            maestro.run_maestro(objective, **additional_args)
            # Emit a final update to the client indicating completion
            completion_message = {'color': 'green', 'content': 'Maestro task completed successfully!', 'title': 'Success', 'footer': ''}
            socketio.emit('update_progress', completion_message)
            
            return render_template('results.html', results=progress_data)
        except Exception as e:
            error_message = f"Error executing maestro module: {str(e)}"
            progress_data.append({'color': 'red', 'content': error_message, 'title': 'Error', 'footer': ''})
            socketio.emit('progress_update', {'color': 'red', 'content': error_message, 'title': 'Error', 'footer': ''})
            return jsonify({"status": "error", "message": error_message}), 500

    return render_template('index.html', files=maestro_files)

@app.route('/update_progress', methods=['POST'])
def update_progress():
    global progress_data
    update = request.json
    progress_data.append(update)
    socketio.emit('update_progress', update)
    return jsonify({"status": "success"}), 200

# Get the UI elements from a given module
@app.route('/get_ui_elements', methods=['POST'])
def get_ui_elements():
    import_name = request.json.get('import_name')
    try:
        elements = maestro.get_ui_elements(import_name)
        return jsonify(elements)
    except Exception as e:
        return jsonify([
            {'type': 'checkbox', 'label': 'Error loading UI elements: ' + str(e), 'id': 'error_get_ui_elements'}
        ])

if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, render_template_string, url_for
import subprocess
import os
import logging

app = Flask(__name__)

# Set up logging; warnings will be printed to the console.
logging.basicConfig(level=logging.INFO)

# Define the tasks that have subtasks.
# In your list, task 1 has subtasks "a" and "b",
# and task 11 has subtasks "a", "b", "c", "d".
SUBTASKS = {
    1: ['a', 'b'],
    11: ['a', 'b', 'c', 'd']
}

# --- HTML Templates ---

# Main homepage template: shows the 12 tasks arranged in a grid.
MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
  <title>Task Selector</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    h1 { text-align: center; }
    .grid-container {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      grid-gap: 20px;
    }
    .button {
      display: block;
      width: 100%;
      padding: 20px;
      font-size: 1.5em;
      text-align: center;
      background-color: #007BFF;
      color: #fff;
      text-decoration: none;
      border-radius: 8px;
      transition: background-color 0.3s;
    }
    .button:hover {
      background-color: #0056b3;
    }
    @media (max-width: 600px) {
      .grid-container {
        grid-template-columns: repeat(2, 1fr);
      }
    }
  </style>
</head>
<body>
  <h1>Select a Task</h1>
  <div class="grid-container">
    {% for task in tasks %}
      <a class="button" href="{{ url_for('handle_task', task_id=task) }}">
        Task {{ task }}
      </a>
    {% endfor %}
  </div>
</body>
</html>
'''

# Subtask selection template: shows buttons for each subtask.
SUBTASK_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
  <title>Task {{ task_id }} Subtasks</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    h1 { text-align: center; }
    .grid-container {
      display: grid;
      /* Use auto-fit to adapt for different number of subtasks */
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      grid-gap: 20px;
    }
    .button {
      display: block;
      width: 100%;
      padding: 20px;
      font-size: 1.5em;
      text-align: center;
      background-color: #28a745;
      color: #fff;
      text-decoration: none;
      border-radius: 8px;
      transition: background-color 0.3s;
    }
    .button:hover {
      background-color: #1e7e34;
    }
  </style>
</head>
<body>
  <h1>Select a Subtask for Task {{ task_id }}</h1>
  <div class="grid-container">
    {% for sub in subtasks %}
      <a class="button" href="{{ url_for('handle_subtask', task_id=task_id, subtask=sub) }}">
        Task {{ task_id }}{{ sub }}
      </a>
    {% endfor %}
  </div>
  <br>
  <div style="text-align: center;">
    <a href="{{ url_for('index') }}">Back to Home</a>
  </div>
</body>
</html>
'''

# Template for displaying the output after executing a task file.
OUTPUT_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
  <title>Result for Task {{ task_name }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    h1 { text-align: center; }
    .preformatted {
      background-color: #f8f9fa;
      border: 1px solid #dee2e6;
      padding: 15px;
      border-radius: 5px;
      white-space: pre-wrap;
      word-wrap: break-word;
      margin: 20px auto;
      max-width: 800px;
    }
    .back-link { text-align: center; display: block; margin-top: 20px; }
  </style>
</head>
<body>
  <h1>Result for Task {{ task_name }}</h1>
  <div class="preformatted">
    {{ output }}
  </div>
  <div class="back-link">
    <a href="{{ url_for('index') }}">Back to Home</a>
  </div>
</body>
</html>
'''

# Template for when a task file is missing (dummy task view).
DUMMY_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
  <title>Task {{ task_name }} Not Implemented</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    h1 { text-align: center; color: #856404; }
    .warning {
      padding: 15px;
      background-color: #ffc107;
      color: #856404;
      border: 1px solid #ffeeba;
      border-radius: 5px;
      max-width: 600px;
      margin: 20px auto;
      text-align: center;
    }
    .back-link { text-align: center; display: block; margin-top: 20px; }
  </style>
</head>
<body>
  <h1>Task {{ task_name }} Not Implemented</h1>
  <div class="warning">
    This task has not been implemented yet.
  </div>
  <div class="back-link">
    <a href="{{ url_for('index') }}">Back to Home</a>
  </div>
</body>
</html>
'''

# --- Flask Routes ---

@app.route('/')
def index():
    """
    Display the homepage with the grid of 12 tasks.
    """
    # Create a list of task numbers 1 through 12.
    tasks = list(range(1, 13))
    return render_template_string(MAIN_TEMPLATE, tasks=tasks)

@app.route('/task/<int:task_id>')
def handle_task(task_id):
    """
    If the task has subtasks (i.e. task 1 or 11), show a subtask selection page.
    Otherwise, run the corresponding task file (e.g. "Task2.py" for task 2).
    """
    if task_id in SUBTASKS:
        # Render the page with subtask buttons.
        return render_template_string(SUBTASK_TEMPLATE, task_id=task_id, subtasks=SUBTASKS[task_id])
    else:
        # Build the filename for tasks without subtasks.
        filename = f"Task{task_id}.py"
        return run_python_file(filename, task_name=str(task_id))

@app.route('/task/<int:task_id>/<subtask>')
def handle_subtask(task_id, subtask):
    """
    For tasks that have subtasks, this route runs the corresponding subtask file.
    For example, for task 1 and subtask "a", it runs "Task1a.py".
    """
    if task_id in SUBTASKS and subtask in SUBTASKS[task_id]:
        filename = f"Task{task_id}{subtask}.py"
        return run_python_file(filename, task_name=f"{task_id}{subtask}")
    else:
        # Log a warning if the subtask is not defined.
        logging.warning(f"Subtask {task_id}{subtask} is not defined in the configuration.")
        return render_template_string(DUMMY_TEMPLATE, task_name=f"{task_id}{subtask}")

def run_python_file(filename, task_name):
    """
    Checks if the file exists. If it does, runs it (using subprocess) and captures its output.
    If not, logs a warning and returns a dummy page.
    """
    if not os.path.isfile(filename):
        logging.warning(f"File {filename} does not exist. Displaying dummy page for task {task_name}.")
        return render_template_string(DUMMY_TEMPLATE, task_name=task_name)
    
    try:
        # Run the file with a timeout (adjust as needed). Both stdout and stderr are captured.
        result = subprocess.run(
            ["python", filename],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Combine standard output and error.
        output = result.stdout + result.stderr
        return render_template_string(OUTPUT_TEMPLATE, task_name=task_name, output=output)
    except subprocess.TimeoutExpired:
        logging.error(f"Execution of {filename} timed out.")
        return render_template_string(OUTPUT_TEMPLATE, task_name=task_name, output="Task execution timed out.")
    except Exception as e:
        logging.error(f"Error executing {filename}: {e}")
        return render_template_string(OUTPUT_TEMPLATE, task_name=task_name, output=f"Error executing task: {e}")

if __name__ == '__main__':
    # For development, run with debug=True.
    app.run(debug=True)

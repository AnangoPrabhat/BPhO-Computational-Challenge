# main.py
from flask import Flask, render_template_string, url_for, send_file, request, redirect
import subprocess
import os
import logging
import io
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------
# Global resources – e.g. load the image used by Task 6 (and similar tasks)
# --------------------------------------------------------------------
image_file = "Tall1.jpg"
if os.path.exists(image_file):
    image = plt.imread(image_file)
    img_height, img_width, channels = image.shape
else:
    logging.error("Image file Tall1.jpg not found!")
    image = None
    img_height, img_width, channels = 0, 0, 0

# --------------------------------------------------------------------
# Define a generic slider configuration for interactive tasks.
# The configuration is a list of dictionaries.
# For Task 6 we need the following four sliders.
# Notice that you can add extra keys later if needed.
# --------------------------------------------------------------------
task6_sliders = [
    {
        "id": "start_x",
        "label": "Start X",
        "min": -int(1 * img_width),
        "max": int(2.5 * img_width),
        "value": 60,
        "step": 10
    },
    {
        "id": "start_y",
        "label": "Start Y",
        "min": -int(1.5 * img_height),
        "max": int(1.5 * img_height),
        "value": 0,
        "step": 10
    },
    {
        "id": "scale",
        "label": "Canvas Scale",
        "min": 1,
        "max": 41,
        "value": 7,
        "step": 10
    },
    {
        "id": "f_val",
        "label": "Focal Length",
        "min": 0,
        "max": int(1.5 * img_height),
        "value": 150,
        "step": 10
    }
]

# --------------------------------------------------------------------
# The generic interactive dictionary.
# For any interactive task you add an entry here.
# (For example, if Task 2 becomes interactive, create its slider config and plot endpoint.)
# --------------------------------------------------------------------
interactive_tasks = {
    6: {
        "title": "Task 6 Interactive Visualization",
        "sliders": task6_sliders,
        "plot_endpoint": "/plot/task6",
        "banned_validation": True,  # indicates that Task 6 needs special banned-range logic
        "extra_context": { "img_width": img_width }  # extra info used in the template
    },
    # You could add more interactive tasks here ...
}

# --------------------------------------------------------------------
# Generic interactive page template.
#
# This template is rendered given a list of slider definitions.
# Each slider definition must include:
#   id, label, min, max, value, and step.
#
# If banned_validation is True, additional JavaScript logic
# is inserted for validating the relationship between sliders.
#
# The image is auto-updated by a URL (i.e. /plot/...) which you pass.
# --------------------------------------------------------------------
interactive_template = '''
<!DOCTYPE html>
<html>
<head>
  <title>{{ title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .slider-container { margin: 20px 0; }
    .slider-block { margin-bottom: 15px; }
    label { font-weight: bold; margin-bottom: 5px; display: block; }
    input[type=range] { width: 100%; }
    .plot-container { text-align: center; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <div class="slider-container">
    {% for slider in sliders %}
      <div class="slider-block">
         <label for="{{ slider.id }}">{{ slider.label }} (<span id="{{ slider.id }}_value">{{ slider.value }}</span>):</label>
         <input type="range" id="{{ slider.id }}" name="{{ slider.id }}" min="{{ slider.min }}" max="{{ slider.max }}" value="{{ slider.value }}" step="{{ slider.step }}">
      </div>
    {% endfor %}
  </div>
  <div class="plot-container">
    <img id="plotImage" src="{{ plot_endpoint }}?{{ initial_query }}" alt="Interactive Plot" style="max-width: 800px; width: 100%;">
  </div>
  <script>
    // Basic function to update the plot from slider values.
    function updatePlot() {
      const params = {};
      {% for slider in sliders %}
        params["{{ slider.id }}"] = document.getElementById("{{ slider.id }}").value;
        document.getElementById("{{ slider.id }}_value").innerText = document.getElementById("{{ slider.id }}").value;
      {% endfor %}
      const query = new URLSearchParams(params);
      // Append a timestamp to prevent caching.
      query.append("_", new Date().getTime());
      document.getElementById("plotImage").src = "{{ plot_endpoint }}?" + query.toString();
    }
    
    {% if banned_validation %}
      // For Task 6 we ban the slider f_val from being in the forbidden zone with respect to start_x.
      var IMG_WIDTH = {{ img_width }};
      var oldValues = {};
      {% for slider in sliders %}
         oldValues["{{ slider.id }}"] = parseInt(document.getElementById("{{ slider.id }}").value);
      {% endfor %}
      
      function sliderChanged(event) {
        var sliderId = event.target.id;
        var newValue = parseInt(event.target.value);
        var start_x = parseInt(document.getElementById("start_x").value);
        var f_val = parseInt(document.getElementById("f_val").value);
        
        // Check the banned condition:
        // If start_x <= f_val <= start_x + IMG_WIDTH then make an adjustment.
        if (sliderId === "start_x") {
          if (start_x <= f_val && f_val <= start_x + IMG_WIDTH) {
            // Determine direction of change.
            if (newValue > oldValues["start_x"]) {
              f_val = f_val + 1;
            } else {
              f_val = f_val - IMG_WIDTH - 1;
            }
            document.getElementById("f_val").value = f_val;
            document.getElementById("f_val_value").innerText = f_val;
          }
        }
        if (sliderId === "f_val") {
          if (start_x <= f_val && f_val <= start_x + IMG_WIDTH) {
            if (newValue > oldValues["f_val"]) {
              f_val = start_x + IMG_WIDTH + 1;
            } else {
              f_val = start_x - 1;
            }
            document.getElementById("f_val").value = f_val;
            document.getElementById("f_val_value").innerText = f_val;
          }
        }
        // Update the old value for this slider.
        oldValues[sliderId] = parseInt(document.getElementById(sliderId).value);
        updatePlot();
      }
    {% endif %}
    
    // Attach event listeners to all sliders.
    {% for slider in sliders %}
      {% if banned_validation %}
        document.getElementById("{{ slider.id }}").addEventListener("input", sliderChanged);
      {% else %}
        document.getElementById("{{ slider.id }}").addEventListener("input", updatePlot);
      {% endif %}
    {% endfor %}
  </script>
</body>
</html>
'''

def render_interactive_page(slider_config, title, plot_endpoint, banned_validation=False, extra_context=None):
    """
    Renders an interactive page using the generic template.
    
    slider_config: list of dicts, one per slider.
    title: title of the page.
    plot_endpoint: URL used for fetching the plot image.
    banned_validation: if True, special validation code is added.
    extra_context: any additional context variables (e.g. img_width).
    """
    if extra_context is None:
        extra_context = {}
    # Build an initial query string from the default slider values.
    initial_params = { slider["id"]: slider["value"] for slider in slider_config }
    initial_query = "&".join([f"{key}={value}" for key, value in initial_params.items()])
    context = {
        "sliders": slider_config,
        "title": title,
        "plot_endpoint": plot_endpoint,
        "initial_query": initial_query,
        "banned_validation": banned_validation
    }
    context.update(extra_context)
    return render_template_string(interactive_template, **context)

# --------------------------------------------------------------------
# The rest of your application: noninteractive tasks, subtasks, etc.
# --------------------------------------------------------------------
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

@app.route('/')
def index():
    """
    Home page showing a grid of tasks.
    """
    tasks = list(range(1, 13))
    return render_template_string(MAIN_TEMPLATE, tasks=tasks)

@app.route('/task/<int:task_id>')
def handle_task(task_id):
    """
    If the task is interactive, redirect to the interactive page.
    If it has subtasks, show the subtask grid.
    Otherwise, run the task file via subprocess.
    """
    if task_id in interactive_tasks:
        return redirect(url_for('interactive_task', task_id=task_id))
    if task_id in [1, 11]:
        subtasks = ['a', 'b'] if task_id == 1 else ['a', 'b', 'c', 'd']
        return render_template_string(SUBTASK_TEMPLATE, task_id=task_id, subtasks=subtasks)
    else:
        filename = f"Task{task_id}.py"
        return run_python_file(filename, task_name=str(task_id))

@app.route('/task/<int:task_id>/<subtask>')
def handle_subtask(task_id, subtask):
    """
    Runs the specified subtask file.
    """
    if task_id in [1, 11]:
        filename = f"Task{task_id}{subtask}.py"
        return run_python_file(filename, task_name=f"{task_id}{subtask}")
    else:
        logging.warning(f"Subtask {task_id}{subtask} is not defined.")
        return render_template_string(DUMMY_TEMPLATE, task_name=f"{task_id}{subtask}")

@app.route('/interactive/<int:task_id>')
def interactive_task(task_id):
    """
    Route for interactive tasks.
    Uses the generic template if an entry exists in interactive_tasks.
    """
    if task_id in interactive_tasks:
        config = interactive_tasks[task_id]
        return render_interactive_page(config["sliders"],
                                       config["title"],
                                       config["plot_endpoint"],
                                       banned_validation=config.get("banned_validation", False),
                                       extra_context=config.get("extra_context", {}))
    else:
        return f"No interactive configuration defined for task {task_id}", 404

def run_python_file(filename, task_name):
    """
    Executes a Python file via subprocess and returns its output.
    """
    if not os.path.isfile(filename):
        logging.warning(f"File {filename} does not exist.")
        return render_template_string(DUMMY_TEMPLATE, task_name=task_name)
    
    try:
        result = subprocess.run(["python", filename],
                                capture_output=True,
                                text=True,
                                timeout=30)
        output = result.stdout + result.stderr
        return render_template_string(OUTPUT_TEMPLATE, task_name=task_name, output=output)
    except subprocess.TimeoutExpired:
        logging.error(f"Execution of {filename} timed out.")
        return render_template_string(OUTPUT_TEMPLATE, task_name=task_name, output="Task execution timed out.")
    except Exception as e:
        logging.error(f"Error executing {filename}: {e}")
        return render_template_string(OUTPUT_TEMPLATE, task_name=task_name, output=f"Error executing task: {e}")

# --------------------------------------------------------------------
# Task 6 Plot Generation
#
# This route is called by the interactive page using the slider values.
# Instead of opening a new window, the code computes the image and returns
# it as a PNG image that the browser displays.
# --------------------------------------------------------------------
@app.route('/plot/task6')
def plot_task6():
    try:
        start_x = int(request.args.get('start_x', task6_sliders[0]["value"]))
        start_y = int(request.args.get('start_y', task6_sliders[1]["value"]))
        scale = int(request.args.get('scale', task6_sliders[2]["value"]))
        f_val = int(request.args.get('f_val', task6_sliders[3]["value"]))
    except Exception as e:
        return "Invalid parameters", 400

    buf = generate_task6_plot(start_x, start_y, scale, f_val)
    return send_file(buf, mimetype='image/png')

def generate_task6_plot(start_x, start_y, scale, f_val):
    """
    Generates the plot for Task 6 similar to your original algorithm,
    but instead of showing the plot, saves it to a PNG buffer.
    """
    t0 = perf_counter()
    # Adjust start_y according to your original code.
    fudge_y = img_height // 2
    start_y_adjusted = (start_y + fudge_y) * -1

    size = max(img_height, img_width) * scale
    canvas_height = size
    canvas_width = int(size * 1.5)
    canvas = np.full((canvas_height, canvas_width, channels), 255, dtype=np.uint8)

    yy, xx = np.indices((img_height, img_width))
    old_x = xx + start_x
    old_y = yy + start_y_adjusted

    new_x_float = - (f_val * old_x) / (old_x - f_val)
    new_x = new_x_float.astype(int)
    new_y_float = (old_y / old_x) * new_x_float
    new_y = new_y_float.astype(int)

    old_y_index = (canvas_height // 2) + old_y
    old_x_index = (canvas_width // 2) + old_x
    new_y_index = (canvas_height // 2) + new_y
    new_x_index = (canvas_width // 2) + new_x

    valid_old = (old_y_index >= 0) & (old_y_index < canvas_height) & \
                (old_x_index >= 0) & (old_x_index < canvas_width)
    valid_new = (new_y_index >= 0) & (new_y_index < canvas_height) & \
                (new_x_index >= 0) & (new_x_index < canvas_width)

    canvas[old_y_index[valid_old], old_x_index[valid_old]] = image[yy[valid_old], xx[valid_old]]
    canvas[new_y_index[valid_new], new_x_index[valid_new]] = image[yy[valid_new], xx[valid_new]]

    # Compute bounding box for the new projection.
    all_new_x = new_x_index[valid_new].ravel()
    all_new_y = new_y_index[valid_new].ravel()
    raw_min_x = int(all_new_x.min())
    raw_max_x = int(all_new_x.max())
    raw_min_y = int(all_new_y.min())
    raw_max_y = int(all_new_y.max())

    minimum_x = max(raw_min_x, 0)
    maximum_x = min(raw_max_x, canvas_width - 1)
    minimum_y = max(raw_min_y, 0)
    maximum_y = min(raw_max_y, canvas_height - 1)

    # Interpolation functions to fix blank areas.
    def fix_row(row, left, right):
        cols = np.arange(left, right+1)
        row_slice = canvas[row, left:right+1]
        mask = (row_slice != 255).any(axis=1)
        if mask.sum() < 2:
            return
        filled_cols = cols[mask]
        seg_left = filled_cols[0]
        seg_right = filled_cols[-1]
        interp_cols = np.arange(seg_left, seg_right+1)
        for ch in range(channels):
            xp = filled_cols
            fp = row_slice[mask, ch]
            interpolated = np.interp(interp_cols, xp, fp)
            canvas[row, interp_cols, ch] = np.around(interpolated).astype(np.uint8)

    def fix_col(col, top, bottom):
        rows = np.arange(top, bottom+1)
        col_slice = canvas[top:bottom+1, col]
        mask = (col_slice != 255).any(axis=1)
        if mask.sum() < 2:
            return
        filled_rows = rows[mask]
        seg_top = filled_rows[0]
        seg_bottom = filled_rows[-1]
        interp_rows = np.arange(seg_top, seg_bottom+1)
        for ch in range(channels):
            xp = filled_rows
            fp = col_slice[mask, ch]
            interpolated = np.interp(interp_rows, xp, fp)
            canvas[interp_rows, col, ch] = np.around(interpolated).astype(np.uint8)

    for col in range(minimum_x, maximum_x+1):
        fix_col(col, minimum_y, maximum_y)
    for row in range(minimum_y, maximum_y+1):
        fix_row(row, minimum_x, maximum_x)

    t_elapsed = perf_counter() - t0
    print("Task 6 processing time: {:.4f} seconds".format(t_elapsed))

    # Create the matplotlib figure.
    fig, ax = plt.subplots(figsize=(8, 6))
    extent_val = [-canvas_width // 2, canvas_width // 2, -canvas_height // 2, canvas_height // 2]
    ax.imshow(canvas, extent=extent_val)
    ax.set_xlim(extent_val[0], extent_val[1])
    ax.set_ylim(extent_val[2], extent_val[3])
    ax.axvline(x=0, color='black', linestyle='--')
    ax.scatter(f_val, 0, color='red', marker='*')
    ax.scatter(-f_val, 0, color='red', marker='*')
    ax.set_title(f"Task 6: start_x = {start_x}, start_y (adjusted) = {start_y_adjusted}")
    
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(debug=True, host='0.0.0.0', port=port)

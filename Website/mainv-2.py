# main.py
import os
import io
import uuid
import logging
import subprocess
from time import perf_counter, time

from flask import Flask, render_template_string, url_for, send_file, request, redirect
import matplotlib.pyplot as plt
import numpy as np

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------
# Global interrupt management
#
# For each interactive task (by key) we keep the latest request ID.
# When a new slider update occurs, the new request ID is stored and
# any long-running computation checking periodically via check_interrupt()
# will abort if it finds its stored ID is no longer current.
# --------------------------------------------------------------------
active_requests = {}  # e.g., {"task6": <uuid>, "task5": <uuid>}

def check_interrupt(task_key, request_id):
    """
    Check if the current computation is still the latest for the given task;
    if not, abort processing by raising an exception.
    """
    if active_requests.get(task_key) != request_id:
        raise Exception("Aborted: a newer slider update was received.")

# --------------------------------------------------------------------
# Global image loading (used by both tasks)
#
# For Task 6 and Task 5 we assume an image file is available.
# (For Task 5 you might later want to add a user selection widget.)
# --------------------------------------------------------------------
# Here we load "Tall1.jpg" as before.
image_file = "Tall1.jpg"
if os.path.exists(image_file):
    image = plt.imread(image_file)
    img_height, img_width, channels = image.shape
else:
    logging.error("Image file Tall1.jpg not found!")
    image = None
    img_height = img_width = channels = 0

# For Task 5, we use the same image and dimensions.
H, W = img_height, img_width

# --------------------------------------------------------------------
# Functions for Task 5 (canvas creation)
# --------------------------------------------------------------------
def compute_S(offset_x, offset_y):
    """
    Compute a square canvas side length S (in pixels) that is as small as possible
    while ensuring both copies of the image (with the given offsets) will be fully contained.
    This is based on an initial factor of 4 * max(W, H) plus additional requirements.
    """
    base = 4 * max(W, H)
    req_x = 4 * ((W - 1) + offset_x)
    req_y = H + 2 * abs(offset_y)
    return int(max(base, req_x, req_y))

def create_canvas(S, offset_x, offset_y, request_id, task_key):
    """
    Create a square white canvas (S x S) and draw two copies of the image:
      - The "right" copy, drawn normally.
      - The "left" copy is a mirrored copy.
    The center of the image is placed at (S//2 + offset_x, S//2 + offset_y).
    Periodically checks for interruption.
    """
    canvas = np.full((S, S, image.shape[2]), 255, dtype=np.uint8)
    center_x = S // 2
    center_y = S // 2 + offset_y

    for y in range(H):
        if y % 10 == 0:
            check_interrupt(task_key, request_id)
        for x in range(W):
            colour = image[y, x]
            # Right (normal) copy:
            old_x = center_x + S // 4 + x + offset_x
            old_y = center_y - H // 2 + y
            # Left (mirrored) copy:
            new_x = center_x - S // 4 - x - offset_x
            new_y = center_y - H // 2 + y
            if 0 <= old_x < S and 0 <= old_y < S:
                canvas[old_y, old_x] = colour
            if 0 <= new_x < S and 0 <= new_y < S:
                canvas[new_y, new_x] = colour
    return canvas

def generate_task5_plot(offset_x, offset_y, request_id):
    """
    Generate the Task 5 plot: two copies of the image (normal and mirrored)
    displayed on a square canvas.
    """
    S = compute_S(offset_x, -offset_y)
    # Create canvas with interruption checks during nested loops.
    canvas = create_canvas(S, offset_x, -offset_y, request_id, "task5")
    
    # Create the matplotlib figure.
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.imshow(canvas, extent=[-2, 2, -2, 2])
    ax.axvline(x=0, color='black', linestyle='--')
    ax.set_title(f"Offset X: {offset_x}, Offset Y: {offset_y}\nCanvas Size: {S}px")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

# --------------------------------------------------------------------
# Functions for Task 6 (image projection)
# --------------------------------------------------------------------
def generate_task6_plot(start_x, start_y, scale, f_val, request_id):
    """
    Generate the Task 6 projection plot using your algorithm.
    This function periodically checks for interruption.
    """
    t0 = perf_counter()
    # Adjust start_y as in your original code.
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

    # --- Interpolation functions with periodic interruption checks ---
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
        interp_rows = np.arange(filled_rows[0], filled_rows[-1]+1)
        for ch in range(channels):
            xp = filled_rows
            fp = col_slice[mask, ch]
            interpolated = np.interp(interp_rows, xp, fp)
            canvas[interp_rows, col, ch] = np.around(interpolated).astype(np.uint8)
    
    # Run interpolation loops with interruption checks every 10 iterations.
    for col in range(minimum_x, maximum_x+1):
        if (col - minimum_x) % 10 == 0:
            check_interrupt("task6", request_id)
        fix_col(col, minimum_y, maximum_y)
    for row in range(minimum_y, maximum_y+1):
        if (row - minimum_y) % 10 == 0:
            check_interrupt("task6", request_id)
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
    ax.set_title(f"Task 6: start_x = {start_x}, start_y (adj) = {start_y_adjusted}")
    
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)
    return buf

def generate_blank_image():
    """
    Return a simple blank image indicating that the computation was cancelled.
    """
    fig, ax = plt.subplots(figsize=(4,4))
    ax.text(0.5, 0.5, 'Cancelled', horizontalalignment='center',
            verticalalignment='center', transform=ax.transAxes, fontsize=16)
    ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

# --------------------------------------------------------------------
# Interactive Page Template (generic)
#
# The template is built from a list of slider definitions and parameters.
# A spinner is overlaid on the plot and shown while a new plot is loading.
# If "banned_validation" is True (for Task 6) extra JS is added.
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
    .plot-container { position: relative; text-align: center; }
    /* Spinner CSS */
    .spinner {
      border: 8px solid #f3f3f3;
      border-top: 8px solid #3498db;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      animation: spin 1s linear infinite;
      position: absolute;
      left: 50%;
      top: 50%;
      margin-left: -20px;
      margin-top: -20px;
      z-index: 10;
      display: none;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
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
    <div id="spinner" class="spinner"></div>
  </div>
  <script>
    function updatePlot() {
      const params = {};
      {% for slider in sliders %}
        params["{{ slider.id }}"] = document.getElementById("{{ slider.id }}").value;
        document.getElementById("{{ slider.id }}_value").innerText = document.getElementById("{{ slider.id }}").value;
      {% endfor %}
      const query = new URLSearchParams(params);
      query.append("_", new Date().getTime());
      // Show spinner while waiting for new plot.
      document.getElementById("spinner").style.display = "block";
      document.getElementById("plotImage").src = "{{ plot_endpoint }}?" + query.toString();
    }
    
    {% if banned_validation %}
      // For banned_validation (Task 6), special logic is added.
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
        
        // Banned condition: disallow f_val from being within start_x and start_x+IMG_WIDTH.
        if (sliderId === "start_x") {
          if (start_x <= f_val && f_val <= start_x + IMG_WIDTH) {
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
        oldValues[sliderId] = parseInt(document.getElementById(sliderId).value);
        updatePlot();
      }
    {% endif %}
    
    // Attach event listeners.
    {% for slider in sliders %}
      {% if banned_validation %}
        document.getElementById("{{ slider.id }}").addEventListener("input", sliderChanged);
      {% else %}
        document.getElementById("{{ slider.id }}").addEventListener("input", updatePlot);
      {% endif %}
    {% endfor %}
    
    // Hide spinner when image loads.
    document.getElementById("plotImage").addEventListener("load", function() {
      document.getElementById("spinner").style.display = "none";
    });
  </script>
</body>
</html>
'''

def render_interactive_page(slider_config, title, plot_endpoint, banned_validation=False, extra_context=None):
    """
    Renders an interactive page using the generic template.
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
# Interactive Tasks Configuration
#
# Here we define the slider configuration for each interactive task.
# --------------------------------------------------------------------
offset_range = max(W, H)
task6_sliders = [
    {
        "id": "start_x",
        "label": "Start X",
        "min": -int(1 * img_width),
        "max": int(2.5 * img_width),
        "value": 60,
        "step": 1
    },
    {
        "id": "start_y",
        "label": "Start Y",
        "min": -int(1.5 * img_height),
        "max": int(1.5 * img_height),
        "value": 0,
        "step": 1
    },
    {
        "id": "scale",
        "label": "Canvas Scale",
        "min": 1,
        "max": 41,
        "value": 7,
        "step": 1
    },
    {
        "id": "f_val",
        "label": "Focal Length",
        "min": 0,
        "max": int(1.5 * img_height),
        "value": 150,
        "step": 1
    }
]

task5_sliders = [
    {
        "id": "offset_x",
        "label": "Object X (px)",
        "min": -offset_range,
        "max": offset_range,
        "value": 0,
        "step": 1
    },
    {
        "id": "offset_y",
        "label": "Object Y (px)",
        "min": -offset_range,
        "max": offset_range,
        "value": 0,
        "step": 1
    }
]

interactive_tasks = {
    6: {
        "title": "Task 6 Interactive Visualization",
        "sliders": task6_sliders,
        "plot_endpoint": "/plot/task6",
        "banned_validation": True,
        "extra_context": { "img_width": img_width }
    },
    5: {
        "title": "Task 5 Interactive Visualization",
        "sliders": task5_sliders,
        "plot_endpoint": "/plot/task5",
        "banned_validation": False
    }
}

# --------------------------------------------------------------------
# Other Templates for noninteractive tasks (unchanged)
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

# --------------------------------------------------------------------
# Flask Routes
# --------------------------------------------------------------------
@app.route('/')
def index():
    tasks = list(range(1, 13))
    return render_template_string(MAIN_TEMPLATE, tasks=tasks)

@app.route('/task/<int:task_id>')
def handle_task(task_id):
    # For interactive tasks (e.g., 5 and 6) redirect to the interactive page.
    if task_id in interactive_tasks:
        return redirect(url_for('interactive_task', task_id=task_id))
    # For tasks with subtasks (example: Task 1 and 11):
    if task_id in [1, 11]:
        subtasks = ['a', 'b'] if task_id == 1 else ['a', 'b', 'c', 'd']
        return render_template_string(SUBTASK_TEMPLATE, task_id=task_id, subtasks=subtasks)
    else:
        filename = f"Task{task_id}.py"
        return run_python_file(filename, task_name=str(task_id))

@app.route('/task/<int:task_id>/<subtask>')
def handle_subtask(task_id, subtask):
    if task_id in [1, 11]:
        filename = f"Task{task_id}{subtask}.py"
        return run_python_file(filename, task_name=f"{task_id}{subtask}")
    else:
        logging.warning(f"Subtask {task_id}{subtask} is not defined.")
        return render_template_string(DUMMY_TEMPLATE, task_name=f"{task_id}{subtask}")

@app.route('/interactive/<int:task_id>')
def interactive_task(task_id):
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
# Plot Routes for Interactive Tasks
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
    try:
        current_id = str(uuid.uuid4())
        active_requests["task6"] = current_id
        buf = generate_task6_plot(start_x, start_y, scale, f_val, current_id)
        return send_file(buf, mimetype='image/png')
    except Exception as e:
        logging.info("Task 6 aborted: " + str(e))
        return send_file(generate_blank_image(), mimetype='image/png')

@app.route('/plot/task5')
def plot_task5():
    try:
        offset_x = int(request.args.get('offset_x', task5_sliders[0]["value"]))
        offset_y = int(request.args.get('offset_y', task5_sliders[1]["value"]))
    except Exception as e:
        return "Invalid parameters", 400
    try:
        current_id = str(uuid.uuid4())
        active_requests["task5"] = current_id
        buf = generate_task5_plot(offset_x, offset_y, current_id)
        return send_file(buf, mimetype='image/png')
    except Exception as e:
        logging.info("Task 5 aborted: " + str(e))
        return send_file(generate_blank_image(), mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(debug=True, host='0.0.0.0', port=port)

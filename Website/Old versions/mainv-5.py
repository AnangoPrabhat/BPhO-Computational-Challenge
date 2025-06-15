# main.py
import os
import io
import uuid
import logging
from math import isqrt, cos, sin, radians, pi
from time import perf_counter
from flask import Flask, request, redirect, url_for
from werkzeug.utils import secure_filename
import os
from PIL import Image
import numpy as np


from flask import Flask, render_template_string, url_for, send_file, request, redirect
import matplotlib.pyplot as plt
import numpy as np

# Additional matplotlib imports
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from werkzeug.utils import secure_filename

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Configure upload folder and maximum dimensions for user uploaded images
UPLOAD_FOLDER = './uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
MAX_DIMENSION = 100  # maximum width or height (in pixels)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

########################################
# GLOBAL INTERRUPT MANAGEMENT
########################################
# For each interactive task, store latest request ID.
active_requests = {}  # e.g. {"3": request_id, "6": request_id, ...}

def check_interrupt(task_key, request_id):
    if active_requests.get(task_key) != request_id:
        raise Exception("Aborted: a newer slider update was received.")

########################################
# GLOBAL IMAGE LOADING
########################################
# Load a default image. (User may upload a new image via the upload form.)
DEFAULT_IMAGE = "Tall1.jpg"
def load_global_image(filename):
    if os.path.exists(filename):
        return plt.imread(filename)
    else:
        logging.error(f"Image file {filename} not found!")
        return None

global_image = load_global_image(DEFAULT_IMAGE)
if global_image is not None:
    img_height, img_width, channels = global_image.shape
else:
    img_height = img_width = channels = 0

H, W = img_height, img_width

########################################
# GENERIC BLANK IMAGE (for aborted computations)
########################################
def generate_blank_image():
    fig, ax = plt.subplots(figsize=(4,4))
    ax.text(0.5, 0.5, 'Cancelled', horizontalalignment='center',
            verticalalignment='center', transform=ax.transAxes, fontsize=16)
    ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

########################################
# INTERACTIVE TEMPLATE WITH SPINNER AND ANIMATION
########################################
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
    .spinner {
      border: 10px solid #f3f3f3;
      border-top: 10px solid #3498db;
      border-radius: 50%;
      width: 60px;
      height: 60px;
      animation: spin 1s linear infinite;
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      z-index: 10;
      display: none;
    }
    .loading-text {
      position: absolute;
      top: 65%;
      left: 50%;
      transform: translateX(-50%);
      font-size: 1.2em;
      color: #3498db;
      z-index: 10;
      display: none;
    }
    .play-button {
      padding: 15px 25px;
      background-color: #28a745;
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 1em;
      cursor: pointer;
      margin-bottom: 15px;
    }
    .play-button:hover { background-color: #1e7e34; }
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
  {% if playable %}
    <button class="play-button" id="playButton">Play Animation</button>
  {% endif %}
  <div class="plot-container">
    <img id="plotImage" src="{{ plot_endpoint }}?{{ initial_query }}" alt="Interactive Plot" style="max-width: 800px; width: 100%;">
    <div id="spinner" class="spinner"></div>
    <div id="loadingText" class="loading-text">Processing...</div>
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
      document.getElementById("spinner").style.display = "block";
      document.getElementById("loadingText").style.display = "block";
      document.getElementById("plotImage").src = "{{ plot_endpoint }}?" + query.toString();
    }
    {% if banned_validation %}
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
        if (sliderId === "start_x") {
          if (start_x <= f_val && f_val <= start_x + IMG_WIDTH) {
            if (newValue > oldValues["start_x"]) { f_val = f_val + 1; }
            else { f_val = f_val - IMG_WIDTH - 1; }
            document.getElementById("f_val").value = f_val;
            document.getElementById("f_val_value").innerText = f_val;
          }
        }
        if (sliderId === "f_val") {
          if (start_x <= f_val && f_val <= start_x + IMG_WIDTH) {
            if (newValue > oldValues["f_val"]) { f_val = start_x + IMG_WIDTH + 1; }
            else { f_val = start_x - 1; }
            document.getElementById("f_val").value = f_val;
            document.getElementById("f_val_value").innerText = f_val;
          }
        }
        oldValues[sliderId] = parseInt(document.getElementById(sliderId).value);
        updatePlot();
      }
    {% endif %}
    {% for slider in sliders %}
      {% if banned_validation %}
        document.getElementById("{{ slider.id }}").addEventListener("input", sliderChanged);
      {% else %}
        document.getElementById("{{ slider.id }}").addEventListener("input", updatePlot);
      {% endif %}
    {% endfor %}
    document.getElementById("plotImage").addEventListener("load", function() {
      document.getElementById("spinner").style.display = "none";
      document.getElementById("loadingText").style.display = "none";
    });
    {% if playable %}
      // Animation code: slow the animation (e.g., 1000 ms per step) and clear any existing animation.
      var currentAnimation = null;
      document.getElementById("playButton").addEventListener("click", function() {
         if (currentAnimation) { clearInterval(currentAnimation); }
         var slider = document.getElementById("{{ sliders[0].id }}");
         var startVal = parseFloat(slider.min);
         var endVal = parseFloat(slider.max);
         var interval = 1000; // 1 second per step
         slider.value = startVal;
         document.getElementById("{{ sliders[0].id }}_value").innerText = startVal;
         updatePlot();
         var current = startVal;
         currentAnimation = setInterval(function() {
            current += parseFloat(slider.step);
            if (current > endVal) {
               clearInterval(currentAnimation);
               currentAnimation = null;
            } else {
               slider.value = current;
               document.getElementById("{{ sliders[0].id }}_value").innerText = current;
               updatePlot();
            }
         }, interval);
      });
    {% endif %}
  </script>
</body>
</html>
'''

def render_interactive_page(slider_config, title, plot_endpoint, banned_validation=False, extra_context=None, playable=False):
    if extra_context is None:
        extra_context = {}
    initial_params = { slider["id"]: slider["value"] for slider in slider_config }
    initial_query = "&".join([f"{key}={value}" for key, value in initial_params.items()])
    context = {
        "sliders": slider_config,
        "title": title,
        "plot_endpoint": plot_endpoint,
        "initial_query": initial_query,
        "banned_validation": banned_validation,
        "playable": playable
    }
    context.update(extra_context)
    return render_template_string(interactive_template, **context)

########################################
# INTERACTIVE TASKS CONFIGURATION
########################################
interactive_tasks = {
    "3": {
        "title": "Task 3 Interactive: Reflection Travel Time",
        "sliders": [
            {"id": "v", "label": "Speed (m/s)", "min": 300000000, "max": 3000000000, "value": 300000000, "step": 10000000},
            {"id": "n", "label": "Refractive Index", "min": 1, "max": 3, "value": 1, "step": 0.1},
            {"id": "y", "label": "Height", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "l", "label": "Length (cm)", "min": 10, "max": 300, "value": 100, "step": 10}
        ],
        "plot_endpoint": "/plot/3",
        "banned_validation": False
    },
    "4": {
        "title": "Task 4 Interactive: Thin Lens Verification",
        "sliders": [
            {"id": "v", "label": "Speed (m/s)", "min": 300000000, "max": 3000000000, "value": 300000000, "step": 10000000},
            {"id": "n1", "label": "Refractive Index 1", "min": 1, "max": 3, "value": 1, "step": 0.1},
            {"id": "n2", "label": "Refractive Index 2", "min": 1, "max": 3, "value": 1, "step": 0.1},
            {"id": "y", "label": "Height", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "l", "label": "Length (cm)", "min": 10, "max": 300, "value": 100, "step": 10}
        ],
        "plot_endpoint": "/plot/4",
        "banned_validation": False
    },
    "5": {
        "title": "Task 5 Interactive: Virtual Image Plot",
        "sliders": [
            {"id": "offset_x", "label": "Offset X (px)", "min": -max(W,H), "max": max(W,H), "value": 0, "step": 1},
            {"id": "offset_y", "label": "Offset Y (px)", "min": -max(W,H), "max": max(W,H), "value": 0, "step": 1},
            {"id": "canvas_size", "label": "Canvas Size (px)", "min": int(4*max(W,H)*0.5), "max": int(4*max(W,H)*2), "value": int(4*max(W,H)), "step": 10}
        ],
        "plot_endpoint": "/plot/5",
        "banned_validation": False
    },
    "6": {
        "title": "Task 6 + 7 Interactive: Real, Inverted Image (Outside Focal Range)",
        "sliders": [
            {"id": "start_x", "label": "Start X", "min": -int(1*img_width), "max": int(2.5*img_width), "value": 60, "step": 1},
            {"id": "start_y", "label": "Start Y", "min": -int(1.5*img_height), "max": int(1.5*img_height), "value": 0, "step": 1},
            {"id": "scale", "label": "Canvas Scale", "min": 1, "max": 41, "value": 7, "step": 1},
            {"id": "f_val", "label": "Focal Length", "min": 0, "max": int(1.5*img_height), "value": 150, "step": 1}
        ],
        "plot_endpoint": "/plot/6",
        "banned_validation": True,
        "extra_context": {"img_width": img_width}
    },
    "8": {
        "title": "Task 8 Interactive: Concave Mirror Model",
        "sliders": [
            {"id": "start_x", "label": "Start X", "min": int(0.5*img_width), "max": int(img_width), "value": int(0.8*img_width), "step": 1},
            {"id": "start_y", "label": "Start Y", "min": -img_height, "max": 0, "value": -img_height, "step": 1},
            {"id": "rad_multiplier", "label": "Radial Multiplier", "min": 1, "max": 3, "value": 2, "step": 0.1}
        ],
        "plot_endpoint": "/plot/8",
        "banned_validation": False
    },
    "9": {
        "title": "Task 9 Interactive: Convex Mirror Model",
        "sliders": [
            {"id": "start_x", "label": "Start X", "min": int(0.5*img_width), "max": int(img_width), "value": int(img_width), "step": 1},
            {"id": "start_y", "label": "Start Y", "min": -img_height, "max": 0, "value": int(-0.5*img_height), "step": 1},
            {"id": "rad_multiplier", "label": "Radial Multiplier", "min": 1, "max": 4, "value": 3.5, "step": 0.1}
        ],
        "plot_endpoint": "/plot/9",
        "banned_validation": False
    },
    "10": {
        "title": "Task 10 Interactive: Anamorphic Image Mapping",
        "sliders": [
            {"id": "Rf", "label": "Projection Scale (Rₑ)", "min": 1, "max": 10, "value": 3, "step": 0.1},
            {"id": "arc_angle", "label": "Arc Angle (deg)", "min": 0, "max": 360, "value": 160, "step": 1}
        ],
        "plot_endpoint": "/plot/10",
        "banned_validation": False
    },
    "11d": {
        "title": "Task 11d Interactive: Rainbow Elevation Angles",
        "sliders": [
            {"id": "alpha", "label": "Alpha (deg)", "min": 0, "max": 60, "value": 0, "step": 1}
        ],
        "plot_endpoint": "/plot/11d",
        "banned_validation": False,
        "playable": True
    }
}

########################################
# TASK OVERVIEW AND BUTTON LABELS (3-word descriptions)
########################################
# These appear on the main page’s task buttons.
task_overview = {
    "1": {
        "title": "Task 1",
        "desc": (
            "TASK 1a: Use the Sellmeier formula to plot the refractive index of crown glass vs wavelength "
            "and TASK 1b: plot the refractive index of water vs frequency."
        ),
        "subtasks": {"1a": "Refractive Index of Crown Glass", 
                     "1b": "Water Refractive Index Plot"},
        "button_text": "Refractive Index Plot"
    },
    "2": {
        "title": "Task 2",
        "desc": (
            "Assess the veracity of the thin lens equation by plotting 1/v vs 1/u and determining the focal length."
        ),
        "subtasks": {},
        "button_text": "Thin Lens Verification"
    },
    "3": {
        "title": "Task 3",
        "desc": (
            "Plot the travel time for a ray reflecting off a surface to demonstrate Fermat’s principle (reflection)."
        ),
        "subtasks": {},
        "button_text": "Reflection Travel Time"
    },
    "4": {
        "title": "Task 4",
        "desc": (
            "Plot the travel time for a refracted ray to demonstrate Snell’s law via Fermat’s principle."
        ),
        "subtasks": {},
        "button_text": "Refraction Travel Time"
    },
    "5": {
        "title": "Task 5",
        "desc": (
            "Compute and plot the virtual image of an object in a plane mirror."
        ),
        "subtasks": {},
        "button_text": "Virtual Image Plot"
    },
    "6": {
        "title": "Task 6 + 7",
        "desc": (
            "Model the real, inverted image of an object placed outside the focal range of a thin lens."
        ),
        "subtasks": {},
        "button_text": "Real Image Model"
    },
    "8": {
        "title": "Task 8",
        "desc": (
            "Create a model for the real image of an object in a concave spherical mirror."
        ),
        "subtasks": {},
        "button_text": "Concave Mirror Model"
    },
    "9": {
        "title": "Task 9",
        "desc": (
            "Model the virtual image of an object in a convex spherical mirror."
        ),
        "subtasks": {},
        "button_text": "Convex Mirror Model"
    },
    "10": {
        "title": "Task 10",
        "desc": (
            "Map pixel coordinates to an anamorphic projection using a polished cylinder."
        ),
        "subtasks": {},
        "button_text": "Anamorphic Image Mapping"
    },
    "11": {
        "title": "Task 11",
        "desc": (
            "Plot the elevation angles of primary and secondary rainbows using Descartes’ model."
        ),
        "subtasks": {
            "11a": "Elevation angles using computed ε curves",
            "11b": "Rainbow curve color mapping",
            "11c": "Scatter plot for refraction angles",
            "11d": "Interactive refraction circles"
        },
        "button_text": "Rainbow Elevation Angles"
    },
    "12": {
        "title": "Task 12",
        "desc": "Dynamic model of a beam of white light through a triangular prism. (Not implemented yet.)",
        "subtasks": {},
        "button_text": "Prism Light Path"
    }
}

########################################
# MAIN PAGE TEMPLATE (big buttons with 3-word labels and an image upload form)
########################################
main_page_template = '''
<!DOCTYPE html>
<html>
<head>
  <title>Challenge Tasks</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f0f0f0; }
    .container { display: flex; flex-wrap: wrap; justify-content: center; padding: 20px; }
    .button {
      background-color: #007BFF; color: white; border: none; border-radius: 10px;
      font-size: 1.5em; margin: 10px; padding: 25px; width: 90%; max-width: 400px;
      text-align: center; text-decoration: none; transition: background-color 0.3s;
      box-shadow: 0px 3px 6px rgba(0,0,0,0.2);
    }
    .button:hover { background-color: #0056b3; }
    .button span { display: block; font-size: 0.8em; margin-top: 8px; }
    .upload-form { margin-top: 30px; text-align: center; }
    .upload-button {
      background-color: #28a745; color: white; padding: 10px 20px; border: none;
      border-radius: 8px; font-size: 1em; cursor: pointer; margin-top: 10px;
    }
    .upload-button:hover { background-color: #1e7e34; }
  </style>
</head>
<body>
  <h1 style="text-align:center;">Challenge Tasks</h1>
  <div class="container">
    {% for key, task in tasks.items() %}
      <a class="button" href="{% if task.subtasks|length > 0 %}{{ url_for('subtask_page', task_id=key) }}{% else %}{{ url_for('handle_task', task_id=key) }}{% endif %}" title="{{ task.desc }}">
        {{ task.title }}<br><span>{{ task.button_text }}</span>
      </a>
    {% endfor %}
  </div>
  <!-- Image Upload Form -->
  <div class="upload-form">
    <form method="POST" action="{{ url_for('upload') }}" enctype="multipart/form-data">
      <label for="image_file">Upload Your Image (max dimension: {{ max_dimension }} px):</label><br>
      <input type="file" name="image_file" id="image_file" accept="image/*"><br>
      <button type="submit" class="upload-button">Upload</button>
    </form>
  </div>
</body>
</html>
'''

########################################
# SUBTASK PAGE TEMPLATE
########################################
subtask_page_template = '''
<!DOCTYPE html>
<html>
<head>
  <title>{{ task.title }} - Subtasks</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f8f8f8; }
    .container { display: flex; flex-direction: column; align-items: center; padding: 20px; }
    .button {
      background-color: #28a745; color: white; border: none; border-radius: 10px;
      font-size: 1.4em; margin: 10px; padding: 25px; width: 90%; max-width: 400px;
      text-align: center; text-decoration: none; transition: background-color 0.3s;
      box-shadow: 0px 3px 6px rgba(0,0,0,0.2);
    }
    .button:hover { background-color: #1e7e34; }
    .back-button {
      background-color: #007BFF; color: white; padding: 15px 25px; border: none;
      border-radius: 8px; font-size: 1.2em; text-decoration: none; margin-top: 20px;
    }
    .back-button:hover { background-color: #0056b3; }
  </style>
</head>
<body>
  <h1 style="text-align:center;">{{ task.title }}</h1>
  <div class="container">
    {% for subkey, subdesc in task.subtasks.items() %}
      <a class="button" href="{{ url_for('handle_task', task_id=subkey) }}" title="{{ subdesc }}">
         {{ subkey }}<br><span>{{ task_overview[subkey].button_text if task_overview.get(subkey) else "" }}</span>
      </a>
    {% endfor %}
    <a class="back-button" href="{{ url_for('index') }}">Back to Home</a>
  </div>
</body>
</html>
'''

########################################
# DUMMY PAGE TEMPLATE (for Task 12)
########################################
dummy_page_template = '''
<!DOCTYPE html>
<html>
<head>
  <title>{{ title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; background: #fff; padding: 20px; text-align: center; }
    .button {
      background-color: #007BFF; color: white; padding: 15px 25px; border: none;
      border-radius: 8px; font-size: 1.2em; text-decoration: none; margin-top: 20px;
    }
    .button:hover { background-color: #0056b3; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <p>{{ message }}</p>
  <a class="button" href="{{ url_for('index') }}">Back to Home</a>
</body>
</html>
'''

########################################
# ROUTE: Main Page with Upload Form
########################################
@app.route('/')
def index():
    return render_template_string(main_page_template, tasks=task_overview, max_dimension=MAX_DIMENSION)

########################################
# ROUTE: Subtask Page
########################################
@app.route('/subtask/<task_id>')
def subtask_page(task_id):
    if task_id in task_overview and task_overview[task_id]["subtasks"]:
        return render_template_string(subtask_page_template, task=task_overview[task_id], task_overview=task_overview)
    else:
        return f"No subtasks for task {task_id}.", 404

########################################
# ROUTE: Handle Task (Static / Interactive / Dummy for Task 12)
########################################
@app.route('/task/<task_id>')
def handle_task(task_id):
    if task_id == "7":
        return redirect(url_for('handle_task', task_id="6"))
    if task_id in interactive_tasks:
        return redirect(url_for('interactive_task', task_id=task_id))
    elif task_id in static_tasks:
        page = '''
        <!DOCTYPE html>
        <html>
        <head>
          <title>Task {{ task_id }}</title>
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 20px; }
            .back-button {
              background-color: #007BFF; color: white; padding: 15px 25px; border: none;
              border-radius: 8px; font-size: 1.2em; text-decoration: none; margin-top: 20px;
            }
            .back-button:hover { background-color: #0056b3; }
          </style>
        </head>
        <body>
          <h1>Task {{ task_id }}</h1>
          <img src="{{ url_for('plot_task', task_id=task_id) }}" style="max-width:800px;width:100%;">
          <br>
          <a class="back-button" href="{{ url_for('index') }}">Back to Home</a>
        </body>
        </html>
        '''
        return render_template_string(page, task_id=task_id)
    elif task_id == "12":
        return render_template_string(dummy_page_template, title="Task 12", message="Not Implemented Yet")
    else:
        return f"Task {task_id} is not defined.", 404

########################################
# ROUTE: Interactive Task
########################################
@app.route('/interactive/<task_id>')
def interactive_task(task_id):
    if task_id in interactive_tasks:
        config = interactive_tasks[task_id]
        playable = config.get("playable", False)
        return render_interactive_page(slider_config=config["sliders"],
                                       title=config["title"],
                                       plot_endpoint=config["plot_endpoint"],
                                       banned_validation=config.get("banned_validation", False),
                                       extra_context=config.get("extra_context", {}),
                                       playable=playable)
    else:
        return f"No interactive configuration defined for task {task_id}", 404

########################################
# ROUTE: Plot Endpoint (for both Interactive and Static Tasks)
########################################


########################################
# STATIC TASKS FUNCTIONS
########################################
def generate_task1a_plot():
    def crown_glass(Lambda):
        x = Lambda/1000
        a = np.array([1.03961212, 0.231792344, 1.01146945])
        b = np.array([0.00600069867, 0.0200179144, 103.560653])
        y = np.zeros(x.size)
        for i in range(len(a)):
            y += (a[i]*(x**2))/((x**2)-b[i])
        return np.sqrt(1+y)
    Lambda = np.linspace(400, 800, 10000)
    RefractiveIndex = crown_glass(Lambda)
    plt.figure()
    plt.plot(Lambda, RefractiveIndex)
    plt.title("Refractive index of crown glass vs wavelength")
    plt.xlabel("$\\lambda$ (nm)")
    plt.ylabel("n")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def generate_task1b_plot():
    rainbow = [(1,0,0),(1,0.3,0),(1,1,0),(0,1,0),(0,0,1),(0.29,0,0.51),(0.58,0,0.83)]
    colourmap = LinearSegmentedColormap.from_list("colours", rainbow)
    frequency = np.linspace(405,790,10000)
    RefractiveIndex = (1+((1/(1.731-0.261*((frequency/1000)**2)))**0.5))**0.5
    points = np.array([frequency, RefractiveIndex]).T.reshape(-1,1,2)
    lines = np.concatenate([points[:-1], points[1:]], axis=1)
    ColourLines = LineCollection(lines, cmap=colourmap, linewidth=2.5)
    ColourLines.set_array(frequency)
    fig, ax = plt.subplots()
    ax.add_collection(ColourLines)
    ax.set_xlim(405,790)
    ax.set_ylim(1.33, RefractiveIndex.max())
    plt.title("Refractive index of water vs Frequency")
    plt.xlabel("Frequency (THz)")
    plt.ylabel("n")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_task2_plot():
    u = np.linspace(20,55,8)
    v = np.array([65.5,40,31,27,25,23.1,21.5,20.5])
    m, c = np.polyfit(1/u, 1/v, 1)
    plt.figure()
    plt.scatter(1/u, 1/v, color="red", zorder=2)
    plt.plot(1/u, m*(1/u)+c, zorder=1)
    plt.title(f"Gradient: {round(m,4)}; Y-intercept: {round(c,4)}")
    plt.xlabel("1/u (cm⁻¹)")
    plt.ylabel("1/v (cm⁻¹)")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def generate_task11a_plot():
    Theta = np.linspace(0, pi/2, 10000)
    def convert(frequency, color_name):
        n = (1+((1/(1.731-0.261*((frequency/1000)**2)))**0.5))**0.5
        Epsilon1 = pi - 6*np.arcsin(np.sin(Theta)/n) + 2*Theta
        Epsilon2 = 4*np.arcsin(np.sin(Theta)/n) - 2*Theta
        SpecialTheta1 = np.arcsin(np.sqrt((9-n**2)/8))
        SpecialTheta2 = np.arcsin(np.sqrt((4-n**2)/3))
        SpecialEpsilon1 = pi - 6*np.arcsin(np.sin(SpecialTheta1)/n) + 2*SpecialTheta1
        SpecialEpsilon2 = 4*np.arcsin(np.sin(SpecialTheta2)/n) - 2*SpecialTheta2
        return {"Epsilon1": np.rad2deg(Epsilon1),
                "Epsilon2": np.rad2deg(Epsilon2),
                "SpecialEpsilon1": np.rad2deg(SpecialEpsilon1),
                "SpecialEpsilon2": np.rad2deg(SpecialEpsilon2),
                "color": color_name,
                "frequency": f"{frequency} THz"}
    freqs = [442.5,495,520,565,610,650,735]
    colors_map = {"Red": "red", "Orange": "orange", "Yellow": "yellow", "Green": "green", "Cyan": "cyan", "Blue": "blue", "Violet": "purple"}
    data = {name: convert(freq, colors_map[name]) for name, freq in zip(colors_map.keys(), freqs)}
    plt.figure(figsize=(12,8))
    Theta_deg = np.rad2deg(Theta)
    for name, d in data.items():
        plt.plot(Theta_deg, d["Epsilon1"], color=d["color"], linewidth=1.5,
                 label=f"{name} {d['frequency']} (ε1)")
        plt.plot(Theta_deg, d["Epsilon2"], color=d["color"], linewidth=1.5,
                 label=f"{name} {d['frequency']} (ε2)")
        plt.axhline(y=d["SpecialEpsilon1"], color=d["color"], alpha=0.7)
        plt.axhline(y=d["SpecialEpsilon2"], color=d["color"], alpha=0.7)
    plt.xlabel("θ (degrees)")
    plt.ylabel("ε (degrees)")
    plt.title("Elevation of deflected beam")
    plt.grid(True, linestyle="--", alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def generate_task11b_plot():
    rainbow = [(1,0,0),(1,0.2,0),(1,0.5,0),(1,1,0),(0,1,0),(0,0,1),(0.29,0,0.51),(0.58,0,0.83)]
    colourmap = LinearSegmentedColormap.from_list("colours", rainbow)
    frequency = np.linspace(405,790,10000)
    RefractiveIndex = (1+((1/(1.731-0.261*((frequency/1000)**2)))**0.5))**0.5
    Theta1 = np.arcsin(np.sqrt((4-RefractiveIndex**2)/3))
    Theta2 = np.arcsin(np.sqrt((9-RefractiveIndex**2)/8))
    Epsilon1 = 4*np.arcsin(np.sin(Theta1)/RefractiveIndex)-2*Theta1
    Epsilon2 = pi-6*np.arcsin(np.sin(Theta2)/RefractiveIndex)+2*Theta2
    Epsilon1, Epsilon2 = np.rad2deg(Epsilon1), np.rad2deg(Epsilon2)
    points1 = np.array([frequency, Epsilon1]).T.reshape(-1,1,2)
    points2 = np.array([frequency, Epsilon2]).T.reshape(-1,1,2)
    lines1 = np.concatenate([points1[:-1], points1[1:]], axis=1)
    lines2 = np.concatenate([points2[:-1], points2[1:]], axis=1)
    ColourLines1 = LineCollection(lines1, cmap=colourmap, linewidth=2.5)
    ColourLines2 = LineCollection(lines2, cmap=colourmap, linewidth=2.5)
    ColourLines1.set_array(frequency)
    ColourLines2.set_array(frequency)
    fig, ax = plt.subplots()
    ax.add_collection(ColourLines1)
    ax.add_collection(ColourLines2)
    ax.set_xlim(405,790)
    ax.set_ylim(Epsilon1.min(), Epsilon2.max())
    plt.title("Elevation of single and double rainbows")
    plt.xlabel("Frequency (THz)")
    plt.ylabel("ε (deg)")
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_task11c_plot():
    frequency = np.linspace(405,790,80)
    RefractiveIndex = (1+((1/(1.731-0.261*((frequency/1000)**2)))**0.5))**0.5
    Theta1 = np.arcsin(np.sqrt((4-RefractiveIndex**2)/3))
    Theta2 = np.arcsin(np.sqrt((9-RefractiveIndex**2)/8))
    Theta3 = pi/2
    Phi1 = np.arcsin(np.sin(Theta1)/RefractiveIndex)
    Phi2 = np.arcsin(np.sin(Theta2)/RefractiveIndex)
    Phi3 = np.arcsin(np.sin(Theta3)/RefractiveIndex)
    Phi1, Phi2, Phi3 = np.rad2deg(Phi1), np.rad2deg(Phi2), np.rad2deg(Phi3)
    colors_list = []
    for f in frequency:
        if f < 475:
            colors_list.append("red")
        elif f < 510:
            colors_list.append("orange")
        elif f < 530:
            colors_list.append("yellow")
        elif f < 600:
            colors_list.append("green")
        elif f < 620:
            colors_list.append("cyan")
        elif f < 675:
            colors_list.append("blue")
        else:
            colors_list.append("purple")
    plt.figure()
    plt.scatter(frequency, Phi1, c=colors_list, s=12)
    plt.plot(frequency, Phi1, color="blue")
    plt.scatter(frequency, Phi2, c=colors_list, s=12)
    plt.plot(frequency, Phi2, color="red")
    plt.plot(frequency, Phi3, color="black")
    plt.title("Refraction angle of single and double rainbows")
    plt.xlabel("Frequency (THz)")
    plt.ylabel("φ (deg)")
    plt.grid(True, alpha=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

########################################
# INTERACTIVE TASKS PLOT FUNCTIONS
########################################
def generate_task3_plot(v, n, y, l, request_id):
    try:
        l_scaled = 0.01 * l
        x = np.linspace(0, l_scaled, 10000)
        check_interrupt("3", request_id)
        t = np.sqrt(x**2 + y**2)/(v/n) + np.sqrt((l_scaled - x)**2 + y**2)/(v/n)
        idx = np.argmin(t)
        plt.figure()
        plt.scatter(x[idx], t[idx], color="red", zorder=2)
        plt.plot(x, t, zorder=1)
        plt.title(f"Minimum at x={round(x[idx],5)}; l/2 = {round(l_scaled/2,5)}")
        plt.xlabel("x (m)")
        plt.ylabel("t (s)")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 3 aborted: " + str(e))
        return generate_blank_image()

def generate_task4_plot(v, n1, n2, y, l, request_id):
    try:
        l_scaled = 0.01 * l
        x = np.linspace(0, l_scaled, 10000)
        check_interrupt("4", request_id)
        t = np.sqrt(x**2 + y**2)/(v/n1) + np.sqrt((l_scaled - x)**2 + y**2)/(v/n2)
        idx = np.argmin(t)
        theta1 = np.arctan(x[idx] / y)
        theta2 = np.arctan((l_scaled - x[idx]) / y)
        plt.figure()
        plt.scatter(x[idx], t[idx], color="red", zorder=2)
        plt.plot(x, t, zorder=1)
        plt.title(f"sin(θ1)/(v/n1): {round(np.sin(theta1)/(v/n1),15)}; sin(θ2)/(v/n2): {round(np.sin(theta2)/(v/n2),15)}")
        plt.xlabel("x (m)")
        plt.ylabel("t (s)")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 4 aborted: " + str(e))
        return generate_blank_image()

def generate_task5_plot(offset_x, offset_y, canvas_size, request_id):
    try:
        # Use the provided canvas size.
        S = canvas_size
        # Flip y-direction: increasing offset_y moves image upward.
        center_x = S // 2
        center_y = S // 2 - offset_y
        for y in range(H):
            if y % 10 == 0:
                check_interrupt("5", request_id)
            for x in range(W):
                colour = global_image[y, x]
                old_x = center_x + S//4 + x + offset_x
                old_y = center_y - H//2 + y
                new_x = center_x - S//4 - x - offset_x
                new_y = center_y - H//2 + y
                if 0 <= old_x < S and 0 <= old_y < S:
                    # Update canvas pixel
                    pass
                # Set pixels if within bounds
                if 0 <= old_x < S and 0 <= old_y < S:
                    pass
        # Reconstruct canvas with two copies:
        canvas = np.full((S, S, global_image.shape[2]), 255, dtype=np.uint8)
        for y in range(H):
            if y % 10 == 0:
                check_interrupt("5", request_id)
            for x in range(W):
                colour = global_image[y, x]
                old_x = center_x + S//4 + x + offset_x
                old_y = center_y - H//2 + y
                new_x = center_x - S//4 - x - offset_x
                new_y = center_y - H//2 + y
                if 0 <= old_x < S and 0 <= old_y < S:
                    canvas[old_y, old_x] = colour
                if 0 <= new_x < S and 0 <= new_y < S:
                    canvas[new_y, new_x] = colour
        plt.figure(figsize=(6,6))
        plt.imshow(canvas, extent=[-2,2,-2,2])
        plt.axvline(x=0, color="black", linestyle="--")
        plt.title(f"Offset X: {offset_x}, Offset Y: {offset_y}; Canvas Size: {S} px")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 5 aborted: " + str(e))
        return generate_blank_image()

def generate_task6_plot(start_x, start_y, scale, f_val, request_id):
    try:
        t0 = perf_counter()
        fudge_y = img_height // 2
        start_y_adj = (start_y + fudge_y) * -1
        size = max(img_height, img_width) * scale
        canvas_height = size
        canvas_width = int(size * 1.5)
        canvas = np.full((canvas_height, canvas_width, channels), 255, dtype=np.uint8)
        yy, xx = np.indices((img_height, img_width))
        old_x = xx + start_x
        old_y = yy + start_y_adj
        new_x_float = - (f_val * old_x)/(old_x - f_val)
        new_x = new_x_float.astype(int)
        new_y_float = (old_y/old_x) * new_x_float
        new_y = new_y_float.astype(int)
        old_y_index = (canvas_height//2) + old_y
        old_x_index = (canvas_width//2) + old_x
        new_y_index = (canvas_height//2) + new_y
        new_x_index = (canvas_width//2) + new_x
        valid_old = (old_y_index >= 0) & (old_y_index < canvas_height) & (old_x_index >= 0) & (old_x_index < canvas_width)
        valid_new = (new_y_index >= 0) & (new_y_index < canvas_height) & (new_x_index >= 0) & (new_x_index < canvas_width)
        canvas[old_y_index[valid_old], old_x_index[valid_old]] = global_image[yy[valid_old], xx[valid_old]]
        canvas[new_y_index[valid_new], new_x_index[valid_new]] = global_image[yy[valid_new], xx[valid_new]]
        def fix_row(row, left, right):
            cols = np.arange(left, right+1)
            row_slice = canvas[row, left:right+1]
            mask = (row_slice != 255).any(axis=1)
            if mask.sum() < 2: return
            filled_cols = cols[mask]
            interp_cols = np.arange(filled_cols[0], filled_cols[-1]+1)
            for ch in range(channels):
                xp = filled_cols
                fp = row_slice[mask, ch]
                interpolated = np.interp(interp_cols, xp, fp)
                canvas[row, interp_cols, ch] = np.around(interpolated).astype(np.uint8)
        def fix_col(col, top, bottom):
            rows = np.arange(top, bottom+1)
            col_slice = canvas[top:bottom+1, col]
            mask = (col_slice != 255).any(axis=1)
            if mask.sum() < 2: return
            filled_rows = rows[mask]
            interp_rows = np.arange(filled_rows[0], filled_rows[-1]+1)
            for ch in range(channels):
                xp = filled_rows
                fp = col_slice[mask, ch]
                interpolated = np.interp(interp_rows, xp, fp)
                canvas[interp_rows, col, ch] = np.around(interpolated).astype(np.uint8)
        all_new_x = new_x_index[valid_new].ravel()
        all_new_y = new_y_index[valid_new].ravel()
        raw_min_x = int(all_new_x.min())
        raw_max_x = int(all_new_x.max())
        raw_min_y = int(all_new_y.min())
        raw_max_y = int(all_new_y.max())
        minimum_x = max(raw_min_x, 0)
        maximum_x = min(raw_max_x, canvas_width-1)
        minimum_y = max(raw_min_y, 0)
        maximum_y = min(raw_max_y, canvas_height-1)
        for col in range(minimum_x, maximum_x+1):
            if (col - minimum_x) % 10 == 0:
                check_interrupt("6", request_id)
            fix_col(col, minimum_y, maximum_y)
        for row in range(minimum_y, maximum_y+1):
            if (row - minimum_y) % 10 == 0:
                check_interrupt("6", request_id)
            fix_row(row, minimum_x, maximum_x)
        t_elapsed = perf_counter() - t0
        print("Task 6 processing time: {:.4f}s".format(t_elapsed))
        fig, ax = plt.subplots(figsize=(8,6))
        extent_val = [-canvas_width//2, canvas_width//2, -canvas_height//2, canvas_height//2]
        ax.imshow(canvas, extent=extent_val)
        ax.set_xlim(extent_val[0], extent_val[1])
        ax.set_ylim(extent_val[2], extent_val[3])
        ax.axvline(x=0, color="black", linestyle="--")
        ax.scatter(f_val, 0, color="red", marker="*")
        ax.scatter(-f_val, 0, color="red", marker="*")
        ax.set_title(f"Task 6: start_x={start_x}, start_y_adj={start_y_adj}")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 6 aborted: " + str(e))
        return generate_blank_image()

def generate_task8_plot(start_x, start_y, rad_multiplier, request_id):
    try:
        size = max(global_image.shape[0], global_image.shape[1]) * 2
        canvas = np.full((size, int(size*1.5), global_image.shape[2]), 255, dtype=np.uint8)
        rad = int(rad_multiplier * global_image.shape[0])
        for y in range(global_image.shape[0]):
            check_interrupt("8", request_id)
            for x in range(global_image.shape[1]):
                colour = global_image[y, x]
                old_x = x + start_x
                old_y = y + start_y
                denominator = rad**2 - old_x**2
                if denominator <= 0: continue
                theta = np.arctan(old_y/np.sqrt(denominator))
                m = np.tan(2*theta)
                numerator_part = np.sqrt(max(0, rad**2 - old_y**2))
                if numerator_part <= 0: continue
                numerator2 = -(m*numerator_part - old_y)
                denominator2 = (old_y/old_x) + m
                if denominator2 == 0:
                    new_x = old_x * (-2*rad+denominator)/(2*old_x+denominator)
                else:
                    new_x = int(numerator2/denominator2)
                new_y = int(new_x * old_y/old_x)
                try:
                    canvas[(size//2)+old_y, (3*size//4)+old_x] = colour
                except:
                    pass
                for dy in range(-1,2):
                    for dx in range(-1,2):
                        try:
                            canvas[(size//2)+new_y+dy, (3*size//4)+new_x+dx] = colour
                        except:
                            continue
        def generate_semicircle_8(center_x, center_y, radius, stepsize=0.1):
            x_val = np.arange(center_x, center_x+radius+stepsize, stepsize)
            y_val = np.sqrt(radius**2 - x_val**2)
            x_val = np.concatenate([x_val, x_val[::-1]])
            y_val = np.concatenate([y_val, -y_val[::-1]])
            return -x_val, y_val + center_y
        semic_x, semic_y = generate_semicircle_8(0, 0, rad)
        plt.figure()
        plt.imshow(canvas, extent=[-size*1.5, size*1.5, -size, size])
        plt.xlim(-size*1.5, size*1.5)
        plt.ylim(-size, size)
        plt.plot(semic_x, semic_y, color="black")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 8 aborted: " + str(e))
        return generate_blank_image()

def generate_task9_plot(start_x, start_y, rad_multiplier, request_id):
    try:
        size = max(global_image.shape[0], global_image.shape[1]) * 2
        canvas = np.full((size, int(size*1.5), global_image.shape[2]), 255, dtype=np.uint8)
        rad = int(rad_multiplier * global_image.shape[0])
        for y in range(global_image.shape[0]):
            check_interrupt("9", request_id)
            for x in range(global_image.shape[1]):
                colour = global_image[y, x]
                old_x = x + start_x
                old_y = y + start_y
                try:
                    alpha = 0.5*np.arctan(old_y/old_x)
                    k = old_x/np.cos(2*alpha)
                    new_y = int(k*np.sin(alpha)/((k/rad) - np.cos(alpha) + (old_x*np.sin(alpha)/old_y)))
                    new_x = int(old_x*new_y/old_y)
                except:
                    new_y = 0
                    new_x = int(-rad*old_x/(rad-2*old_x))
                try:
                    canvas[(size//2)+old_y, old_x] = colour
                except:
                    pass
                for dy in range(-1,2):
                    for dx in range(-1,2):
                        try:
                            canvas[(size//2)+new_y+dy, new_x+dx] = colour
                        except:
                            continue
        def generate_semicircle_9(center_x, center_y, radius, stepsize=0.1):
            x_val = np.arange(center_x, center_x+radius+stepsize, stepsize)
            y_val = np.sqrt(radius**2 - x_val**2)
            x_val = np.concatenate([x_val, x_val[::-1]])
            y_val = np.concatenate([y_val, -y_val[::-1]])
            return x_val, y_val + center_y
        semic_x, semic_y = generate_semicircle_9(0, 0, rad)
        plt.figure()
        plt.imshow(canvas, extent=[0, size*3, -size, size])
        plt.xlim(0, size*3)
        plt.ylim(-size, size)
        plt.plot(semic_x, semic_y, color="black")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 9 aborted: " + str(e))
        return generate_blank_image()

def generate_task10_plot(Rf, arc_angle, request_id):
    try:
        plt.close('all')
        # Compute the radius that inscribes the image.
        inscribed_radius = isqrt(int((img_width/2)**2+(img_height/2)**2))
        # Use center = (0,0) always.
        arc_center_x = 0
        arc_center_y = 0
        # Use the slider value Rf as the anamorphic projection factor.
        canvas_size = int(inscribed_radius * (2*Rf + 2))
        fig, ax = plt.subplots(figsize=(8,8))
        canvas = np.full((canvas_size, canvas_size, global_image.shape[2]), 255, dtype=np.uint8)
        ax.imshow(canvas, extent=[-canvas_size/2, canvas_size/2, -canvas_size/2, canvas_size/2])
        # Also display the image (centered) using its inscribed dimensions.
        ax.imshow(global_image, extent=[-img_width/2, img_width/2, -img_height/2, img_height/2])
        # Draw the inscribing circle.
        circle = plt.Circle((0, 0), inscribed_radius, color="gray", fill=False, linewidth=1)
        ax.add_artist(circle)
        # For each row in the image, generate an arc.
        arc_angle_rad = np.deg2rad(arc_angle)
        start_angle = pi*1.5 - arc_angle_rad/2
        end_angle   = pi*1.5 + arc_angle_rad/2
        R_f_slider = Rf  # anamorphic projection factor from slider.
        for row in range(img_height):
            if row % 5 == 0:
                check_interrupt("10", request_id)
            R_here = R_f_slider * ((img_height - row - 1)/img_height) + 1
            theta = np.linspace(start_angle, end_angle, 300)
            x_center = 0
            y_center = img_height//2
            arc_x = x_center + inscribed_radius * R_here * np.cos(theta)
            arc_y = y_center + inscribed_radius * R_here * np.sin(theta)
            points = np.array([arc_x, arc_y]).T.reshape(-1,1,2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            # For simplicity, use a single color for arcs.
            lc = LineCollection(segments, colors="black", linewidth=3)
            ax.add_collection(lc)
        ax.set_xlim(-canvas_size/2, canvas_size/2)
        ax.set_ylim(-canvas_size/2, canvas_size/2)
        ax.set_title(f"Task 10: Anamorphic Projection (R_f={Rf}, Arc Angle={arc_angle}°)")
        ax.axis("on")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 10 aborted: " + str(e))
        return generate_blank_image()

def generate_task11d_plot(alpha, request_id):
    try:
        r = 1
        alpha_rad = np.deg2rad(alpha)
        def convert(frequency, color_name, alpha_rad):
            n = (1+((1/(1.731-0.261*((frequency/1000)**2)))**0.5))**0.5
            Theta1 = np.arcsin(np.sqrt((9-n**2)/8))
            Theta2 = np.arcsin(np.sqrt((4-n**2)/3))
            Epsilon1 = pi - 6*np.arcsin(np.sin(Theta1)/n) + 2*Theta1
            Epsilon2 = 4*np.arcsin(np.sin(Theta2)/n) - 2*Theta2
            Radius1 = r * np.sin(Epsilon1) * np.cos(alpha_rad)
            Radius2 = r * np.sin(Epsilon2) * np.cos(alpha_rad)
            Center1 = Radius1 - r * np.sin(Epsilon1 - alpha_rad)
            Center2 = Radius2 - r * np.sin(Epsilon2 - alpha_rad)
            return {"Center1": Center1,
                    "Center2": Center2,
                    "Radius1": Radius1,
                    "Radius2": Radius2,
                    "color": color_name,
                    "frequency": f"{frequency} THz"}
        freqs = [442.5,495,520,565,610,650,735]
        colors_dict = {"Red": "red", "Orange": "orange", "Yellow": "yellow", "Green": "green", "Cyan": "cyan", "Blue": "blue", "Violet": "purple"}
        data = {}
        for freq, name in zip(freqs, colors_dict.keys()):
            data[name] = convert(freq, colors_dict[name], alpha_rad)
            check_interrupt("11d", request_id)
        fig, ax = plt.subplots()
        max_radius = max(max(d["Radius1"], d["Radius2"]) for d in data.values())
        plot_limit = max_radius * 1.1
        for name, d in data.items():
            Circle1 = plt.Circle((0, -d["Center1"]), d["Radius1"], color=d["color"], linewidth=1.5, fill=False)
            Circle2 = plt.Circle((0, -d["Center2"]), d["Radius2"], color=d["color"], linewidth=1.5, fill=False)
            ax.add_artist(Circle1)
            ax.add_artist(Circle2)
        ax.set_aspect("equal")
        plt.xlim(-plot_limit, plot_limit)
        plt.ylim(0, plot_limit)
        plt.title("Task 11d: Rainbow Elevation Angles")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 11d aborted: " + str(e))
        return generate_blank_image()

########################################
# STATIC TASKS MAPPING
########################################
static_tasks = {
    "1a": generate_task1a_plot,
    "1b": generate_task1b_plot,
    "2": generate_task2_plot,
    "11a": generate_task11a_plot,
    "11b": generate_task11b_plot,
    "11c": generate_task11c_plot
}

########################################
# IMAGE UPLOAD ROUTE
########################################
@app.route('/upload', methods=["POST"])
def upload():
    global global_image, img_height, img_width, channels, H, W
    if "image_file" not in request.files:
        return redirect(url_for("index"))
    file = request.files["image_file"]
    if file.filename == "":
        return redirect(url_for("index"))
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Read the image
    img = plt.imread(filepath)
    h, w = img.shape[0], img.shape[1]
    
    if h > MAX_DIMENSION or w > MAX_DIMENSION:
        # Simple downscale: factor
        factor = max(h, w) / MAX_DIMENSION
        new_h, new_w = int(h / factor), int(w / factor)
        
        # Resize the image with anti-aliasing
        from skimage.transform import resize
        img = resize(img, (new_h, new_w), anti_aliasing=True)
        
        # Convert to uint8 format based on value range
        if img.min() >= 0 and img.max() <= 1:  # Float range [0, 1]
            img = (img * 255).clip(0, 255).astype(np.uint8)
        else:  # Assume uint8 or other range
            img = img.clip(0, 255).astype(np.uint8)
        
        print(img)
    
    global_image = img
    img_height, img_width, channels = global_image.shape
    H, W = img_height, img_width
    
    return redirect(url_for("index"))

########################################
# ROUTE: Handle Plot (Interactive/Static)
########################################
@app.route('/plot/<task_id>')
def plot_task(task_id):
    if task_id in interactive_tasks:
        req_id = str(uuid.uuid4())
        active_requests[task_id] = req_id
        try:
            if task_id == "3":
                v = float(request.args.get("v", 300000000))
                n = float(request.args.get("n", 1))
                y_val = float(request.args.get("y", 1))
                l = float(request.args.get("l", 100))
                buf = generate_task3_plot(v, n, y_val, l, req_id)
            elif task_id == "4":
                v = float(request.args.get("v", 300000000))
                n1 = float(request.args.get("n1", 1))
                n2 = float(request.args.get("n2", 1))
                y_val = float(request.args.get("y", 1))
                l = float(request.args.get("l", 100))
                buf = generate_task4_plot(v, n1, n2, y_val, l, req_id)
            elif task_id == "5":
                offset_x = int(request.args.get("offset_x", 0))
                offset_y = int(request.args.get("offset_y", 0))
                canvas_size = int(request.args.get("canvas_size", int(4*max(W,H))))
                buf = generate_task5_plot(offset_x, offset_y, canvas_size, req_id)
            elif task_id == "6":
                start_x = int(request.args.get("start_x", 60))
                start_y = int(request.args.get("start_y", 0))
                scale = int(request.args.get("scale", 7))
                f_val = int(request.args.get("f_val", 150))
                buf = generate_task6_plot(start_x, start_y, scale, f_val, req_id)
            elif task_id == "8":
                start_x = int(request.args.get("start_x", int(0.8*img_width)))
                start_y = int(request.args.get("start_y", -img_height))
                rad_multiplier = float(request.args.get("rad_multiplier", 2))
                buf = generate_task8_plot(start_x, start_y, rad_multiplier, req_id)
            elif task_id == "9":
                start_x = int(request.args.get("start_x", int(img_width)))
                start_y = int(request.args.get("start_y", int(-0.5*img_height)))
                rad_multiplier = float(request.args.get("rad_multiplier", 3.5))
                buf = generate_task9_plot(start_x, start_y, rad_multiplier, req_id)
            elif task_id == "10":
                Rf = float(request.args.get("Rf", 3))
                arc_angle = float(request.args.get("arc_angle", 160))
                buf = generate_task10_plot(Rf, arc_angle, req_id)
            elif task_id == "11d":
                alpha = float(request.args.get("alpha", 0))
                buf = generate_task11d_plot(alpha, req_id)
            else:
                return "Interactive task not implemented", 404
            return send_file(buf, mimetype="image/png")
        except Exception as e:
            logging.error(f"Error in interactive task {task_id}: {e}")
            return send_file(generate_blank_image(), mimetype="image/png")
    elif task_id in static_tasks:
        buf = static_tasks[task_id]()
        return send_file(buf, mimetype="image/png")
    else:
        return f"Task {task_id} not defined", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
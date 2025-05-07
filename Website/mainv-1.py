# main.py
import os
import io
import uuid
import logging
from math import isqrt
from time import perf_counter, time

from flask import Flask, render_template_string, url_for, send_file, request, redirect
import matplotlib.pyplot as plt
import numpy as np

# Additional matplotlib imports for Task 1b and 11b
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

############################
# Global Interrupt Manager
############################
# For interactive tasks, we store the most recent request id
active_requests = {}  # e.g. {"3": request_id, "6": request_id, ...}

def check_interrupt(task_key, request_id):
    """
    Called periodically to check if the current computation should abort
    because a newer request id has been registered.
    """
    if active_requests.get(task_key) != request_id:
        raise Exception("Aborted: a newer slider update was received.")

############################
# Global Image Loading
############################
# We'll use one global image for many tasks.
# (For tasks that need to choose among different images, you could extend this logic.)
image_file = "Tall1.jpg"  # Default image file
if os.path.exists(image_file):
    global_image = plt.imread(image_file)
    img_height, img_width, channels = global_image.shape
else:
    logging.error("Global image file Tall1.jpg not found!")
    global_image = None
    img_height = img_width = channels = 0

# For Task 5, 8, 9, 10 etc. we use the same global_image.
H, W = img_height, img_width

############################
# Generic Blank Image (for aborted computations)
############################
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

############################
# GENERIC INTERACTIVE PAGE TEMPLATE
############################
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
      document.getElementById("spinner").style.display = "block";
      document.getElementById("plotImage").src = "{{ plot_endpoint }}?" + query.toString();
    }
    
    // (Optionally add banned-range logic here if needed for some tasks)
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
    
    {% for slider in sliders %}
      {% if banned_validation %}
        document.getElementById("{{ slider.id }}").addEventListener("input", sliderChanged);
      {% else %}
        document.getElementById("{{ slider.id }}").addEventListener("input", updatePlot);
      {% endif %}
    {% endfor %}
    
    document.getElementById("plotImage").addEventListener("load", function() {
      document.getElementById("spinner").style.display = "none";
    });
  </script>
</body>
</html>
'''

def render_interactive_page(slider_config, title, plot_endpoint, banned_validation=False, extra_context=None):
    """Renders an interactive page using the generic template."""
    if extra_context is None:
        extra_context = {}
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

############################
# Interactive Tasks Configuration
############################
# Each interactive task here is keyed by a string id.
# You can modify the slider ranges and default values as needed.

interactive_tasks = {
    "3": {
        "title": "Task 3 Interactive: Optimize Travel Time",
        "sliders": [
            {"id": "v", "label": "Speed (m/s)", "min": 3e8, "max": 3e8*10, "value": 3e8, "step": 1e7},
            {"id": "n", "label": "Refractive Index", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "y", "label": "Height", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "l", "label": "Length (cm)", "min": 10, "max": 300, "value": 100, "step": 10}
        ],
        "plot_endpoint": "/plot/3",
        "banned_validation": False
    },
    "4": {
        "title": "Task 4 Interactive: Dual Speed Optimization",
        "sliders": [
            {"id": "v", "label": "Speed (m/s)", "min": 3e8, "max": 3e8*10, "value": 3e8, "step": 1e7},
            {"id": "n1", "label": "Refractive Index 1", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "n2", "label": "Refractive Index 2", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "y", "label": "Height", "min": 1, "max": 10, "value": 1, "step": 1},
            {"id": "l", "label": "Length (cm)", "min": 10, "max": 300, "value": 100, "step": 10}
        ],
        "plot_endpoint": "/plot/4",
        "banned_validation": False
    },
    "5": {
        "title": "Task 5 Interactive: Dual Image Placement",
        "sliders": [
            {"id": "offset_x", "label": "Object X (px)", "min": -max(W, H), "max": max(W, H), "value": 0, "step": 1},
            {"id": "offset_y", "label": "Object Y (px)", "min": -max(W, H), "max": max(W, H), "value": 0, "step": 1}
        ],
        "plot_endpoint": "/plot/5",
        "banned_validation": False
    },
    "6": {
        "title": "Task 6 Interactive: Image Projection",
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
        "title": "Task 8 Interactive: Image Transformation (Arc Overlay)",
        "sliders": [
            {"id": "start_x", "label": "Start X", "min": int(0.5*img_width), "max": int(img_width), "value": int(0.8*img_width), "step": 1},
            {"id": "start_y", "label": "Start Y", "min": -img_height, "max": 0, "value": -img_height, "step": 1},
            {"id": "rad_multiplier", "label": "Radial Multiplier", "min": 1, "max": 3, "value": 2, "step": 0.1}
        ],
        "plot_endpoint": "/plot/8",
        "banned_validation": False
    },
    "9": {
        "title": "Task 9 Interactive: Alternative Image Transformation",
        "sliders": [
            {"id": "start_x", "label": "Start X", "min": int(0.5*img_width), "max": int(img_width), "value": int(img_width), "step": 1},
            {"id": "start_y", "label": "Start Y", "min": -img_height, "max": 0, "value": int(-0.5*img_height), "step": 1},
            {"id": "rad_multiplier", "label": "Radial Multiplier", "min": 1, "max": 4, "value": 3.5, "step": 0.1}
        ],
        "plot_endpoint": "/plot/9",
        "banned_validation": False
    },
    "10": {
        "title": "Task 10 Interactive: Arc and Image Overlay",
        "sliders": [
            {"id": "arc_center_x", "label": "Center X", "min": -int(img_width/2), "max": int(img_width/2), "value": 0, "step": 1},
            {"id": "arc_center_y", "label": "Center Y", "min": -int(img_height/2), "max": int(img_height/2), "value": 0, "step": 1}
        ],
        "plot_endpoint": "/plot/10",
        "banned_validation": False
    },
    "11d": {
        "title": "Task 11d Interactive: Refraction Circles",
        "sliders": [
            {"id": "alpha", "label": "Alpha (degrees)", "min": 0, "max": 60, "value": 0, "step": 1}
        ],
        "plot_endpoint": "/plot/11d",
        "banned_validation": False
    }
}

############################
# Static Tasks Functions (Return plot images)
############################
def generate_task1a_plot():
    # Task 1a: Refractive index of crown glass vs wavelength
    def crown_glass(Lambda):
        x = Lambda / 1000
        a = np.array([1.03961212, 0.231792344, 1.01146945])
        b = np.array([0.00600069867, 0.0200179144, 103.560653])
        y = np.zeros(x.size)
        for i in range(len(a)):
            y += (a[i] * (x**2)) / ((x**2) - b[i])
        return np.sqrt(1 + y)
    Lambda = np.linspace(400, 800, 10000)
    RefractiveIndex = crown_glass(Lambda)
    plt.figure()
    plt.plot(Lambda, RefractiveIndex)
    plt.title("Refractive index of crown glass vs wavelength")
    plt.xlabel('$\\lambda$ (nm)')
    plt.ylabel('n')
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def generate_task1b_plot():
    # Task 1b: Refractive index of water vs frequency (with rainbow colors)
    rainbow = [(1,0,0),(1,0.3,0),(1,1,0),(0,1,0),(0,0,1),(0.29,0,0.51),(0.58,0,0.83)]
    colourmap = LinearSegmentedColormap.from_list('colours', rainbow)
    frequency = np.linspace(405, 790, 10000)
    RefractiveIndex = (1 + ((1 / (1.731 - 0.261*((frequency/1000)**2))) ** 0.5)) ** 0.5
    points = np.array([frequency, RefractiveIndex]).T.reshape(-1,1,2)
    lines = np.concatenate([points[:-1], points[1:]], axis=1)
    ColourLines = LineCollection(lines, cmap=colourmap, linewidth=2.5)
    ColourLines.set_array(frequency)
    fig, ax = plt.subplots()
    ax.add_collection(ColourLines)
    ax.set_xlim(405, 790)
    ax.set_ylim(1.33, RefractiveIndex.max())
    plt.title("Refractive index of water vs Frequency of light")
    plt.xlabel('Frequency (THz)')
    plt.ylabel('Refractive index')
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_task2_plot():
    # Task 2: Scatter and linear regression of 1/u vs 1/v
    u = np.linspace(20, 55, 8)
    v = np.array([65.5, 40, 31, 27, 25, 23.1, 21.5, 20.5])
    m, c = np.polyfit(1/u, 1/v, 1)
    plt.figure()
    plt.scatter(1/u, 1/v, color='red', zorder=2)
    plt.plot(1/u, m*(1/u)+c, zorder=1)
    plt.title(f"Gradient: {round(m,4)}; Y-intercept: {round(c,4)}")
    plt.xlabel('1/u (cm^-1)')
    plt.ylabel('1/v (cm^-1)')
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def generate_task11a_plot():
    # Task 11a: Multiple curves for ε vs θ with special markers
    Theta = np.linspace(0, np.pi/2, 10000)
    def convert(frequency, color_name):
        n = (1 + ((1/(1.731 - 0.261*((frequency/1000)**2)))**0.5))**0.5
        Epsilon1 = np.pi - 6*np.arcsin(np.sin(Theta)/n) + 2*Theta
        Epsilon2 = 4*np.arcsin(np.sin(Theta)/n) - 2*Theta
        SpecialTheta1 = np.arcsin(np.sqrt((9-n**2)/8))
        SpecialTheta2 = np.arcsin(np.sqrt((4-n**2)/3))
        SpecialEpsilon1 = np.pi - 6*np.arcsin(np.sin(SpecialTheta1)/n) + 2*SpecialTheta1
        SpecialEpsilon2 = 4*np.arcsin(np.sin(SpecialTheta2)/n) - 2*SpecialTheta2
        return {
            'Epsilon1': np.rad2deg(Epsilon1),
            'Epsilon2': np.rad2deg(Epsilon2),
            'SpecialEpsilon1': np.rad2deg(SpecialEpsilon1),
            'SpecialEpsilon2': np.rad2deg(SpecialEpsilon2),
            'color': color_name,
            'frequency': f"{frequency} THz"
        }
    freqs = np.array([442.5, 495, 520, 565, 610, 650, 735])
    colors_map = {'Red': 'red', 'Orange': 'orange', 'Yellow': 'yellow',
                  'Green': 'green', 'Cyan': 'cyan', 'Blue': 'blue', 'Violet': 'purple'}
    data = {name: convert(freq, colors_map[name]) for name, freq in zip(colors_map.keys(), freqs)}
    plt.figure(figsize=(12,8))
    Theta_deg = np.rad2deg(Theta)
    for name, d in data.items():
        plt.plot(Theta_deg, d['Epsilon1'], color=d['color'], linewidth=1.5,
                 label=f"{name} {d['frequency']} (ε1)")
        plt.plot(Theta_deg, d['Epsilon2'], color=d['color'], linewidth=1.5,
                 label=f"{name} {d['frequency']} (ε2)")
        plt.axhline(y=d['SpecialEpsilon1'], color=d['color'], alpha=0.7)
        plt.axhline(y=d['SpecialEpsilon2'], color=d['color'], alpha=0.7)
    plt.xlabel('$\\theta$ (degrees)', fontsize=12)
    plt.ylabel('$\\epsilon$ (degrees)', fontsize=12)
    title_str = ("Elevation of deflected beam (deg).\nPrimary: ε = {:.1f} to {:.1f}\n"
                 "Secondary: ε = {:.1f} to {:.1f}").format(
                 data['Violet']['SpecialEpsilon2'], data['Red']['SpecialEpsilon2'],
                 data['Red']['SpecialEpsilon1'], data['Violet']['SpecialEpsilon1'])
    plt.title(title_str, fontsize=14, pad=20)
    plt.grid(True, which='both', linestyle='--', alpha=0.3)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

def generate_task11b_plot():
    # Task 11b: LineCollection of rainbow-coloured curves
    rainbow = [(1,0,0),(1,0.2,0),(1,0.5,0),(1,1,0),
               (0,1,0),(0,0,1),(0.29,0,0.51),(0.58,0,0.83)]
    colourmap = LinearSegmentedColormap.from_list('colours', rainbow)
    frequency = np.linspace(405, 790, 10000)
    RefractiveIndex = (1 + ((1/(1.731 - 0.261*((frequency/1000)**2)))**0.5))**0.5
    Theta1 = np.arcsin(np.sqrt((4-RefractiveIndex**2)/3))
    Theta2 = np.arcsin(np.sqrt((9-RefractiveIndex**2)/8))
    Epsilon1 = 4*np.arcsin(np.sin(Theta1)/RefractiveIndex) - 2*Theta1
    Epsilon2 = np.pi - 6*np.arcsin(np.sin(Theta2)/RefractiveIndex) + 2*Theta2
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
    ax.set_xlim(405, 790)
    ax.set_ylim(Epsilon1.min(), Epsilon2.max())
    plt.title("Elevation of single and double rainbows")
    plt.xlabel('Frequency (THz)')
    plt.ylabel('$\\epsilon$ (deg)')
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

def generate_task11c_plot():
    # Task 11c: Scatter and line plots for refraction angles (colored points)
    frequency = np.linspace(405, 790, 80)
    RefractiveIndex = (1 + ((1/(1.731 - 0.261*((frequency/1000)**2)))**0.5))**0.5
    Theta1 = np.arcsin(np.sqrt((4-RefractiveIndex**2)/3))
    Theta2 = np.arcsin(np.sqrt((9-RefractiveIndex**2)/8))
    Theta3 = np.pi/2
    Phi1 = np.arcsin(np.sin(Theta1)/RefractiveIndex)
    Phi2 = np.arcsin(np.sin(Theta2)/RefractiveIndex)
    Phi3 = np.arcsin(np.sin(Theta3)/RefractiveIndex)
    Phi1, Phi2, Phi3 = np.rad2deg(Phi1), np.rad2deg(Phi2), np.rad2deg(Phi3)
    colors_list = []
    for f in frequency:
        if f < 475:
            colors_list.append('red')
        elif f < 510:
            colors_list.append('orange')
        elif f < 530:
            colors_list.append('yellow')
        elif f < 600:
            colors_list.append('green')
        elif f < 620:
            colors_list.append('cyan')
        elif f < 675:
            colors_list.append('blue')
        else:
            colors_list.append('purple')
    plt.figure()
    plt.scatter(frequency, Phi1, c=colors_list, s=12)
    plt.plot(frequency, Phi1, color='blue')
    plt.scatter(frequency, Phi2, c=colors_list, s=12)
    plt.plot(frequency, Phi2, color='red')
    plt.plot(frequency, Phi3, color='black')
    plt.title("Refraction angle of single and double rainbows")
    plt.xlabel('Frequency (THz)')
    plt.ylabel('$\\phi$ (deg)')
    plt.grid(True, alpha=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

############################
# Interactive Tasks Plot Generation Functions
############################
def generate_task3_plot(v, n, y, l, request_id):
    # Task 3: Compute travel time and plot as function of x.
    try:
        l_scaled = 0.01 * l
        x = np.linspace(0, l_scaled, 10000)
        check_interrupt("3", request_id)
        t = np.sqrt(x**2 + y**2) / (v/n) + np.sqrt((l_scaled - x)**2 + y**2) / (v/n)
        idx = np.argmin(t)
        plt.figure()
        plt.scatter(x[idx], t[idx], color='red', zorder=2)
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
        logging.info("Task 3 aborted: "+str(e))
        return generate_blank_image()

def generate_task4_plot(v, n1, n2, y, l, request_id):
    # Task 4: Compute travel time with two refractive indexes.
    try:
        l_scaled = 0.01 * l
        x = np.linspace(0, l_scaled, 10000)
        check_interrupt("4", request_id)
        t = np.sqrt(x**2+y**2)/(v/n1) + np.sqrt((l_scaled-x)**2+y**2)/(v/n2)
        idx = np.argmin(t)
        theta1 = np.arctan(x[idx] / y)
        theta2 = np.arctan((l_scaled-x[idx]) / y)
        plt.figure()
        plt.scatter(x[idx], t[idx], color='red', zorder=2)
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
        logging.info("Task 4 aborted: "+str(e))
        return generate_blank_image()

def generate_task5_plot(offset_x, offset_y, request_id):
    # Task 5: Draw two copies of the image on a square canvas.
    try:
        S = int(4 * max(W, H))
        canvas = np.full((S, S, global_image.shape[2]), 255, dtype=np.uint8)
        center_x = S // 2
        center_y = S // 2 + offset_y
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
        plt.axvline(x=0, color='black', linestyle='--')
        plt.title(f"Offset X: {offset_x}, Offset Y: {offset_y}; Canvas Size: {S} px")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 5 aborted: "+str(e))
        return generate_blank_image()

def generate_task6_plot(start_x, start_y, scale, f_val, request_id):
    # Task 6: Image projection with a focal length parameter.
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
        canvas[old_y_index[valid_old], old_x_index[valid_old]] = global_image[yy[valid_old], xx[valid_old]]
        canvas[new_y_index[valid_new], new_x_index[valid_new]] = global_image[yy[valid_new], xx[valid_new]]
        # Interpolate along rows and columns (with periodic checking)
        def fix_row(row, left, right):
            cols = np.arange(left, right+1)
            row_slice = canvas[row, left:right+1]
            mask = (row_slice != 255).any(axis=1)
            if mask.sum() < 2:
                return
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
            if mask.sum() < 2:
                return
            filled_rows = rows[mask]
            interp_rows = np.arange(filled_rows[0], filled_rows[-1]+1)
            for ch in range(channels):
                xp = filled_rows
                fp = col_slice[mask, ch]
                interpolated = np.interp(interp_rows, xp, fp)
                canvas[interp_rows, col, ch] = np.around(interpolated).astype(np.uint8)
        # Interpolate with checks every 10 iterations
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
        print("Task 6 processing time: {:.4f} seconds".format(t_elapsed))
        fig, ax = plt.subplots(figsize=(8,6))
        extent_val = [-canvas_width//2, canvas_width//2, -canvas_height//2, canvas_height//2]
        ax.imshow(canvas, extent=extent_val)
        ax.set_xlim(extent_val[0], extent_val[1])
        ax.set_ylim(extent_val[2], extent_val[3])
        ax.axvline(x=0, color='black', linestyle='--')
        ax.scatter(f_val, 0, color='red', marker='*')
        ax.scatter(-f_val, 0, color='red', marker='*')
        ax.set_title(f"Task 6: start_x={start_x}, start_y(adj)={start_y_adj}")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 6 aborted: "+str(e))
        return generate_blank_image()

def generate_task8_plot(start_x, start_y, rad_multiplier, request_id):
    # Task 8: Image transformation with arc overlay.
    try:
        size = max(global_image.shape[0], global_image.shape[1]) * 2
        canvas = np.full((size, int(size*1.5), global_image.shape[2]), 255, dtype=np.uint8)
        rad = int(rad_multiplier * global_image.shape[0])
        # Use the provided start values.
        for y in range(global_image.shape[0]):
            check_interrupt("8", request_id)
            for x in range(global_image.shape[1]):
                colour = global_image[y, x]
                old_x = x + start_x
                old_y = y + start_y
                denominator = rad**2 - old_x**2
                if denominator <= 0:
                    continue
                theta = np.arctan(old_y / np.sqrt(denominator))
                m = np.tan(2*theta)
                numerator_part = np.sqrt(max(0, rad**2 - old_y**2))
                if numerator_part <= 0:
                    continue
                numerator2 = -(m * numerator_part - old_y)
                denominator2 = (old_y/old_x) + m
                if denominator2 == 0:
                    new_x = old_x * (-2*rad+denominator)/(2*old_x+denominator)
                else:
                    new_x = int(numerator2/denominator2)
                new_y = int(new_x * old_y / old_x)
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
        # Draw semicircle (using Task 8 style: reversed x)
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
        plt.plot(semic_x, semic_y, color='black')
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 8 aborted: " + str(e))
        return generate_blank_image()

def generate_task9_plot(start_x, start_y, rad_multiplier, request_id):
    # Task 9: Alternative image transformation.
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
                    alpha = 0.5 * np.arctan(old_y/old_x)
                    k = old_x / np.cos(2*alpha)
                    new_y = int(k * np.sin(alpha) / ((k/rad) - np.cos(alpha) + (old_x*np.sin(alpha)/old_y)))
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
        plt.plot(semic_x, semic_y, color='black')
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 9 aborted: " + str(e))
        return generate_blank_image()

def generate_task10_plot(arc_center_x, arc_center_y, request_id):
    # Task 10: Arc and image overlay.
    try:
        image_height_local = global_image.shape[0]
        image_width_local = global_image.shape[1]
        circle_radius = isqrt(int((image_width_local/2)**2 + (image_height_local/2)**2))
        R_f = 3
        canvas_size = circle_radius * (2*R_f+2)
        canvas = np.full((canvas_size, canvas_size, global_image.shape[2]), 255, dtype=np.uint8)
        fig, ax = plt.subplots(figsize=(8,8))
        ax.imshow(canvas, extent=[-canvas_size/2, canvas_size/2, -canvas_size/2, canvas_size/2])
        ax.imshow(global_image, extent=[-image_width_local/2, image_width_local/2, 0, image_height_local])
        def generate_circle(center_x, center_y, radius, num_points=2000):
            theta = np.linspace(0, 2*np.pi, num_points)
            return center_x + radius*np.cos(theta), center_y + radius*np.sin(theta)
        circle_x, circle_y = generate_circle(arc_center_x, (image_height_local/2)+arc_center_y, circle_radius)
        ax.plot(circle_x, circle_y, color='gray', lw=1, label="Circle")
        arc_angle = 160
        for row in range(image_height_local):
            if row % 10 == 0:
                check_interrupt("10", request_id)
            R_here = R_f * ((image_height_local - row - 1) / image_height_local) + 1
            # Generate arc for this row
            start_angle = np.deg2rad(270 - arc_angle/2)
            end_angle = np.deg2rad(270 + arc_angle/2)
            theta = np.linspace(start_angle, end_angle, 300)
            arc_x = arc_center_x + circle_radius * R_here * np.cos(theta)
            arc_y = arc_center_y + circle_radius * R_here * np.sin(theta)
            # Interpolate colors from the given row of the image
            col_indices = (theta - start_angle) * image_width_local / (end_angle - start_angle)
            row_data = global_image[int(row), :, :]
            num_channels = row_data.shape[1]
            arc_colors = np.empty((300, num_channels), dtype=row_data.dtype)
            cols = np.arange(image_width_local)
            for ch in range(num_channels):
                arc_colors[:, ch] = np.interp(col_indices, cols, row_data[:, ch])
            points = np.array([arc_x, arc_y]).T.reshape(-1,1,2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            lc = LineCollection(segments, colors=arc_colors[:-1]/255, linewidth=3)
            ax.add_collection(lc)
        ax.set_xlim(-canvas_size/2, canvas_size/2)
        ax.set_ylim(-canvas_size/2, canvas_size/2)
        ax.set_title(f"Task 10: Arc Center = ({arc_center_x}, {arc_center_y})")
        ax.axis('on')
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 10 aborted: " + str(e))
        return generate_blank_image()

def generate_task11d_plot(alpha, request_id):
    # Task 11d: Refraction circles with a slider controlling alpha.
    try:
        r = 1
        alpha_rad = np.deg2rad(alpha)
        def convert(frequency, color_name, alpha_rad):
            n = (1 + ((1/(1.731 - 0.261*((frequency/1000)**2)))**0.5))**0.5
            Theta1 = np.arcsin(np.sqrt((9-n**2)/8))
            Theta2 = np.arcsin(np.sqrt((4-n**2)/3))
            Epsilon1 = np.pi - 6*np.arcsin(np.sin(Theta1)/n) + 2*Theta1
            Epsilon2 = 4*np.arcsin(np.sin(Theta2)/n) - 2*Theta2
            Radius1 = r * np.sin(Epsilon1) * np.cos(alpha_rad)
            Radius2 = r * np.sin(Epsilon2) * np.cos(alpha_rad)
            Center1 = Radius1 - r * np.sin(Epsilon1 - alpha_rad)
            Center2 = Radius2 - r * np.sin(Epsilon2 - alpha_rad)
            return {'Center1': Center1,
                    'Center2': Center2,
                    'Radius1': Radius1,
                    'Radius2': Radius2,
                    'color': color_name,
                    'frequency': f"{frequency} THz"}
        freqs = [442.5, 495, 520, 565, 610, 650, 735]
        colors_dict = {'Red': 'red', 'Orange': 'orange', 'Yellow': 'yellow',
                       'Green': 'green', 'Cyan': 'cyan', 'Blue': 'blue', 'Violet': 'purple'}
        data = {}
        for freq, name in zip(freqs, colors_dict.keys()):
            data[name] = convert(freq, colors_dict[name], alpha_rad)
            check_interrupt("11d", request_id)
        fig, ax = plt.subplots()
        max_radius = max(max(d['Radius1'], d['Radius2']) for d in data.values())
        plot_limit = max_radius * 1.1
        for name, d in data.items():
            Circle1 = plt.Circle((0, -d['Center1']), d['Radius1'], color=d['color'], linewidth=1.5, fill=False)
            Circle2 = plt.Circle((0, -d['Center2']), d['Radius2'], color=d['color'], linewidth=1.5, fill=False)
            ax.add_artist(Circle1)
            ax.add_artist(Circle2)
        ax.set_aspect('equal')
        plt.xlim(-plot_limit, plot_limit)
        plt.ylim(0, plot_limit)
        plt.title("Task 11d: Refraction Circles")
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.info("Task 11d aborted: "+str(e))
        return generate_blank_image()

############################
# Static Tasks Mapping
############################
static_tasks = {
    "1a": generate_task1a_plot,
    "1b": generate_task1b_plot,
    "2": generate_task2_plot,
    "11a": generate_task11a_plot,
    "11b": generate_task11b_plot,
    "11c": generate_task11c_plot
}

############################
# Flask Routes
############################
# Homepage: Display grid of tasks.
# We list all tasks as links. Interactive tasks and static tasks are distinguished by their IDs.
# Task 7 is special (redirect to 6).
MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
  <title>Task Selector</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .grid-container {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      grid-gap: 15px;
    }
    .button {
      padding: 15px;
      text-align: center;
      background-color: #007BFF;
      color: white;
      text-decoration: none;
      border-radius: 8px;
      transition: background-color 0.3s;
    }
    .button:hover { background-color: #0056b3; }
  </style>
</head>
<body>
  <h1>Select a Task</h1>
  <div class="grid-container">
    {% for task in tasks %}
      <a class="button" href="{{ url_for('handle_task', task_id=task) }}">{{ task }}</a>
    {% endfor %}
  </div>
</body>
</html>
'''

@app.route('/')
def index():
    # List task IDs including interactive tasks (3,4,5,6,7,8,9,10,11d) and static tasks (1a, 1b, 2, 11a, 11b, 11c)
    tasks = ["1a", "1b", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11a", "11b", "11c", "11d"]
    return render_template_string(MAIN_TEMPLATE, tasks=tasks)

@app.route('/task/<task_id>')
def handle_task(task_id):
    # For Task 7, redirect to Task 6 with a short interim message.
    if task_id == "7":
        return redirect(url_for('handle_task', task_id="6"))
    if task_id in interactive_tasks:
        return redirect(url_for('interactive_task', task_id=task_id))
    elif task_id in static_tasks:
        # Render a simple page with the static plot image.
        page = '''
        <!DOCTYPE html>
        <html>
        <head>
          <title>Task {{ task_id }}</title>
          <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body>
          <h1>Task {{ task_id }}</h1>
          <img src="{{ url_for('plot_task', task_id=task_id) }}" style="max-width:800px;width:100%;">
          <br><br>
          <a href="{{ url_for('index') }}">Back to Home</a>
        </body>
        </html>
        '''
        return render_template_string(page, task_id=task_id)
    else:
        return f"Task {task_id} is not defined.", 404

@app.route('/interactive/<task_id>')
def interactive_task(task_id):
    if task_id in interactive_tasks:
        config = interactive_tasks[task_id]
        return render_interactive_page(slider_config=config["sliders"],
                                       title=config["title"],
                                       plot_endpoint=config["plot_endpoint"],
                                       banned_validation=config.get("banned_validation", False),
                                       extra_context=config.get("extra_context", {}))
    else:
        return f"No interactive configuration defined for task {task_id}", 404

@app.route('/plot/<task_id>')
def plot_task(task_id):
    # For interactive tasks, use the interactive generate functions with request id.
    if task_id in interactive_tasks:
        req_id = str(uuid.uuid4())
        active_requests[task_id] = req_id
        try:
            if task_id == "3":
                v = float(request.args.get("v", 3e8))
                n = float(request.args.get("n", 1))
                y_val = float(request.args.get("y", 1))
                l = float(request.args.get("l", 100))
                buf = generate_task3_plot(v, n, y_val, l, req_id)
            elif task_id == "4":
                v = float(request.args.get("v", 3e8))
                n1 = float(request.args.get("n1", 1))
                n2 = float(request.args.get("n2", 1))
                y_val = float(request.args.get("y", 1))
                l = float(request.args.get("l", 100))
                buf = generate_task4_plot(v, n1, n2, y_val, l, req_id)
            elif task_id == "5":
                offset_x = int(request.args.get("offset_x", 0))
                offset_y = int(request.args.get("offset_y", 0))
                buf = generate_task5_plot(offset_x, offset_y, req_id)
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
                arc_center_x = int(request.args.get("arc_center_x", 0))
                arc_center_y = int(request.args.get("arc_center_y", 0))
                buf = generate_task10_plot(arc_center_x, arc_center_y, req_id)
            elif task_id == "11d":
                alpha = float(request.args.get("alpha", 0))
                buf = generate_task11d_plot(alpha, req_id)
            else:
                return "Interactive task not implemented", 404
            return send_file(buf, mimetype="image/png")
        except Exception as e:
            logging.error(f"Error in interactive task {task_id}: {e}")
            return send_file(generate_blank_image(), mimetype="image/png")
    # For static tasks, use the corresponding static function.
    elif task_id in static_tasks:
        buf = static_tasks[task_id]()
        return send_file(buf, mimetype="image/png")
    else:
        return f"Task {task_id} not defined", 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(debug=True, host='0.0.0.0', port=port)
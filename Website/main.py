# main.py
import os
import io
import uuid
import logging
from math import isqrt, cos, sin, radians, pi, log10, acos, atan2, degrees, sqrt # Added sqrt
from time import perf_counter
from flask import Flask, request, redirect, url_for, render_template_string, send_file, jsonify
from werkzeug.utils import secure_filename
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Polygon, Circle # Added Circle
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from skimage.transform import resize
import matplotlib.image as mpimg


app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Configure upload folder and maximum dimensions for user uploaded images
UPLOAD_FOLDER = './uploads'
STATIC_FOLDER = './static'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True) # Ensure static folder exists
MAX_DIMENSION = 120  # maximum width or height (in pixels)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Ensure dummy logo and optics images exist in ./static for testing if not provided by user ---
DUMMY_LOGO_PATH = os.path.join(STATIC_FOLDER, 'bpho_logo.jpg')
DUMMY_OPTICS_IMAGE_PATH = os.path.join(STATIC_FOLDER, 'optics_image_1.jpg')

if not os.path.exists(DUMMY_LOGO_PATH):
    try:
        fig_logo = Figure(figsize=(3.96, 1.27))
        canvas_logo = FigureCanvas(fig_logo)
        ax_logo = fig_logo.add_subplot(111)
        ax_logo.text(0.5, 0.5, 'BPHO Logo', ha='center', va='center')
        ax_logo.axis('off')
        fig_logo.savefig(DUMMY_LOGO_PATH)
        logging.info(f"Created dummy logo at {DUMMY_LOGO_PATH}")
    except Exception as e:
        logging.error(f"Failed to create dummy logo: {e}")


if not os.path.exists(DUMMY_OPTICS_IMAGE_PATH):
    try:
        fig_optics = Figure(figsize=(2.574, 3.861)) # Approx 1/100th scale for speed
        canvas_optics = FigureCanvas(fig_optics)
        ax_optics = fig_optics.add_subplot(111)
        ax_optics.text(0.5, 0.5, 'Optics Image', ha='center', va='center')
        ax_optics.axis('off')
        fig_optics.savefig(DUMMY_OPTICS_IMAGE_PATH)
        logging.info(f"Created dummy optics image at {DUMMY_OPTICS_IMAGE_PATH}")
    except Exception as e:
        logging.error(f"Failed to create dummy optics image: {e}")


########################################
# GLOBAL INTERRUPT MANAGEMENT
########################################
active_requests = {}  # e.g. {"3": request_id, "6": request_id, ...}

def check_interrupt(task_key, request_id):
    if active_requests.get(task_key) != request_id:
        raise Exception("Aborted: a newer slider update was received.")

########################################
# GLOBAL IMAGE LOADING
########################################
DEFAULT_IMAGE_FILENAME = "Tall1.jpg" # Default image filename
DEFAULT_IMAGE_PATH = os.path.join(STATIC_FOLDER, DEFAULT_IMAGE_FILENAME)

# Create a dummy default image if it doesn't exist
if not os.path.exists(DEFAULT_IMAGE_PATH):
    try:
        dummy_img_array = np.zeros((MAX_DIMENSION, MAX_DIMENSION, 4), dtype=np.uint8) # RGBA
        dummy_img_array[10:MAX_DIMENSION-10, 10:MAX_DIMENSION-10, 0] = 255 # Red square
        dummy_img_array[10:MAX_DIMENSION-10, 10:MAX_DIMENSION-10, 3] = 255 # Full Alpha
        mpimg.imsave(DEFAULT_IMAGE_PATH, dummy_img_array)
        logging.info(f"Created dummy default image at {DEFAULT_IMAGE_PATH}")
    except Exception as e:
        logging.error(f"Could not create dummy default image: {e}")


global_image_rgba = None # Will store image as RGBA float [0,1]
img_height, img_width = MAX_DIMENSION, MAX_DIMENSION # Default placeholder
img_aspect_ratio = 1.0

def load_and_process_image(filepath):
    global global_image_rgba, img_height, img_width, img_aspect_ratio
    try:
        img_data_raw = mpimg.imread(filepath)
    except FileNotFoundError:
        logging.error(f"Image file {filepath} not found!")
        # Fallback to a black placeholder if default also fails
        img_data_raw = np.zeros((MAX_DIMENSION, MAX_DIMENSION, 4), dtype=np.float32) # RGBA
        img_data_raw[:,:,3] = 1.0 # Full alpha

    # Normalize image data to [0, 1] if it's in [0, 255] (uint8)
    if img_data_raw.dtype == np.uint8:
        img_data_raw = img_data_raw / 255.0
    
    # Ensure image is resized if too large (from upload, not default)
    h_orig, w_orig = img_data_raw.shape[0], img_data_raw.shape[1]
    if filepath != DEFAULT_IMAGE_PATH and (h_orig > MAX_DIMENSION or w_orig > MAX_DIMENSION): # Only resize uploads if too big
        factor = max(h_orig, w_orig) / MAX_DIMENSION
        new_h, new_w = int(h_orig / factor), int(w_orig / factor)
        img_data_raw = resize(img_data_raw, (new_h, new_w), anti_aliasing=True, mode='reflect')
        img_data_raw = np.clip(img_data_raw, 0, 1)


    # Process image into RGBA float [0,1]
    if img_data_raw.ndim == 2: # Grayscale image
        img_rgb = np.stack((img_data_raw,)*3, axis=-1) 
        img_alpha = np.ones(img_data_raw.shape, dtype=np.float32)
    elif img_data_raw.shape[2] == 3: # RGB image
        img_rgb = img_data_raw
        img_alpha = np.ones((img_data_raw.shape[0], img_data_raw.shape[1]), dtype=np.float32)
    elif img_data_raw.shape[2] == 4: # RGBA image
        img_rgb = img_data_raw[:,:,:3]
        img_alpha = img_data_raw[:,:,3]
    else: # Fallback for unexpected shapes
        logging.warning(f"Unexpected image shape: {img_data_raw.shape}. Using placeholder.")
        img_rgb = np.zeros((MAX_DIMENSION, MAX_DIMENSION, 3), dtype=np.float32)
        img_alpha = np.ones((MAX_DIMENSION, MAX_DIMENSION), dtype=np.float32)

    global_image_rgba = np.concatenate((img_rgb, img_alpha[:,:,np.newaxis]), axis=2)
    img_height, img_width = global_image_rgba.shape[:2]
    img_aspect_ratio = img_width / img_height if img_height > 0 else 1.0
    logging.info(f"Image loaded: {filepath}, Size: {img_width}x{img_height}")

load_and_process_image(DEFAULT_IMAGE_PATH) # Load default image at startup

H, W = img_height, img_width # For old code compatibility if needed, prefer img_height, img_width

########################################
# GENERIC BLANK IMAGE (for aborted computations)
########################################
def generate_blank_image():
    fig = Figure(figsize=(4,4))
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, 'Cancelled / Error', horizontalalignment='center',
            verticalalignment='center', transform=ax.transAxes, fontsize=16)
    ax.axis('off')
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

########################################
# HELPER FUNCTIONS FOR TASK 12 (PRISM MODEL)
########################################
def get_prism_color_for_frequency(f): 
    if 405e12 <= f < 480e12: return (1, 0, 0) # Red
    elif 480e12 <= f < 510e12: return (1, 127/255, 0) # Orange
    elif 510e12 <= f < 530e12: return (1, 1, 0) # Yellow
    elif 530e12 <= f < 600e12: return (0, 1, 0) # Green
    elif 600e12 <= f < 620e12: return (0, 1, 1) # Cyan
    elif 620e12 <= f < 680e12: return (0, 0, 1) # Blue
    else: return (137/255, 0, 1) # Violet

def draw_triangle_prism(ax, alpha_rad): 
    half_base = np.sin(alpha_rad / 2.0)
    height = np.cos(alpha_rad / 2.0)
    
    left_vertex = (-half_base, 0)
    right_vertex = (half_base, 0)
    top_vertex = (0, height)
    
    vertices = [left_vertex, top_vertex, right_vertex, left_vertex]
    x_coords, y_coords = zip(*vertices)
    ax.plot(x_coords, y_coords, 'r-', linewidth=2, zorder=0) 

def get_refractive_index_sellmeier(wavelength_m): 
    x_um = wavelength_m * 1e6
    a_coeffs = np.array([1.03961212, 0.231792344, 1.01146945])
    b_coeffs = np.array([0.00600069867, 0.0200179144, 103.560653])
    
    n_sq_minus_1 = np.zeros_like(x_um)
    for i in range(len(a_coeffs)):
        n_sq_minus_1 += (a_coeffs[i] * (x_um**2)) / ((x_um**2) - b_coeffs[i] + 1e-9) 
    return np.sqrt(np.maximum(1, 1 + n_sq_minus_1)) 


########################################
# TASK 12a PLOT FUNCTION (Dynamic Prism Model) - Revised
########################################
def generate_task12a_plot(ThetaI_deg_slider, alpha_deg_slider, canvas_scale_12a, request_id): # Added canvas_scale_12a
    try:
        check_interrupt("12a", request_id)
        
        alpha_rad = np.deg2rad(alpha_deg_slider)     
        ThetaI_abs_rad = np.deg2rad(ThetaI_deg_slider)

        # Banned validation: ThetaI_deg_slider <= 90 - alpha_deg_slider / 2
        # This validation is primarily handled client-side for responsiveness,
        # but server-side can also enforce or log if needed.
        # max_theta_i_deg = 90.0 - alpha_deg_slider / 2.0
        # if ThetaI_deg_slider > max_theta_i_deg:
        #     ThetaI_deg_slider = max_theta_i_deg # Enforce server-side too
        #     ThetaI_abs_rad = np.deg2rad(ThetaI_deg_slider)


        N_L_angle = np.pi - alpha_rad / 2.0
        N_R_angle = alpha_rad / 2.0

        frequencies = np.linspace(405e12, 790e12, 50) 
        wavelengths_m = 3e8 / frequencies
        n_prism_array = get_refractive_index_sellmeier(wavelengths_m)
        n_air = 1.0

        all_segments_incident = []
        all_segments_internal = []
        all_segments_exit = []
        all_colors = []

        P1_x = -np.sin(alpha_rad/2.0) * 0.5
        P1_y = np.cos(alpha_rad/2.0) * 0.5 
        
        P0_x = P1_x - 1.0 * np.cos(ThetaI_abs_rad)
        P0_y = P1_y - 1.0 * np.sin(ThetaI_abs_rad)

        for i in range(len(frequencies)):
            check_interrupt("12a", request_id)
            n_prism = n_prism_array[i]
            ray_color = get_prism_color_for_frequency(frequencies[i])
            all_colors.append(ray_color)

            i1_raw = N_L_angle - ThetaI_abs_rad
            i1_raw = pi - i1_raw
            i1_signed = atan2(sin(i1_raw), cos(i1_raw))
            
            sin_r1_signed = (n_air / n_prism) * np.sin(i1_signed)
            if abs(sin_r1_signed) > 1.0: 
                P2_x, P2_y = P1_x + 0.1*cos(ThetaI_abs_rad), P1_y + 0.1*sin(ThetaI_abs_rad) 
                all_segments_incident.append([[P0_x, P0_y], [P1_x, P1_y]])
                all_segments_internal.append([[P1_x, P1_y], [P2_x, P2_y]]) 
                all_segments_exit.append([[P2_x, P2_y], [P2_x, P2_y]]) 
                continue

            r1_signed = np.arcsin(sin_r1_signed)
            
            d_internal_abs = N_L_angle + r1_signed
            d_internal_real = (N_L_angle + r1_signed + pi) % (2*pi)

            denom_t = -np.cos(d_internal_abs - alpha_rad/2.0)
            if abs(denom_t) < 1e-9: 
                P2_x, P2_y = P1_x + 1.0*cos(d_internal_abs), P1_y + 1.0*sin(d_internal_abs) 
            else:
                numer_t = P1_x*np.cos(alpha_rad/2.0) - np.sin(alpha_rad/2.0)*np.cos(alpha_rad/2.0) + P1_y*np.sin(alpha_rad/2.0)
                t_to_P2 = numer_t / denom_t
                P2_x = P1_x + t_to_P2 * np.cos(d_internal_abs)
                P2_y = P1_y + t_to_P2 * np.sin(d_internal_abs)

            i2_raw = d_internal_real - N_R_angle
            i2_signed = atan2(sin(i2_raw), cos(i2_raw)) 

            sin_i2_mag = np.abs(np.sin(i2_signed))
            
            d_exit_abs = d_internal_abs 
            is_tir = False
            if n_prism * sin_i2_mag > n_air: 
                is_tir = True
                r2_signed_tir = -i2_signed + pi 
                d_exit_abs = N_R_angle + r2_signed_tir
                d_exit_abs %= 2 * pi
            else: 
                sin_r2_signed = (n_prism / n_air) * np.sin(i2_signed)
                r2_signed = np.arcsin(np.clip(sin_r2_signed, -1, 1))
                d_exit_abs = N_R_angle + r2_signed
            
            P3_x = P2_x + 1.0 * np.cos(d_exit_abs)
            P3_y = P2_y + 1.0 * np.sin(d_exit_abs)

            all_segments_incident.append([[P0_x, P0_y], [P1_x, P1_y]])
            all_segments_internal.append([[P1_x, P1_y], [P2_x, P2_y]])
            all_segments_exit.append([[P2_x, P2_y], [P3_x, P3_y]])

        fig = Figure(figsize=(8, 6)) # Base figsize
        fig.patch.set_facecolor('black')
        ax = fig.add_subplot(111, facecolor="black")
        
        if all_segments_incident:
            lc_incident = LineCollection(np.array(all_segments_incident), colors="white", alpha=0.6, linewidths=0.8, zorder=1)
            ax.add_collection(lc_incident)
        if all_segments_internal:
            lc_internal = LineCollection(np.array(all_segments_internal), colors=all_colors, alpha=0.8, linewidths=1.2, zorder=1)
            ax.add_collection(lc_internal)
        if all_segments_exit:
            lc_exit = LineCollection(np.array(all_segments_exit), colors=all_colors, alpha=0.8, linewidths=1.2, zorder=1)
            ax.add_collection(lc_exit)
            
        draw_triangle_prism(ax, alpha_rad)
        
        # Apply canvas scale
        base_xlim = (-1.6, 1.6)
        base_ylim = (-0.8, 1.2)
        ax.set_xlim(base_xlim[0] * canvas_scale_12a, base_xlim[1] * canvas_scale_12a)
        ax.set_ylim(base_ylim[0] * canvas_scale_12a, base_ylim[1] * canvas_scale_12a)
        
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        for spine in ax.spines.values(): spine.set_edgecolor('white')
        ax.xaxis.label.set_color('white'); ax.yaxis.label.set_color('white'); ax.title.set_color('white')
        ax.set_aspect('equal', adjustable='box')


        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Task 12a plot error: {e}", exc_info=True)
        return generate_blank_image()


########################################
# INTERACTIVE TEMPLATE WITH SPINNER, ANIMATION, AND NAVIGATION
########################################
interactive_template = '''
<!DOCTYPE html>
<html>
<head>  
  <title>{{ title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; padding: 10px; background-color: #f0f0f0; color: #333; }
    .container { max-width: 900px; margin: auto; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    h1 { color: #0056b3; text-align: center; }
    .slider-container { margin: 20px 0; }
    .slider-block { margin-bottom: 15px; padding: 10px; background-color: #f9f9f9; border-radius: 5px; }
    label { font-weight: bold; margin-bottom: 5px; display: block; color: #555; }
    input[type=range] { width: 100%; cursor: pointer; }
    .plot-container { position: relative; text-align: center; margin-top: 20px; min-height:300px; background-color:#eee; border-radius:4px; padding:10px;}
    .plot-image { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;}
    .spinner {
      border: 10px solid #f3f3f3; border-top: 10px solid #3498db; border-radius: 50%;
      width: 60px; height: 60px; animation: spin 1s linear infinite;
      position: absolute; left: 50%; top: 40%; transform: translate(-50%, -50%); z-index: 10; display: none;
    }
    .loading-text {
      position: absolute; top: calc(40% + 40px); left: 50%; transform: translateX(-50%);
      font-size: 1.1em; color: #3498db; z-index: 10; display: none;
    }
    @keyframes spin { 0% { transform: translate(-50%, -50%) rotate(0deg); } 100% { transform: translate(-50%, -50%) rotate(360deg); } }
    .play-button, .back-button, .small-task-button, .subtask-nav-button {
      padding: 10px 18px; border: none; border-radius: 5px; font-size: 0.95em; cursor: pointer; margin: 5px;
      transition: background-color 0.2s ease-in-out; text-decoration: none; display: inline-block;
    }
    .play-button { background-color: #28a745; color: white; }
    .play-button:hover { background-color: #218838; }
    .back-button { background-color: #007BFF; color: white; }
    .back-button:hover { background-color: #0056b3; }
    .nav-buttons-footer { margin-top: 30px; text-align: center; padding-top: 20px; border-top: 1px solid #eee; }
    .small-task-button { background-color: #6c757d; color: white; font-size: 0.8em; padding: 6px 12px;}
    .small-task-button:hover { background-color: #545b62; }
    .subtask-nav-button { background-color: #17a2b8; color: white; }
    .subtask-nav-button:hover { background-color: #117a8b; }
    .keypress-instructions { margin-top: 15px; padding: 10px; background-color: #e9ecef; border-radius: 4px; font-size: 0.9em; }
  </style>
</head>
<body>
  <div class="container">
    <h1>{{ title }}</h1>
    <div class="slider-container">
      {% for slider in sliders %}
        <div class="slider-block">
           <label for="{{ slider.id }}">{{ slider.label }} (<span id="{{ slider.id }}_value">{{ slider.value }}</span>{{ slider.unit if slider.unit else '' }})</label>
           <input type="range" id="{{ slider.id }}" name="{{ slider.id }}" min="{{ slider.min }}" max="{{ slider.max }}" value="{{ slider.value }}" step="{{ slider.step }}">
        </div>
      {% endfor %}
    </div>

    {% if task_id_for_template == "12a" %}
    <div class="keypress-instructions">
        <p><strong>Keypress controls (active anywhere on this page):</strong></p>
        <ul>
            <li>Incident Angle (ThetaI): 'Q' (decrease), 'W' (increase)</li>
            <li>Prism Apex Angle (alpha): 'A' (decrease), 'S' (increase)</li>
        </ul>
    </div>
    {% endif %}

    {% if playable %}
      <div style="text-align: center; margin-bottom: 20px;">
        <button class="play-button" id="playButton">Play Animation</button>
      </div>
    {% endif %}

    <div class="plot-container">
      <img id="plotImage" src="{{ plot_endpoint }}?{{ initial_query }}" alt="Interactive Plot" class="plot-image">
      <div id="spinner" class="spinner"></div>
      <div id="loadingText" class="loading-text">Processing...</div>
    </div>
  </div>

  <div class="nav-buttons-footer">
      <button class="back-button" onclick="window.location.href='{{ url_for('index') }}'">Back to Home</button>
      {% for key, task_info in tasks_overview.items() %}
         {% if key not in ['1a', '1b', '11a', '11b', '11c', '11d', '12a', '12b', '12bi', '12bii', '12biii'] %} {# Only show main tasks/subtask groups in footer #}
            {% if task_info.subtasks and task_info.subtasks|length > 0 %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('subtask_page', task_id=key) }}'">{{ task_info.button_text if task_info.button_text else task_info.title }}</button>
            {% else %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('handle_task', task_id=key) }}'">{{ task_info.button_text if task_info.button_text else task_info.title }}</button>
            {% endif %}
         {% endif %}
      {% endfor %}
  </div>

  <script>
    var requestTimer = null;
    var uniqueRequestId = null; 

    function formatDisplayValue(sliderId, rawValue) {
        let displayValue;
        const floatVal = parseFloat(rawValue);
        if (sliderId === "v" || sliderId === "v_task4") { 
            displayValue = Math.pow(10, floatVal).toExponential(2);
        } else if (String(rawValue).includes('.') && Math.abs(floatVal) < 0.01 && floatVal !== 0) {
            displayValue = floatVal.toExponential(2);
        } else if (String(rawValue).includes('.')) {
            const stepStr = document.getElementById(sliderId).step;
            let precision = 2;
            if (stepStr && stepStr.includes('.')) {
                precision = stepStr.split('.')[1].length;
            } else if (Math.abs(floatVal) < 10 && !Number.isInteger(floatVal)) {
                 precision = 2;
            } else if (Number.isInteger(floatVal)){
                 precision = 0;
            }
            displayValue = floatVal.toFixed(precision);
        } else {
            displayValue = floatVal.toString();
        }
        return displayValue;
    }

    function updatePlot() {
      if (requestTimer) {
        clearTimeout(requestTimer);
      }
      requestTimer = setTimeout(function() {
        const params = {};
        uniqueRequestId = new Date().getTime().toString(); 
        params["_req_id"] = uniqueRequestId;

        {% for slider in sliders %}
          let rawValue_{{ slider.id }} = document.getElementById("{{ slider.id }}").value;
          document.getElementById("{{ slider.id }}_value").innerText = formatDisplayValue("{{ slider.id }}", rawValue_{{ slider.id }});
          params["{{ slider.id }}"] = rawValue_{{ slider.id }};
        {% endfor %}

        const query = new URLSearchParams(params);
        document.getElementById("spinner").style.display = "block";
        document.getElementById("loadingText").style.display = "block";
        document.getElementById("plotImage").src = "{{ plot_endpoint }}?" + query.toString();
      }, 150); 
    }

    {% if banned_validation %} // For Task 6 (original banned validation)
      var IMG_WIDTH_JS = {{ img_width if img_width else 100 }}; 
      var oldValues = {};
      {% for slider in sliders %}
         oldValues["{{ slider.id }}"] = parseFloat(document.getElementById("{{ slider.id }}").value);
      {% endfor %}

      function sliderChangedWithValidation(event) { // This is for task 6
        var sliderId = event.target.id;
        var newValue = parseFloat(event.target.value);
        var startXElement = document.getElementById("start_x");
        var fValElement = document.getElementById("f_val");

        if (startXElement && fValElement) {
            var start_x = parseFloat(startXElement.value);
            var f_val = parseFloat(fValElement.value); 

            if (sliderId === "start_x") { 
              if (start_x <= f_val && f_val <= start_x + IMG_WIDTH_JS) { 
                if (newValue <= f_val && f_val <= newValue + IMG_WIDTH_JS) { 
                    if (newValue > oldValues["start_x"]) { fValElement.value = newValue + IMG_WIDTH_JS + 1; } 
                    else { fValElement.value = newValue - 1; } 
                    document.getElementById("f_val_value").innerText = formatDisplayValue("f_val", fValElement.value);
                }
              }
            } else if (sliderId === "f_val") { 
              if (start_x <= newValue && newValue <= start_x + IMG_WIDTH_JS) { 
                if (newValue > oldValues["f_val"]) { fValElement.value = start_x + IMG_WIDTH_JS + 1; }
                else { fValElement.value = start_x - 1; }
                document.getElementById("f_val_value").innerText = formatDisplayValue("f_val", fValElement.value);
              }
            }
        }
        oldValues[sliderId] = parseFloat(document.getElementById(sliderId).value); 
        updatePlot();
      }
    {% endif %}

    {% for slider in sliders %}
      {% if task_id_for_template == "12a" and (slider.id == "ThetaI" or slider.id == "alpha" or slider.id == "canvas_scale_12a") %}
        document.getElementById("{{ slider.id }}").addEventListener("input", function(event) {
          if (document.getElementById("ThetaI") && document.getElementById("alpha")) { // Ensure both sliders exist
              var thetaISlider = document.getElementById("ThetaI");
              var alphaSlider = document.getElementById("alpha");
              var thetaIVal = parseFloat(thetaISlider.value);
              var alphaVal = parseFloat(alphaSlider.value);
              
              let stepAttr = thetaISlider.getAttribute('step');
              let stepPrecision = 0;
              if (stepAttr && stepAttr.includes('.')) {
                  stepPrecision = stepAttr.split('.')[1].length;
              }

              var maxThetaI = 90.0 - (alphaVal / 2.0);
              if (thetaIVal > maxThetaI) {
                  thetaISlider.value = maxThetaI.toFixed(stepPrecision);
                  // document.getElementById("ThetaI_value").innerText = formatDisplayValue("ThetaI", thetaISlider.value); // updatePlot will do this
              }
          }
          updatePlot();
        });
      {% elif banned_validation and task_id_for_template == "6" %} // Task 6 specific validation
        document.getElementById("{{ slider.id }}").addEventListener("input", sliderChangedWithValidation);
      {% else %} // Default behavior
        document.getElementById("{{ slider.id }}").addEventListener("input", updatePlot);
      {% endif %}
    {% endfor %}
    
    {% if task_id_for_template == "12a" %}
    document.addEventListener('keydown', function(e) {
        // Check if the event target is an input field, if so, don't process global keys.
        // This prevents interference if user is typing in a future text input on the page.
        if (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'textarea') {
            return;
        }

        var thetaISlider = document.getElementById('ThetaI');
        var alphaSlider = document.getElementById('alpha');
        // No specific key for canvas_scale_12a for now, can be added if needed.

        if (!thetaISlider || !alphaSlider) return;

        let thetaStep = parseFloat(thetaISlider.step);
        let thetaValue = parseFloat(thetaISlider.value);
        let thetaMin = parseFloat(thetaISlider.min);
        let thetaMax = parseFloat(thetaISlider.max); 

        let alphaStep = parseFloat(alphaSlider.step);
        let alphaValue = parseFloat(alphaSlider.value);
        let alphaMin = parseFloat(alphaSlider.min);
        let alphaMax = parseFloat(alphaSlider.max);

        let keyProcessed = false;

        if (e.key.toLowerCase() === 'q') { 
            thetaValue = Math.max(thetaMin, thetaValue - thetaStep); 
            keyProcessed = true; 
        } else if (e.key.toLowerCase() === 'w') { 
            thetaValue = Math.min(thetaMax, thetaValue + thetaStep); 
            keyProcessed = true; 
        } else if (e.key.toLowerCase() === 'a') { 
            alphaValue = Math.max(alphaMin, alphaValue - alphaStep); 
            keyProcessed = true; 
        } else if (e.key.toLowerCase() === 's') { 
            alphaValue = Math.min(alphaMax, alphaValue + alphaStep); 
            keyProcessed = true; 
        }

        if (keyProcessed) {
            e.preventDefault(); // Prevent default browser action for these keys (e.g., scrolling)
            
            thetaISlider.value = thetaValue;
            alphaSlider.value = alphaValue;

            // Perform validation after key press updates values
            var currentAlphaVal = parseFloat(alphaSlider.value); // Re-read potentially changed alpha
            var currentThetaIVal = parseFloat(thetaISlider.value); // Re-read potentially changed thetaI
            
            let stepAttrTheta = thetaISlider.getAttribute('step');
            let stepPrecisionTheta = 0;
            if (stepAttrTheta && stepAttrTheta.includes('.')) {
                stepPrecisionTheta = stepAttrTheta.split('.')[1].length;
            }

            var maxThetaIAfterKey = 90.0 - (currentAlphaVal / 2.0);
            if (currentThetaIVal > maxThetaIAfterKey) {
                thetaISlider.value = maxThetaIAfterKey.toFixed(stepPrecisionTheta);
            }
            
            // Update displayed values (updatePlot will also do this, but this makes UI feel more responsive)
            // document.getElementById('ThetaI_value').innerText = formatDisplayValue('ThetaI', thetaISlider.value);
            // document.getElementById('alpha_value').innerText = formatDisplayValue('alpha', alphaSlider.value);
            
            updatePlot(); // This will also update the display values
        }
    });
    {% endif %}


    document.querySelectorAll('input[type=range]').forEach(function(slider) {
      slider.addEventListener("keydown", function(e) { // General arrow key support for focused sliders
         let step = parseFloat(slider.step);
         if (isNaN(step) || step <= 0) { 
            let min = parseFloat(slider.min);
            let max = parseFloat(slider.max);
            step = (max - min) / 100; 
            if (slider.id === "v" || slider.id === "v_task4") step = 0.01; 
         }
         let value = parseFloat(slider.value);
         let min = parseFloat(slider.min);
         let max = parseFloat(slider.max);
         let keyProcessed = false;

         // Specific key bindings for 12a are now handled by the global listener if task_id_for_template == "12a"
         // So, we ensure this block does not also process QWAS for 12a.
         // The global listener for 12a does not use slider.id checks, it directly targets ThetaI and alpha.
         // This general handler is for arrow keys on ANY slider.
         
         if(e.key === "ArrowRight" || e.key === "ArrowUp"){ value = Math.min(max, value + step); keyProcessed = true; } 
         else if(e.key === "ArrowLeft" || e.key === "ArrowDown"){ value = Math.max(min, value - step); keyProcessed = true; }
         

         if (keyProcessed) {
             slider.value = value;
             // For task 12a, if QWAS was pressed, the global handler already called updatePlot.
             // If arrow keys were pressed on a 12a slider, this will trigger updatePlot.
             // If it's not 12a, it triggers updatePlot.
             // The validation for 12a is tied to its specific "input" event, not this "keydown".
             // So, after arrow key change on 12a slider, we need to ensure validation runs before plot.
             // The "input" event listener for 12a sliders already calls updatePlot.
             // Manually triggering "input" event might be an option, or call the validation + updatePlot sequence.
             
             // Simplest: let updatePlot handle display update.
             // For 12a, the input listener will do the validation.
             // We need to ensure that if an arrow key changes a 12a slider, its specific input listener logic is triggered.
             // Setting slider.value programmatically does not fire "input" event automatically.
             // So, we dispatch it:
             var inputEvent = new Event('input', { bubbles: true, cancelable: true });
             slider.dispatchEvent(inputEvent);
             // updatePlot(); // updatePlot is now called by the 'input' event listener including 12a's custom one.
             e.preventDefault();
         }
      });
    });

    document.getElementById("plotImage").addEventListener("load", function() {
      const currentSrc = document.getElementById("plotImage").src;
      if (currentSrc.includes("_req_id=" + uniqueRequestId) || !currentSrc.includes("_req_id=")) {
          document.getElementById("spinner").style.display = "none";
          document.getElementById("loadingText").style.display = "none";
      }
    });
    document.getElementById("plotImage").addEventListener("error", function() {
      const currentSrc = document.getElementById("plotImage").src;
       if (currentSrc.includes("_req_id=" + uniqueRequestId) || !currentSrc.includes("_req_id=")){
          document.getElementById("spinner").style.display = "none";
          document.getElementById("loadingText").style.display = "none";
          console.error("Failed to load plot image: " + currentSrc);
      }
    });

    {% if playable %}
      var currentAnimation = null;
      var animationSliderId = "{{ sliders[0].id }}"; 

      document.getElementById("playButton").addEventListener("click", function() {
         if (currentAnimation) { 
            clearInterval(currentAnimation); currentAnimation = null;
            document.getElementById("playButton").innerText = "Play Animation"; return;
         }
         document.getElementById("playButton").innerText = "Stop Animation";
         var slider = document.getElementById(animationSliderId);
         var startVal = parseFloat(slider.min); var endVal = parseFloat(slider.max);
         var stepVal = parseFloat(slider.step); var interval = 1000; 

         slider.value = startVal;
         // Dispatch input event to trigger updates and validation if any
         var inputEvent = new Event('input', { bubbles: true, cancelable: true });
         slider.dispatchEvent(inputEvent);
         // updatePlot(); // Called by the input event listener

         var current = startVal;
         currentAnimation = setInterval(function() {
            current += stepVal;
            if (current > endVal) {
               current = startVal; 
            }
            slider.value = current;
            slider.dispatchEvent(inputEvent); // Triggers validation and updatePlot
         }, interval);
      });
    {% endif %}

    window.onload = function() {
        {% for slider in sliders %}
            // Initial value display update
            document.getElementById("{{ slider.id }}_value").innerText = formatDisplayValue("{{ slider.id }}", document.getElementById("{{ slider.id }}").value);
            
            // For Task 12a, run initial validation after setting up values
            {% if task_id_for_template == "12a" and (slider.id == "ThetaI" or slider.id == "alpha") %}
              if (document.getElementById("ThetaI") && document.getElementById("alpha")) {
                var thetaISlider = document.getElementById("ThetaI");
                var alphaSlider = document.getElementById("alpha");
                var thetaIVal = parseFloat(thetaISlider.value);
                var alphaVal = parseFloat(alphaSlider.value);
                
                let stepAttr = thetaISlider.getAttribute('step');
                let stepPrecision = 0;
                if (stepAttr && stepAttr.includes('.')) {
                    stepPrecision = stepAttr.split('.')[1].length;
                }

                var maxThetaI = 90.0 - (alphaVal / 2.0);
                if (thetaIVal > maxThetaI) {
                    thetaISlider.value = maxThetaI.toFixed(stepPrecision);
                    document.getElementById("ThetaI_value").innerText = formatDisplayValue("ThetaI", thetaISlider.value);
                }
              }
            {% endif %}
        {% endfor %}
        
        // Initial plot load
        const initialParams = {};
        uniqueRequestId = new Date().getTime().toString();
        initialParams["_req_id"] = uniqueRequestId;
        {% for slider in sliders %}
            initialParams["{{ slider.id }}"] = document.getElementById("{{ slider.id }}").value;
        {% endfor %}
        const initialQuery = new URLSearchParams(initialParams);
        document.getElementById("spinner").style.display = "block";
        document.getElementById("loadingText").style.display = "block";
        document.getElementById("plotImage").src = "{{ plot_endpoint }}?" + initialQuery.toString();
    };
  </script>
</body>
</html>
'''

def render_interactive_page(slider_config, title, plot_endpoint, task_id_for_template, banned_validation=False, extra_context=None, playable=False):
    if extra_context is None: extra_context = {}
    for slider in slider_config: slider.setdefault('unit', '')

    initial_params = { slider["id"]: slider["value"] for slider in slider_config }
    initial_query_list = []
    for key, value in initial_params.items():
        initial_query_list.append(f"{key}={value}")
    initial_query = "&".join(initial_query_list)
    
    current_img_width = img_width if 'img_width' in globals() and img_width is not None else 100

    context = {
        "sliders": slider_config, "title": title, "plot_endpoint": plot_endpoint,
        "initial_query": initial_query, 
        "banned_validation": banned_validation and task_id_for_template == "6", # Make specific to task 6
        "playable": playable, "img_width": current_img_width,
        "tasks_overview": task_overview, "task_id_for_template": task_id_for_template
    }
    context.update(extra_context)
    return render_template_string(interactive_template, **context)

########################################
# INTERACTIVE TASKS CONFIGURATION
########################################
interactive_tasks = {
    "3": {
        "title": "Task 3: Reflection Travel Time",
        "sliders": [
            {"id": "v", "label": "Speed (m/s)", "min": round(log10(3),3), "max": round(log10(3e8),3), "value": round(log10(3e8),3), "step": 0.05, "unit": " m/s"},
            {"id": "n", "label": "Refractive Index", "min": 1, "max": 3, "value": 1, "step": 0.05},
            {"id": "y", "label": "Height (m)", "min": 1, "max": 10, "value": 1, "step": 0.1},
            {"id": "l", "label": "Length (m)", "min": 0.1, "max": 3.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/3",
    },
    "4": {
        "title": "Task 4: Refraction Travel Time",
        "sliders": [
            {"id": "v_task4", "label": "Log10(Speed)", "min": round(log10(3),3), "max": round(log10(3e8),3), "value": round(log10(3e8),3), "step": 0.05, "unit": " m/s"},
            {"id": "n1", "label": "Refractive Index 1", "min": 1, "max": 3, "value": 1.0, "step": 0.05},
            {"id": "n2", "label": "Refractive Index 2", "min": 1, "max": 3, "value": 1.5, "step": 0.05},
            {"id": "y_task4", "label": "Height (m)", "min": 1, "max": 10, "value": 1, "step": 0.1},
            {"id": "l_task4", "label": "Length (m)", "min": 0.1, "max": 3.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/4",
    },
    "5": {
        "title": "Task 5: Virtual Image Plot",
        "sliders": [
            {"id": "offset_x", "label": "Object X Dist from Mirror", "min": 0, "max": int(3 * (img_width if img_width else W)), "value": int((img_width if img_width else W)/10.0 +1), "step": max(1,int(W/20)), "unit":"px"},
            {"id": "offset_y", "label": "Object Y Offset from Center (slider increase moves object UP)", "min": int(-(img_height if img_height else H)), "max": int(img_height if img_height else H), "value": 0, "step": max(1,int(H/20)), "unit":"px"},
            {"id": "canvas_size", "label": "Canvas Size", "min": int(max(W, H) * 1.5), "max": int(max(W, H) * 5), "value": int(max(W,H)*3), "step": 10, "unit":"px"}
        ],
        "plot_endpoint": "/plot/5",
    },
    "6": { 
        "title": "Task 6+7: Converging Lens Model",
        "sliders": [
            {"id": "start_x", "label": "Object Start X (from lens)", "min": 0, "max": int(3 * (img_width if img_width else W)), "value": int(1.5*(img_width if img_width else W)), "step": max(1,int(W/20)), "unit":"px"},
            {"id": "start_y", "label": "Object Start Y (from axis, slider increase moves object UP, image DOWN if inverted)", "min": -int(1.5 * (img_height if img_height else H)), "max": int(1.5 * (img_height if img_height else H)), "value": 0, "step": max(1,int(H/20)), "unit":"px"},
            {"id": "scale", "label": "Canvas Scale Factor", "min": 1, "max": 15, "value": 7, "step": 1},
            {"id": "f_val", "label": "Focal Length", "min": 1, "max": int(2 * (img_width if img_width else W)), "value": int(0.75*(img_width if img_width else W)), "step": max(1,int(W/20)), "unit":"px"}
        ],
        "plot_endpoint": "/plot/6",
        "banned_validation": True, 
        "extra_context": {"img_width": img_width if img_width else W} 
    },
    "8": {
        "title": "Task 8: Concave Mirror (Spherical Aberration)",
        "sliders": [
            {"id": "R_val_t8", "label": "Mirror Radius (R)", "min": 0.2, "max": 5.0, "value": 2.0, "step": 0.05, "unit":" units"},
            {"id": "obj_left_x_t8", "label": "Object Left X (from C)", "min": 0.01, "max": 5.0, "value": 1.5, "step": 0.05, "unit":" units"}, 
            {"id": "obj_center_y_t8", "label": "Object Center Y (from axis)", "min": -2.0, "max": 2.0, "value": 0.0, "step": 0.05, "unit":" units"},
            {"id": "obj_world_height_t8", "label": "Object Height", "min": 0.1, "max": 3.0, "value": 0.5, "step": 0.05, "unit":" units"},
            {"id": "plot_zoom_t8", "label": "Plot Zoom", "min": 0.5, "max": 4.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/8",
    },
    "9": {
        "title": "Task 9: Convex Mirror (Object Right of Pole)",
        "sliders": [
            {"id": "R_val_t9", "label": "Mirror Radius (R)", "min": 0.2, "max": 5.0, "value": 1.0, "step": 0.05, "unit":" units"},
            {"id": "obj_center_x_t9", "label": "Object Center X (from C)", "min": 1.0 + 0.35/2 + 0.01, "max": 4.5, "value": 1.8, "step": 0.02, "unit":" units"}, 
            {"id": "obj_center_y_t9", "label": "Object Center Y (from axis)", "min": -2.0, "max": 2.0, "value": 0.0, "step": 0.02, "unit":" units"},
            {"id": "obj_height_factor_t9", "label": "Obj Height Factor (rel to R)", "min": 0.1, "max": 1.5, "value": 0.7, "step": 0.05},
            {"id": "plot_zoom_t9", "label": "Plot Zoom", "min": 0.15, "max": 6.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/9",
    },
    "10": {
        "title": "Task 10: Anamorphic Image Mapping",
        "sliders": [
            {"id": "Rf", "label": "Projection Scale (R_effective / R_base)", "min": 1, "max": 10, "value": 3, "step": 0.1},
            {"id": "arc_angle", "label": "Arc Angle", "min": 10, "max": 360, "value": 160, "step": 5, "unit":" deg"}
        ],
        "plot_endpoint": "/plot/10",
    },
    "11d": {
        "title": "Task 11d: Interactive Rainbow Elevation Angles",
        "sliders": [
            {"id": "alpha_11d", "label": "Sun Elevation Angle (α)", "min": 0, "max": 60, "value": 0, "step": 1, "unit":" deg"}
        ],
        "plot_endpoint": "/plot/11d",
        "playable": True
    },
    "12a": { 
        "title": "Task 12a: Interactive Prism Dispersion",
        "sliders": [
            {"id": "ThetaI", "label": "Incident Ray Angle (from horizontal)", "min": 0, "max": 89, "value": 30, "step": 1, "unit":" deg"}, # Max 89 to avoid issues near 90 with 90-alpha/2
            {"id": "alpha", "label": "Prism Apex Angle", "min": 10, "max": 90, "value": 60, "step": 1, "unit":" deg"},
            {"id": "canvas_scale_12a", "label": "Canvas Scale", "min": 0.5, "max": 3.0, "value": 1.0, "step": 0.1} # Added scale slider
        ],
        "plot_endpoint": "/plot/12a", 
        # banned_validation for 12a is handled by custom JS in template
    }
}
# Dynamic update for Task 9 slider based on current image aspect ratio
try:
    default_R_t9 = interactive_tasks["9"]["sliders"][0]["value"] 
    default_h_factor_t9 = interactive_tasks["9"]["sliders"][3]["value"] 
    initial_obj_height_t9 = default_R_t9 * default_h_factor_t9
    initial_obj_width_t9 = img_aspect_ratio * initial_obj_height_t9 if img_aspect_ratio > 0 else initial_obj_height_t9
    min_obj_x_t9 = default_R_t9 + initial_obj_width_t9 / 2.0 + 0.01 * default_R_t9 # Object X is from C, mirror at R from C. Pole at R. Object is to the right of pole.
    interactive_tasks["9"]["sliders"][1]["min"] = round(min_obj_x_t9, 2) 
    if interactive_tasks["9"]["sliders"][1]["value"] < min_obj_x_t9:
        interactive_tasks["9"]["sliders"][1]["value"] = round(min_obj_x_t9,2)
except Exception as e:
    logging.warning(f"Could not dynamically set Task 9 slider min: {e}")


########################################
# TASK OVERVIEW AND BUTTON LABELS
########################################
task_overview = {
    "1": {"title": "Task 1: Refractive Indices", "desc": "Refractive index plots.", "subtasks": {"1a": "Crown Glass Index", "1b": "Water Index"}, "button_text": "Task 1: Refractive Indices"},
    "1a": {"title": "Task 1a: Crown Glass Index", "desc": "Sellmeier formula for crown glass.", "subtasks": {}, "button_text": "1a: Crown Glass Index"},
    "1b": {"title": "Task 1b: Water Index Plot", "desc": "Refractive index of water vs frequency.", "subtasks": {}, "button_text": "1b: Water Index Plot"},
    "2": {"title": "Task 2: Thin Lens Verification", "desc": "Thin lens equation verification.", "subtasks": {}, "button_text": "Task 2: Thin Lens Verification"},
    "3": {"title": "Task 3: Reflection Time", "desc": "Fermat’s principle for reflection.", "subtasks": {}, "button_text": "Task 3: Reflection Time"},
    "4": {"title": "Task 4: Refraction Time", "desc": "Fermat’s principle for refraction.", "subtasks": {}, "button_text": "Task 4: Refraction Time"},
    "5": {"title": "Task 5: Virtual Image", "desc": "Virtual image in a plane mirror.", "subtasks": {}, "button_text": "Task 5: Virtual Image"},
    "6": {"title": "Task 6+7: Converging Lens Image", "desc": "Real image by a converging lens.", "subtasks": {}, "button_text": "Task 6+7: Converging Lens"}, 
    "8": {"title": "Task 8: Concave Mirror Image", "desc": "Real image by a concave spherical mirror.", "subtasks": {}, "button_text": "Task 8: Concave Mirror"},
    "9": {"title": "Task 9: Convex Mirror Image", "desc": "Virtual image by a convex spherical mirror.", "subtasks": {}, "button_text": "Task 9: Convex Mirror"},
    "10": {"title": "Task 10: Anamorphic Projection", "desc": "Anamorphic projection.", "subtasks": {}, "button_text": "Task 10: Anamorphic Projection"},
    "11": {"title": "Task 11: Rainbow Angles", "desc": "Rainbow elevation angles.", "subtasks": {"11a": "Descartes' Model ε Curves", "11b": "Rainbow Color Mapping", "11c": "Refraction Angle Scatter", "11d": "Interactive Refraction Circles"}, "button_text": "Task 11: Rainbow Angles"},
    "11a": {"title": "Task 11a: ε Curves", "desc": "Elevation angles using computed ε curves.", "subtasks": {}, "button_text": "11a: ε Curves"},
    "11b": {"title": "Task 11b: Color Mapping", "desc": "Rainbow curve color mapping.", "subtasks": {}, "button_text": "11b: Color Mapping"},
    "11c": {"title": "Task 11c: Refraction Scatter", "desc": "Scatter plot for refraction angles.", "subtasks": {}, "button_text": "11c: Refraction Scatter"},
    "11d": {"title": "Task 11d: Interactive Circles", "desc": "Interactive refraction circles for rainbow.", "subtasks": {}, "button_text": "11d: Interactive Circles"},
    "12": {
        "title": "Task 12: Prism Analysis", "desc": "Prism light dispersion and angle analysis.",
        "subtasks": { "12a": "Interactive Prism Model", "12b": "Prism Angle Plots" },
        "button_text": "Task 12: Prism Analysis"
    },
    "12a": { 
        "title": "Task 12a: Interactive Prism", "desc": "Dynamic model of white light through a prism.", "subtasks": {},
        "button_text": "12a: Interactive Prism" 
    },
    "12b": { 
        "title": "Task 12b: Prism Angle Plots", "desc": "Static plots related to prism angles.",
        "subtasks": { 
            "12bi": "Transmission Angle vs Incidence",
            "12bii": "Deflection Angle vs Incidence",
            "12biii": "Deflection vs. Vertex Angle"
        },
        "button_text": "12b: Prism Angle Plots" 
    },
    "12bi": {"title": "Task 12bi: Transmission Angle", "desc": "Transmission angle vs. incidence.", "subtasks": {}, "button_text": "12bi: Transmission Angle"},
    "12bii": {"title": "Task 12bii: Deflection Angle", "desc": "Deflection angle vs. incidence.", "subtasks": {}, "button_text": "12bii: Deflection Angle"},
    "12biii": {"title": "Task 12biii: Deflection vs. Vertex", "desc": "Deflection for various vertex angles.", "subtasks": {}, "button_text": "12biii: Deflection vs. Vertex"}
}


########################################
# MAIN PAGE TEMPLATE
########################################
main_page_template = '''
<!DOCTYPE html>
<html>
<head>
  <title>Physics Optics Challenge Tasks</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f4f6f8; color: #333; line-height: 1.6; }
    .header-banner { display: flex; align-items: center; justify-content: space-between; padding: 10px 20px; background-color: #004080; color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .header-banner img { max-height: 50px; width: auto; border-radius: 4px; }
    .header-banner img.logo { margin-right:15px;}
    .header-banner img.optics-img { margin-left:15px;}
    .header-banner h1 { margin: 0; font-size: 1.6em; font-weight: 500; text-align: center; flex-grow: 1; }
    .container { display: flex; flex-wrap: wrap; justify-content: center; padding: 15px; }
    .button-link {
      background-color: #007bff; color: white; border: none; border-radius: 8px;
      font-size: 1.0em; /* Adjusted font size */ margin: 8px; padding: 15px; /* Adjusted padding */ width: calc(50% - 24px); max-width: 320px;
      text-align: center; text-decoration: none; transition: background-color 0.25s, transform 0.2s;
      box-shadow: 0px 3px 7px rgba(0,0,0,0.12); display: flex; flex-direction: column; justify-content: center; min-height: 60px; /* Adjusted min-height */
    }
    .button-link:hover { background-color: #0056b3; transform: translateY(-3px); box-shadow: 0px 5px 10px rgba(0,0,0,0.15); }
    .button-link .task-title { font-weight: 500; }
    .button-link .task-button-text { font-size: 0.9em; /* Adjusted for potentially longer text */ margin-top: 4px; color: #d0e0ff; display: block; /* Ensure it behaves as a block for wrapping if needed */ }
    .upload-form { margin: 25px auto; padding: 20px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 1px 5px rgba(0,0,0,0.1); text-align: center; max-width: 480px; }
    .upload-button {
      background-color: #28a745; color: white; padding: 10px 20px; border: none;
      border-radius: 6px; font-size: 1em; cursor: pointer; margin-top: 10px; transition: background-color 0.2s;
    }
    .upload-button:hover { background-color: #218838; }
    .credits { text-align: center; margin-top: 25px; padding-bottom: 20px; font-size: 0.9em; color: #555; }
    @media (max-width: 768px) { 
        .button-link { width: calc(100% - 24px); max-width:none; } 
        .header-banner h1 {font-size: 1.3em;} 
        .header-banner img {max-height:35px;}
        .header-banner img.logo { margin-right:10px;}
        .header-banner img.optics-img { margin-left:10px;}
    }
  </style>
</head>
<body>
  <div class="header-banner">
    <img src="{{ url_for('static', filename='bpho_logo.jpg') }}" alt="BPHO Logo" class="logo">
    <h1>Physics Optics Tasks</h1>
    <img src="{{ url_for('static', filename='optics_image_1.jpg') }}" alt="Optics Image" class="optics-img">
  </div>

  <div class="container">
    {% for key, task in tasks_overview.items() %}
      {% if key not in ['1a', '1b', '11a', '11b', '11c', '11d', '12a', '12b', '12bi', '12bii', '12biii'] %}
        <a class="button-link" href="{% if task.subtasks and task.subtasks|length > 0 %}{{ url_for('subtask_page', task_id=key) }}{% else %}{{ url_for('handle_task', task_id=key) }}{% endif %}" title="{{ task.desc }}">
          <!-- <span class="task-title">{{ task.title }}</span> -->
          <span class="task-button-text">{{ task.button_text if task.button_text else task.title }}</span>
        </a>
      {% endif %}
    {% endfor %}
  </div>
  
  <div class="upload-form">
    <form method="POST" action="{{ url_for('upload_file') }}" enctype="multipart/form-data">
      <label for="image_file">Upload Image (reduced to {{ max_dimension }}px side):</label><br>
      <input type="file" name="image_file" id="image_file" accept="image/*" style="margin-top:10px; display:block; margin-left:auto; margin-right:auto;"><br>
      <button type="submit" class="upload-button">Upload and Resize</button>
    </form>
  </div>

  <div class="credits">
    <p>Anango Prabhat, Thales Swanson</p>
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
  <title>{{ parent_task_title }} - Subtasks</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f4f6f8; padding:0; margin:0; color: #333; }
    .container { display: flex; flex-direction: column; align-items: center; padding: 20px; max-width: 700px; margin: 20px auto; background-color: #fff; border-radius: 8px; box-shadow: 0 1px 5px rgba(0,0,0,0.1); }
    h1 { color: #0056b3; text-align: center; font-weight: 500; margin-bottom: 25px; }
    .button-link {
      background-color: #17a2b8; color: white; border: none; border-radius: 8px;
      font-size: 1.0em; margin: 8px; padding: 15px; width: 90%; max-width: 400px;
      text-align: center; text-decoration: none; transition: background-color 0.25s, transform 0.2s;
      box-shadow: 0px 3px 6px rgba(0,0,0,0.1);
    }
    .button-link:hover { background-color: #117a8b; transform: translateY(-2px); }
    .button-link .subtask-title { font-weight: 500; }
    .button-link .subtask-desc { font-size: 0.9em; margin-top: 5px; color: #e0f7fa; display: block; }
    .nav-buttons-footer { margin-top: 30px; text-align: center; padding: 20px 10px; border-top: 1px solid #e0e0e0; }
    .back-button, .small-task-button {
      padding: 9px 16px; border: none; border-radius: 5px; font-size: 0.9em; cursor: pointer; margin: 4px;
      transition: background-color 0.2s ease-in-out; text-decoration: none; display: inline-block;
    }
    .back-button { background-color: #007BFF; color: white; }
    .back-button:hover { background-color: #0056b3; }
    .small-task-button { background-color: #6c757d; color: white; font-size: 0.75em; padding: 7px 12px;}
    .small-task-button:hover { background-color: #545b62; }
  </style>
</head>
<body>
  <div class="container">
    <h1>{{ parent_task_title }}</h1>
    {% for subkey, sub_desc_from_parent in subtasks_for_page.items() %}
      {% set sub_task_def = tasks_overview.get(subkey, {}) %}
      <a class="button-link" href="{% if sub_task_def.subtasks and sub_task_def.subtasks|length > 0 %}{{ url_for('subtask_page', task_id=subkey) }}{% else %}{{ url_for('handle_task', task_id=subkey) }}{% endif %}" title="{{ sub_task_def.desc if sub_task_def else '' }}">
         <span class="subtask-button-text">{{ sub_task_def.button_text if sub_task_def.button_text else (sub_task_def.title if sub_task_def.title else subkey) }}</span>
         <!-- Removed subtask-desc as button_text should now be comprehensive -->
      </a>
    {% endfor %}
  </div>
  <div class="nav-buttons-footer">
    <button class="back-button" onclick="window.location.href='{{ url_for('index') }}'">Back to Home</button>
    {% for key, task_info in tasks_overview.items() %}
        {% if key not in ['1a', '1b', '11a', '11b', '11c', '11d', '12a', '12b', '12bi', '12bii', '12biii'] %}
            {% if task_info.subtasks and task_info.subtasks|length > 0 %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('subtask_page', task_id=key) }}'">{{ task_info.button_text if task_info.button_text else task_info.title }}</button>
            {% else %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('handle_task', task_id=key) }}'">{{ task_info.button_text if task_info.button_text else task_info.title }}</button>
            {% endif %}
        {% endif %}
    {% endfor %}
  </div>
</body>
</html>
'''


########################################
# STATIC PLOT PAGE TEMPLATE
########################################
static_plot_page_template = '''
<!DOCTYPE html>
<html>
<head>
  <title>{{ title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f4f6f8; padding:10px; margin:0; color: #333; }
    .container { max-width: 850px; margin: 20px auto; background-color: #fff; padding: 25px; border-radius: 8px; box-shadow: 0 1px 5px rgba(0,0,0,0.1); }
    h1 { color: #0056b3; text-align: center; font-weight: 500; margin-bottom: 15px; }
    .plot-display { text-align: center; margin: 20px 0; background-color:#fdfdfd; padding:15px; border-radius:6px; border: 1px solid #e7e7e7;}
    .plot-display img { max-width: 100%; height: auto; border-radius: 4px; }
    .description { text-align: center; margin-bottom: 20px; font-style: italic; color: #555; font-size:0.95em; }
    .nav-buttons-footer { margin-top: 30px; text-align: center; padding: 20px 10px; border-top: 1px solid #e0e0e0; }
    .back-button, .small-task-button {
      padding: 9px 16px; border: none; border-radius: 5px; font-size: 0.9em; cursor: pointer; margin: 4px;
      transition: background-color 0.2s ease-in-out; text-decoration: none; display: inline-block;
    }
    .back-button { background-color: #007BFF; color: white; }
    .back-button:hover { background-color: #0056b3; }
    .small-task-button { background-color: #6c757d; color: white; font-size: 0.75em; padding: 7px 12px;}
    .small-task-button:hover { background-color: #545b62; }
  </style>
</head>
<body>
  <div class="container">
    <h1>{{ title }}</h1>
    {% if description %}
      <p class="description">{{ description }}</p>
    {% endif %}
    <div class="plot-display">
      <img src="{{ url_for('plot_task', task_id=task_id_for_plot) }}" alt="{{ title }} Plot">
    </div>
  </div>
  <div class="nav-buttons-footer">
    <button class="back-button" onclick="window.location.href='{{ url_for('index') }}'">Back to Home</button>
     {% for key, task_info in tasks_overview.items() %}
         {% if key not in ['1a', '1b', '11a', '11b', '11c', '11d', '12a', '12b', '12bi', '12bii', '12biii'] %}
            {% if task_info.subtasks and task_info.subtasks|length > 0 %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('subtask_page', task_id=key) }}'">{{ task_info.button_text if task_info.button_text else task_info.title }}</button>
            {% else %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('handle_task', task_id=key) }}'">{{ task_info.button_text if task_info.button_text else task_info.title }}</button>
            {% endif %}
         {% endif %}
     {% endfor %}
  </div>
</body>
</html>
'''

########################################
# ROUTE: Main Page
########################################
@app.route('/')
def index():
    return render_template_string(main_page_template, tasks_overview=task_overview, max_dimension=MAX_DIMENSION)

########################################
# ROUTE: Subtask Page
########################################
@app.route('/subtask/<task_id>')
def subtask_page(task_id):
    parent_task = task_overview.get(task_id)
    if parent_task and parent_task.get("subtasks"):
        return render_template_string(subtask_page_template,
                                      parent_task_title=parent_task["title"],
                                      subtasks_for_page=parent_task["subtasks"], 
                                      tasks_overview=task_overview,
                                      parent_task_id_for_nav=task_id)
    return f"No subtasks defined for task {task_id} or task not found.", 404


########################################
# ROUTE: Handle Task (Static / Interactive)
########################################
@app.route('/task/<task_id>')
def handle_task(task_id):
    if task_id == "7": 
        return redirect(url_for('handle_task', task_id="6"))

    if task_id in interactive_tasks:
        return redirect(url_for('interactive_task_page', task_id=task_id))
    
    elif task_id in static_tasks:
        task_info = task_overview.get(task_id, {"title": f"Task {task_id}", "desc": "Static plot."})
        return render_template_string(static_plot_page_template, 
                                      title=task_info["title"],
                                      description=task_info["desc"],
                                      task_id_for_plot=task_id, 
                                      tasks_overview=task_overview,
                                      current_task_id_for_nav=task_id) 
    elif task_id == "12b": 
        return redirect(url_for('subtask_page', task_id="12b"))
    else:
        return f"Task {task_id} is not defined or has no direct page.", 404

########################################
# ROUTE: Interactive Task Page
########################################
@app.route('/interactive/<task_id>')
def interactive_task_page(task_id):
    if task_id in interactive_tasks:
        config = interactive_tasks[task_id]
        return render_interactive_page(slider_config=config["sliders"],
                                       title=config["title"],
                                       plot_endpoint=config["plot_endpoint"],
                                       task_id_for_template=task_id, 
                                       banned_validation=config.get("banned_validation", False), # This will be true for task 6
                                       extra_context=config.get("extra_context", {}),
                                       playable=config.get("playable", False))
    return f"No interactive configuration for task {task_id}", 404


########################################
# STATIC TASKS PLOT GENERATION
########################################
def generate_task1a_plot():
    def crown_glass(Lambda_nm):
        x_um = Lambda_nm / 1000.0
        a = np.array([1.03961212, 0.231792344, 1.01146945])
        b_um_sq = np.array([0.00600069867, 0.0200179144, 103.560653])
        n_sq_minus_1 = np.zeros_like(x_um)
        for i in range(len(a)):
            n_sq_minus_1 += (a[i] * (x_um**2)) / ((x_um**2) - b_um_sq[i])
        return np.sqrt(1 + n_sq_minus_1)
    Lambda_nm = np.linspace(400, 800, 500)
    RefractiveIndex = crown_glass(Lambda_nm)
    fig = Figure(figsize=(8,5))
    ax = fig.add_subplot(111)
    ax.plot(Lambda_nm, RefractiveIndex)
    ax.set_title("Refractive index of N-BK7 Crown Glass vs Wavelength")
    ax.set_xlabel("Wavelength $\\lambda$ (nm)")
    ax.set_ylabel("Refractive Index (n)")
    ax.grid(True, linestyle=":", alpha=0.6)
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task1b_plot():
    rainbow = [(1,0,0),(1,0.3,0),(1,1,0),(0,1,0),(0,0,1),(0.29,0,0.51),(0.58,0,0.83)]
    colourmap = LinearSegmentedColormap.from_list("colours", rainbow, N=256)
    frequency_THz = np.linspace(405,790,500) 
    n_water = (1 + ((1 / (1.731 - 0.261 * ((frequency_THz / 1000.0)**2)))**0.5))**0.5

    points = np.array([frequency_THz, n_water]).T.reshape(-1,1,2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = LineCollection(segments, cmap=colourmap, linewidth=3)
    lc.set_array(frequency_THz) 
    
    fig = Figure(figsize=(8,5))
    ax = fig.add_subplot(111)
    ax.add_collection(lc)
    ax.set_xlim(frequency_THz.min(), frequency_THz.max())
    ax.set_ylim(n_water.min() - 0.01, n_water.max() + 0.01)
    ax.set_title("Refractive Index of Water vs Frequency")
    ax.set_xlabel("Frequency (THz)")
    ax.set_ylabel("Refractive Index (n)")
    ax.grid(True, linestyle=":", alpha=0.6)
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task2_plot():
    u_cm = np.array([20, 25, 30, 35, 40, 45, 50, 55])
    v_cm = np.array([65.5,40,31,27,25,23.1,21.5,20.5])
    inv_u = 1.0 / u_cm
    inv_v = 1.0 / v_cm

    # Perform linear regression
    m, c = np.polyfit(inv_u, inv_v, 1)

    # Calculate R^2 value
    # 1. Calculate the predicted y values using the linear fit
    inv_v_pred = m * inv_u + c
    # 2. Calculate the sum of squares of residuals (SS_res)
    ss_res = np.sum((inv_v - inv_v_pred)**2)
    # 3. Calculate the total sum of squares (SS_tot)
    ss_tot = np.sum((inv_v - np.mean(inv_v))**2)
    # 4. Calculate R^2
    #   Handle the case where ss_tot is zero to avoid division by zero,
    #   though unlikely with this data. If ss_tot is 0, it means all inv_v are the same.
    if ss_tot == 0:
        r_squared = 1.0 if ss_res == 0 else 0.0 # Perfect fit if ss_res is also 0, otherwise no fit
    else:
        r_squared = 1 - (ss_res / ss_tot)

    fig = Figure(figsize=(8,5))
    ax = fig.add_subplot(111)
    ax.scatter(inv_u, inv_v, color="red", zorder=2, label="Data Points")
    # Update the label for the fit line to include R^2
    ax.plot(inv_u, m * inv_u + c, zorder=1, label=f"Fit: y={m:.3f}x + {c:.3f}\nR² = {r_squared:.4f}")

    f_calc = 1/c if c!=0 else float('inf')
    ax.set_title(f"Thin Lens: 1/v vs 1/u (Calculated f ≈ {f_calc:.2f} cm)")
    ax.set_xlabel("1/u (cm⁻¹)")
    ax.set_ylabel("1/v (cm⁻¹)")
    ax.legend()
    ax.grid(True, linestyle=":", alpha=0.6)

    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task11a_plot():
    Theta_rad = np.linspace(0, pi/2, 500)
    def convert_11a(freq_THz, color_str):
        n = (1+((1/(1.731-0.261*((freq_THz/1000.0)**2)))**0.5))**0.5 
        Epsilon1_sec = pi - 6*np.arcsin(np.sin(Theta_rad)/n) + 2*Theta_rad
        Epsilon2_pri = 4*np.arcsin(np.sin(Theta_rad)/n) - 2*Theta_rad
        
        with np.errstate(invalid='ignore'): 
            Theta_crit_sec = np.arcsin(np.sqrt(np.clip((9-n**2)/8.0,0,1))) if (9-n**2)/8.0 >=0 else np.nan
            Theta_crit_pri = np.arcsin(np.sqrt(np.clip((4-n**2)/3.0,0,1))) if (4-n**2)/3.0 >=0 else np.nan

        SpecialEpsilon1 = pi - 6*np.arcsin(np.sin(Theta_crit_sec)/n) + 2*Theta_crit_sec if not np.isnan(Theta_crit_sec) else np.nan
        SpecialEpsilon2 = 4*np.arcsin(np.sin(Theta_crit_pri)/n) - 2*Theta_crit_pri if not np.isnan(Theta_crit_pri) else np.nan
        
        return {"Epsilon1_sec_deg": np.rad2deg(Epsilon1_sec), "Epsilon2_pri_deg": np.rad2deg(Epsilon2_pri),
                "SpecialEpsilon1_deg": np.rad2deg(SpecialEpsilon1), "SpecialEpsilon2_deg": np.rad2deg(SpecialEpsilon2),
                "color": color_str, "frequency_label": f"{freq_THz} THz"}

    freqs_THz_11a = [442.5,495,520,565,610,650,735]
    colors_map_11a = {"Red":"red", "Orange":"orange", "Yellow":"gold", "Green":"green", "Cyan":"cyan", "Blue":"blue", "Violet":"darkviolet"}
    plot_data_11a = {name: convert_11a(freq, colors_map_11a[name]) for name, freq in zip(colors_map_11a.keys(), freqs_THz_11a)}
    
    fig = Figure(figsize=(10,7))
    ax = fig.add_subplot(111)
    Theta_plot_deg = np.rad2deg(Theta_rad)
    for name, d in plot_data_11a.items():
        ax.plot(Theta_plot_deg, d["Epsilon2_pri_deg"], color=d["color"], lw=1.5, label=f"{name} Primary (ε₁)")
        ax.plot(Theta_plot_deg, d["Epsilon1_sec_deg"], color=d["color"], lw=1.5, ls='--', label=f"{name} Secondary (ε₂)")
        if not np.isnan(d["SpecialEpsilon2_deg"]): ax.axhline(y=d["SpecialEpsilon2_deg"], color=d["color"], alpha=0.8, lw=1)
        if not np.isnan(d["SpecialEpsilon1_deg"]): ax.axhline(y=d["SpecialEpsilon1_deg"], color=d["color"], alpha=0.8, lw=1, ls='--')
    
    ax.set_xlabel("Angle of Incidence θ (degrees)")
    ax.set_ylabel("Angle of Deflection ε (degrees from anti-solar point)")
    ax.set_title("Rainbow Deflection Angles (Descartes' Model)")
    ax.legend(fontsize='small', loc='upper right')
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.set_ylim(0, 180) 
    fig.tight_layout()
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task11b_plot():
    rainbow_cm = [(1,0,0),(1,0.2,0),(1,0.5,0),(1,1,0),(0,1,0),(0,0,1),(0.29,0,0.51),(0.58,0,0.83)]
    colourmap_11b = LinearSegmentedColormap.from_list("colours_11b", rainbow_cm)
    frequency_THz = np.linspace(405,790,500)
    n_water = (1+((1/(1.731-0.261*((frequency_THz/1000.0)**2)))**0.5))**0.5
    
    with np.errstate(invalid='ignore', divide='ignore'):
        Theta_crit_pri = np.arcsin(np.sqrt(np.clip((4-n_water**2)/3.0,0,1)))
        Theta_crit_sec = np.arcsin(np.sqrt(np.clip((9-n_water**2)/8.0,0,1)))
    
    Epsilon_pri_rad = 4*np.arcsin(np.sin(Theta_crit_pri)/n_water)-2*Theta_crit_pri
    Epsilon_sec_rad = np.pi-6*np.arcsin(np.sin(Theta_crit_sec)/n_water)+2*Theta_crit_sec
    Epsilon_pri_deg = np.rad2deg(Epsilon_pri_rad)
    Epsilon_sec_deg = np.rad2deg(Epsilon_sec_rad)

    points_pri = np.array([frequency_THz, Epsilon_pri_deg]).T.reshape(-1,1,2)
    segments_pri = np.concatenate([points_pri[:-1], points_pri[1:]], axis=1)
    lc_pri = LineCollection(segments_pri, cmap=colourmap_11b, linewidth=3)
    lc_pri.set_array(frequency_THz)
    points_sec = np.array([frequency_THz, Epsilon_sec_deg]).T.reshape(-1,1,2)
    segments_sec = np.concatenate([points_sec[:-1], points_sec[1:]], axis=1)
    lc_sec = LineCollection(segments_sec, cmap=colourmap_11b, linewidth=3) 
    lc_sec.set_array(frequency_THz) 
    
    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    ax.add_collection(lc_pri)
    ax.add_collection(lc_sec)
    ax.set_xlim(frequency_THz.min(),frequency_THz.max())
    ax.set_ylim(min(np.nanmin(Epsilon_pri_deg)-2 if not np.all(np.isnan(Epsilon_pri_deg)) else 40, 
                    np.nanmin(Epsilon_sec_deg)-2 if not np.all(np.isnan(Epsilon_sec_deg)) else 50), 
                max(np.nanmax(Epsilon_pri_deg)+2 if not np.all(np.isnan(Epsilon_pri_deg)) else 45, 
                    np.nanmax(Epsilon_sec_deg)+2 if not np.all(np.isnan(Epsilon_sec_deg)) else 55))
    ax.set_title("Elevation of Primary and Secondary Rainbows")
    ax.set_xlabel("Frequency (THz)")
    ax.set_ylabel("Elevation Angle ε (degrees)")
    ax.grid(True, linestyle=":", alpha=0.8)
    fig.tight_layout()
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task11c_plot():
    frequency_THz = np.linspace(405,790,80)
    n_water = (1+((1/(1.731-0.261*((frequency_THz/1000.0)**2)))**0.5))**0.5
    
    with np.errstate(invalid='ignore', divide='ignore'):
        Theta_crit_pri = np.arcsin(np.sqrt(np.clip((4-n_water**2)/3.0,0,1))) 
        Theta_crit_sec = np.arcsin(np.sqrt(np.clip((9-n_water**2)/8.0,0,1))) 
    
    Phi_pri_rad = np.arcsin(np.sin(Theta_crit_pri)/n_water)
    Phi_sec_rad = np.arcsin(np.sin(Theta_crit_sec)/n_water)
    Phi_tir_limit_rad = np.arcsin(1.0/n_water) 
    
    Phi_pri_deg = np.rad2deg(Phi_pri_rad)
    Phi_sec_deg = np.rad2deg(Phi_sec_rad)
    Phi_tir_limit_deg = np.rad2deg(Phi_tir_limit_rad)
    
    colors_list_11c = []
    for f_thz in frequency_THz:
        if f_thz < 475: colors_list_11c.append("red")
        elif f_thz < 510: colors_list_11c.append("orange")
        elif f_thz < 530: colors_list_11c.append("gold")
        elif f_thz < 600: colors_list_11c.append("green")
        elif f_thz < 620: colors_list_11c.append("cyan")
        elif f_thz < 675: colors_list_11c.append("blue")
        else: colors_list_11c.append("darkviolet")
        
    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    ax.scatter(frequency_THz, Phi_pri_deg, c=colors_list_11c, s=15, label="φ for Primary Rainbow Min. Deviation")
    ax.plot(frequency_THz, Phi_pri_deg, color="cornflowerblue", alpha=0.7)
    ax.scatter(frequency_THz, Phi_sec_deg, c=colors_list_11c, s=15, marker='x', label="φ for Secondary Rainbow Min. Deviation")
    ax.plot(frequency_THz, Phi_sec_deg, color="lightcoral", alpha=0.7, linestyle='--')
    ax.plot(frequency_THz, Phi_tir_limit_deg, color="black", linestyle=':', label="Critical Angle φ_c (TIR limit)")
    
    ax.set_title("Refraction Angle φ at Min. Deviation vs. Frequency")
    ax.set_xlabel("Frequency (THz)")
    ax.set_ylabel("Refraction Angle φ (degrees)")
    ax.legend(fontsize='small')
    ax.grid(True, alpha=0.8, linestyle=":")
    fig.tight_layout()
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task12bi_plot(): 
    frequency_val = 542.5e12
    wavelength_val = 3e8 / frequency_val
    alpha_val = np.pi/4 
    ThetaI_rad = np.linspace(0, np.pi/2, 500) 
    n = get_refractive_index_sellmeier(np.array([wavelength_val]))[0]
    
    sin_e_arg = np.sqrt(np.maximum(0, n**2 - np.sin(ThetaI_rad)**2)) * np.sin(alpha_val) - np.sin(ThetaI_rad) * np.cos(alpha_val)
    e_rad = np.arcsin(np.clip(sin_e_arg, -1, 1)) 
    
    valid_mask = ~np.isnan(e_rad) & (np.abs(sin_e_arg) <= 1.0) 
    ThetaI_deg_valid = np.rad2deg(ThetaI_rad[valid_mask])
    e_deg_valid = np.rad2deg(e_rad[valid_mask])
    
    ThetaMax_deg = 0
    if len(e_deg_valid) > 0:
        grazing_indices = np.where(np.isclose(np.abs(e_deg_valid), 90, atol=1.0))[0]
        if len(grazing_indices) > 0:
             ThetaMax_deg = ThetaI_deg_valid[grazing_indices[0]] 

    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    if len(ThetaI_deg_valid)>0:
        ax.plot(ThetaI_deg_valid, e_deg_valid, label=f"n ≈ {n:.3f}")
    ax.set_xlabel("Angle of Incidence on First Face (degrees)")
    ax.set_ylabel("Angle of Emergence from Second Face (degrees)")
    title = f"Task 12bi: Emergence Angle vs. Incidence (Apex α={degrees(alpha_val):.0f}°)"
    if ThetaMax_deg > 0:
        ax.axvline(x=ThetaMax_deg, color='r', linestyle='--', alpha=0.7, label=f"Limit for Emergence ≈ {ThetaMax_deg:.1f}°")
        ax.legend(fontsize='small')
    ax.set_title(title)
    ax.grid(True, linestyle=":", alpha=0.8)
    ax.set_ylim(-95, 95)
    fig.tight_layout()
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task12bii_plot(): 
    frequency_val = 542.5e12
    wavelength_val = 3e8 / frequency_val
    alpha_val = np.pi/4 
    ThetaI_rad = np.linspace(0, np.pi/2, 500) 
    n = get_refractive_index_sellmeier(np.array([wavelength_val]))[0]

    sin_e_arg = np.sqrt(np.maximum(0, n**2 - np.sin(ThetaI_rad)**2)) * np.sin(alpha_val) - np.sin(ThetaI_rad) * np.cos(alpha_val)
    e_rad = np.arcsin(np.clip(sin_e_arg, -1, 1)) 
    delta_rad = ThetaI_rad + e_rad - alpha_val 

    valid_mask = ~np.isnan(e_rad) & (np.abs(sin_e_arg) <= 1.0)
    ThetaI_deg_valid = np.rad2deg(ThetaI_rad[valid_mask])
    delta_deg_valid = np.rad2deg(delta_rad[valid_mask])
    e_deg_valid = np.rad2deg(e_rad[valid_mask]) # Need this to find ThetaMax_deg

    ThetaMax_deg, min_delta_deg, ThetaI_min_delta_deg = 0, np.nan, np.nan # Initialize with nan
    if len(delta_deg_valid) > 0:
        # Find limit for emergence based on e_deg_valid
        grazing_indices = np.where(np.isclose(np.abs(e_deg_valid), 90, atol=1.0))[0]
        if len(grazing_indices) > 0: ThetaMax_deg = ThetaI_deg_valid[grazing_indices[0]]
        
        # Find minimum deviation only within the valid emergence range
        valid_delta_indices = np.where(~np.isnan(delta_deg_valid))[0]
        if len(valid_delta_indices) > 0:
            min_delta_idx_local = np.nanargmin(delta_deg_valid[valid_delta_indices])
            min_delta_idx_global = valid_delta_indices[min_delta_idx_local]
            min_delta_deg = delta_deg_valid[min_delta_idx_global]
            ThetaI_min_delta_deg = ThetaI_deg_valid[min_delta_idx_global]

    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    if len(ThetaI_deg_valid) > 0:
        ax.plot(ThetaI_deg_valid, delta_deg_valid, label=f"n ≈ {n:.3f}")
    ax.set_xlabel("Angle of Incidence on First Face (degrees)")
    ax.set_ylabel("Angle of Deviation (degrees)")
    title = f"Task 12bii: Deviation vs. Incidence (Apex α={degrees(alpha_val):.0f}°)"
    legend_items = []
    if ThetaMax_deg > 0 :
        ax.axvline(x=ThetaMax_deg, color='r', linestyle='--', alpha=0.7)
        legend_items.append(plt.Line2D([0], [0], color='r', linestyle='--', label=f"Limit for Emergence ≈ {ThetaMax_deg:.1f}°"))
    if not np.isnan(min_delta_deg):
        ax.scatter(ThetaI_min_delta_deg, min_delta_deg, color='g', zorder=5, s=40)
        legend_items.append(plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='g', markersize=7, label=f"Min. Deviation ≈ {min_delta_deg:.1f}°"))
    
    if legend_items:
        ax.legend(handles=legend_items, fontsize='small')
    ax.set_title(title)
    ax.grid(True, linestyle=":", alpha=0.8)
    fig.tight_layout()
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

def generate_task12biii_plot(): 
    frequency_val = 542.5e12
    wavelength_val = 3e8 / frequency_val
    ThetaI_rad = np.linspace(np.deg2rad(0.1), np.pi/2 - np.deg2rad(0.1), 300) 
    n = get_refractive_index_sellmeier(np.array([wavelength_val]))[0]

    fig = Figure(figsize=(10, 7))
    ax = fig.add_subplot(111)
    colors_12biii = plt.cm.viridis(np.linspace(0.1, 0.9, 15))

    min_overall_delta = float('inf')
    max_overall_delta = float('-inf')

    for i, alpha_deg_val in enumerate(range(10, 81, 5)):
        alpha_rad_val = np.deg2rad(alpha_deg_val)
        
        sin_e_arg = np.sqrt(np.maximum(0,n**2 - np.sin(ThetaI_rad)**2)) * np.sin(alpha_rad_val) - np.sin(ThetaI_rad) * np.cos(alpha_rad_val)
        with np.errstate(invalid='ignore'): 
            e_rad = np.arcsin(np.clip(sin_e_arg, -1.0, 1.0))
        delta_rad = ThetaI_rad + e_rad - alpha_rad_val
        
        valid_mask = ~np.isnan(e_rad) & (np.abs(sin_e_arg) <= 1.0)
        ThetaI_plot_deg = np.rad2deg(ThetaI_rad[valid_mask])
        delta_plot_deg = np.rad2deg(delta_rad[valid_mask])
        
        if len(ThetaI_plot_deg) > 0:
            ax.plot(ThetaI_plot_deg, delta_plot_deg, color=colors_12biii[i], label=f'{alpha_deg_val}°')
            if len(delta_plot_deg) > 0:
                 min_overall_delta = min(min_overall_delta, np.nanmin(delta_plot_deg))
                 max_overall_delta = max(max_overall_delta, np.nanmax(delta_plot_deg))

    ax.set_xlabel("Angle of Incidence on First Face (degrees)")
    ax.set_ylabel("Angle of Deviation (degrees)")
    ax.set_title(f"Task 12biii: Deviation vs. Incidence for Various Apex Angles (n ≈ {n:.3f})")
    ax.legend(title="Apex Angle α", bbox_to_anchor=(1.02, 1), loc='upper left', fontsize='small')
    ax.grid(True, linestyle=":", alpha=0.8)
    
    current_bottom, current_top = ax.get_ylim()
    new_bottom = min(current_bottom, min_overall_delta if min_overall_delta != float('inf') else 0)
    new_top = max(current_top, max_overall_delta if max_overall_delta != float('-inf') else 80)
    ax.set_ylim(bottom=new_bottom - 5, top=new_top + 5) # Add some padding

    fig.tight_layout(rect=[0, 0, 0.83, 1]) 
    buf = io.BytesIO()
    FigureCanvas(fig).print_png(buf)
    buf.seek(0)
    return buf

########################################
# INTERACTIVE TASKS PLOT FUNCTIONS
########################################
def generate_task3_plot(v_log, n_val, y_val, l_val, request_id): 
    try:
        check_interrupt("3", request_id)
        v_actual = 10 ** v_log  
        x = np.linspace(0, l_val, 300) 
        with np.errstate(divide='ignore', invalid='ignore'):
            t = np.sqrt(x**2 + y_val**2) / (v_actual / n_val) + np.sqrt((l_val - x)**2 + y_val**2) / (v_actual / n_val)
        
        fig = Figure(figsize=(8,5))
        ax = fig.add_subplot(111)
        if len(x)>0 and not np.all(np.isnan(t)) :
            idx = np.nanargmin(t)
            ax.scatter(x[idx], t[idx], color="red", zorder=5, s=30)
            ax.plot(x, t, zorder=1, color='dodgerblue')
            ax.set_title(f"Min. Time at x = {x[idx]:.3g} m (l/2 = {l_val/2:.3g} m)")
        else:
            ax.set_title("Plot error or no valid data.")
        ax.set_xlabel("Reflection Point x (m)")
        ax.set_ylabel("Total Travel Time t (s)")
        ax.grid(True, linestyle=":", alpha=0.6)
        fig.tight_layout()
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Task 3 plot error: {e}", exc_info=True)
        return generate_blank_image()

def generate_task4_plot(v_log, n1_val, n2_val, y_val, l_val, request_id):
    try:
        check_interrupt("4", request_id)
        v_actual = 10 ** v_log
        x = np.linspace(0.001, l_val-0.001, 300) 
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (np.sqrt(x**2 + y_val**2) / (v_actual / n1_val)) + \
                (np.sqrt((l_val - x)**2 + y_val**2) / (v_actual / n2_val))
        
        fig = Figure(figsize=(8,5))
        ax = fig.add_subplot(111)

        if len(x)>0 and not np.all(np.isnan(t)):
            idx = np.nanargmin(t)
            x_min = x[idx]
            theta1 = np.arctan(x_min / y_val) if y_val != 0 else (np.pi/2 if x_min > 0 else 0)
            theta2 = np.arctan((l_val - x_min) / y_val) if y_val != 0 else (np.pi/2 if (l_val-x_min)>0 else 0)
            
            term1_snell = n1_val * np.sin(theta1)
            term2_snell = n2_val * np.sin(theta2)
            title_text = (f"Min. Time at x={x_min:.3g}m.  $n_1\\sin\\theta_1 \\approx {term1_snell:.3g}$, $n_2\\sin\\theta_2 \\approx {term2_snell:.3g}$")

            ax.scatter(x_min, t[idx], color="red", zorder=5, s=30)
            ax.plot(x, t, zorder=1, color='dodgerblue')
            ax.set_title(title_text)
        else:
            ax.set_title("Plot error or no valid data.")
            
        ax.set_xlabel("Boundary Crossing Point x (m)")
        ax.set_ylabel("Total Travel Time t (s)")
        ax.grid(True, linestyle=":", alpha=0.6)
        fig.tight_layout()
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Task 4 plot error: {e}", exc_info=True)
        return generate_blank_image()

def generate_task5_plot(offset_x_slider, offset_y_from_slider, canvas_size_val, request_id):
    global global_image_rgba, img_height, img_width
    try:
        check_interrupt("5", request_id)
        if global_image_rgba is None or img_height == 0 or img_width == 0: 
            logging.warning("Task 5: Global image not available.")
            return generate_blank_image()

        S = int(canvas_size_val)
        H_img, W_img = img_height, img_width
        
        # Apply slider reversal for Y offset
        effective_offset_y = -offset_y_from_slider
        
        fig = Figure(figsize=(7, 7)) 
        ax = fig.add_subplot(111)
        
        canvas_array = np.ones((S, S, 4), dtype=np.float32) 

        obj_plot_left_x = S/2 + offset_x_slider
        # Object's center Y on plot: S/2 + effective_offset_y
        # Object's bottom Y on plot: (S/2 + effective_offset_y) - H_img / 2.0
        obj_plot_bottom_y = (S/2 + effective_offset_y) - H_img / 2.0
        
        img_plot_left_x = (S/2 - offset_x_slider) - W_img # Image is flipped horizontally
        img_plot_bottom_y = obj_plot_bottom_y 

        for r_img_disp in range(H_img): # Iterate through display rows of object (0=top)
            if r_img_disp % 20 == 0: check_interrupt("5", request_id)
            # To fix object inversion: read from bottom of source image for top of display
            r_img_src = H_img - 1 - r_img_disp 
            for c_img in range(W_img): 
                color_rgba = global_image_rgba[r_img_src, c_img]
                
                # Object pixel target on canvas array
                canvas_c_obj = int(obj_plot_left_x + c_img)
                # y-coordinate of this pixel on the plot (origin bottom):
                # obj_plot_bottom_y is the bottom of the object.
                # (H_img - 1 - r_img_disp) is the y-offset from the bottom of the displayed object.
                plot_y_pixel = obj_plot_bottom_y + (H_img - 1 - r_img_disp)
                canvas_r_obj = int(S - 1 - plot_y_pixel)

                if 0 <= canvas_r_obj < S and 0 <= canvas_c_obj < S:
                    canvas_array[canvas_r_obj, canvas_c_obj] = color_rgba
                
                # Image pixel target on canvas array (image is also inverted like object)
                canvas_c_img = int(img_plot_left_x + (W_img - 1 - c_img)) # Flipped horizontally for mirror image
                canvas_r_img = canvas_r_obj 

                if 0 <= canvas_r_img < S and 0 <= canvas_c_img < S:
                    canvas_array[canvas_r_img, canvas_c_img] = color_rgba
        
        ax.imshow(canvas_array, extent=[0, S, 0, S], origin='lower', interpolation='nearest')
        ax.axvline(x=S / 2, color="black", linestyle="--", lw=1.0, label="Mirror")
        
        ax.set_xlim(0, S)
        ax.set_ylim(0, S)
        
        num_ticks = 5
        x_ticks = np.linspace(0, S, num_ticks)
        y_ticks = np.linspace(0, S, num_ticks)
        x_tick_labels = [f"{val - S/2:.0f}" for val in x_ticks]
        y_tick_labels = [f"{val - S/2:.0f}" for val in y_ticks] # Positive Y is up
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_tick_labels)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_tick_labels)

        ax.set_title(f"Object X from Mirror: {offset_x_slider:.0f}px, Object Y (effective): {effective_offset_y:.0f}px")
        ax.set_xlabel("X relative to Mirror (px)")
        ax.set_ylabel("Y relative to Centerline (px)")
        ax.legend(fontsize='small', loc='upper right')
        fig.tight_layout()
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Task 5 plot error: {e}", exc_info=True)
        return generate_blank_image()

def generate_task6_plot(start_x_obj_dist, start_y_obj_from_slider, scale_val, f_val_lens, request_id):
    global global_image_rgba, img_height, img_width
    try:
        check_interrupt("6", request_id)
        if global_image_rgba is None or img_height == 0 or img_width == 0:
            return generate_blank_image()

        H_img, W_img = img_height, img_width
        num_channels_on_canvas = 4 

        # Apply slider reversal for Y offset
        effective_start_y_obj = -start_y_obj_from_slider

        diag_obj = np.sqrt(W_img**2 + H_img**2)
        canvas_dim_heuristic = max(diag_obj * scale_val, abs(f_val_lens) * 4, abs(start_x_obj_dist)*2) * 1.5
        canvas_height = int(canvas_dim_heuristic)
        canvas_width = int(canvas_dim_heuristic * 1.2) 
        canvas_height = max(canvas_height, 120) 
        canvas_width = max(canvas_width, 120)  

        plot_canvas = np.ones((canvas_height, canvas_width, num_channels_on_canvas), dtype=np.float32) 

        drawn_image_pixel_cols = []
        drawn_image_pixel_rows = []

        for r_img_disp in range(H_img): # Iterate through display rows of object (0=top)
            if r_img_disp % 10 == 0: check_interrupt("6", request_id)
            r_img_src = H_img - 1 - r_img_disp # To fix object inversion: read from bottom of source for top of display
            
            for c_img in range(W_img): 
                color = global_image_rgba[r_img_src, c_img]

                # Object pixel's x-coordinate relative to lens (u for this column of pixels)
                # start_x_obj_dist is distance of object's left edge from lens.
                # c_img is column index from left of object.
                x_o_pixel_dist_from_lens = start_x_obj_dist + c_img 
                
                # Object pixel's y-coordinate relative to optical axis
                # y_pix_offset_from_obj_center: (H_img-1)/2.0 is center row index. r_img_disp is current display row.
                # (positive up from object's center)
                y_pix_offset_from_obj_center = ((H_img - 1.0) / 2.0) - r_img_disp
                y_o_pixel_rel_axis = effective_start_y_obj + y_pix_offset_from_obj_center

                # Draw object pixel
                canv_c_obj = int(canvas_width/2 - x_o_pixel_dist_from_lens) # Object is to the left of lens (negative x in plot coords)
                canv_r_obj = int(canvas_height/2 - y_o_pixel_rel_axis) # Y flip for array
                if 0 <= canv_r_obj < canvas_height and 0 <= canv_c_obj < canvas_width:
                    plot_canvas[canv_r_obj, canv_c_obj] = color

                # Image formation
                u_dist_pixel = x_o_pixel_dist_from_lens # u is positive if object left of lens

                if abs(u_dist_pixel - f_val_lens) < 1e-9 or abs(f_val_lens) < 1e-9 or abs(u_dist_pixel) < 1e-9:
                    v_dist_pixel = float('inf')
                    magnification = 1 
                else:
                    v_dist_pixel = (u_dist_pixel * f_val_lens) / (u_dist_pixel - f_val_lens)
                    magnification = -v_dist_pixel / u_dist_pixel # magnification for height

                if v_dist_pixel != float('inf'):
                    x_i_pixel_rel_lens = v_dist_pixel # v is positive if image right of lens
                    y_i_pixel_rel_axis = y_o_pixel_rel_axis * magnification

                    canv_c_img = int(canvas_width/2 + x_i_pixel_rel_lens) # Image x-coord on canvas
                    canv_r_img = int(canvas_height/2 - y_i_pixel_rel_axis) # Y flip for array

                    if 0 <= canv_r_img < canvas_height and 0 <= canv_c_img < canvas_width:
                        plot_canvas[canv_r_img, canv_c_img] = color
                        drawn_image_pixel_cols.append(canv_c_img)
                        drawn_image_pixel_rows.append(canv_r_img)
        
        # Interpolation (same as before)
        def fix_row_on_canvas(current_canvas, row_idx, left_bound, right_bound, channels_count):
            if not (0 <= row_idx < current_canvas.shape[0] and 0 <= left_bound <= right_bound < current_canvas.shape[1] and left_bound < right_bound): return
            cols_to_interpolate = np.arange(left_bound, right_bound + 1)
            row_data_slice = current_canvas[row_idx, left_bound:right_bound + 1]
            is_pixel_background = np.all(np.isclose(row_data_slice, 1.0), axis=1)
            non_background_mask = ~is_pixel_background
            if non_background_mask.sum() < 2: return
            filled_cols_in_slice = cols_to_interpolate[non_background_mask]
            if filled_cols_in_slice.size < 2 or filled_cols_in_slice[0] == filled_cols_in_slice[-1]: return
            interpolation_target_cols = np.arange(filled_cols_in_slice[0], filled_cols_in_slice[-1] + 1)
            for ch_idx in range(channels_count):
                xp_known = filled_cols_in_slice
                fp_known = row_data_slice[non_background_mask, ch_idx]
                interpolated_channel_data = np.interp(interpolation_target_cols, xp_known, fp_known)
                current_canvas[row_idx, interpolation_target_cols, ch_idx] = interpolated_channel_data

        def fix_col_on_canvas(current_canvas, col_idx, top_bound, bottom_bound, channels_count):
            if not (0 <= col_idx < current_canvas.shape[1] and 0 <= top_bound <= bottom_bound < current_canvas.shape[0] and top_bound < bottom_bound): return
            rows_to_interpolate = np.arange(top_bound, bottom_bound + 1)
            col_data_slice = current_canvas[top_bound:bottom_bound + 1, col_idx]
            is_pixel_background = np.all(np.isclose(col_data_slice, 1.0), axis=1)
            non_background_mask = ~is_pixel_background
            if non_background_mask.sum() < 2: return
            filled_rows_in_slice = rows_to_interpolate[non_background_mask]
            if filled_rows_in_slice.size < 2 or filled_rows_in_slice[0] == filled_rows_in_slice[-1]: return
            interpolation_target_rows = np.arange(filled_rows_in_slice[0], filled_rows_in_slice[-1] + 1)
            for ch_idx in range(channels_count):
                xp_known = filled_rows_in_slice
                fp_known = col_data_slice[non_background_mask, ch_idx]
                interpolated_channel_data = np.interp(interpolation_target_rows, xp_known, fp_known)
                current_canvas[interpolation_target_rows, col_idx, ch_idx] = interpolated_channel_data

        if drawn_image_pixel_cols and drawn_image_pixel_rows:
            min_img_c_bound = max(0, int(min(drawn_image_pixel_cols)))
            max_img_c_bound = min(canvas_width - 1, int(max(drawn_image_pixel_cols)))
            min_img_r_bound = max(0, int(min(drawn_image_pixel_rows)))
            max_img_r_bound = min(canvas_height - 1, int(max(drawn_image_pixel_rows)))
            if max_img_c_bound > min_img_c_bound and max_img_r_bound > min_img_r_bound:
                for c_interpolate_idx in range(min_img_c_bound, max_img_c_bound + 1):
                    if (c_interpolate_idx - min_img_c_bound) % 20 == 0: check_interrupt("6", request_id)
                    fix_col_on_canvas(plot_canvas, c_interpolate_idx, min_img_r_bound, max_img_r_bound, num_channels_on_canvas)
                for r_interpolate_idx in range(min_img_r_bound, max_img_r_bound + 1):
                    if (r_interpolate_idx - min_img_r_bound) % 20 == 0: check_interrupt("6", request_id)
                    fix_row_on_canvas(plot_canvas, r_interpolate_idx, min_img_c_bound, max_img_c_bound, num_channels_on_canvas)
        
        plot_canvas = np.clip(plot_canvas, 0.0, 1.0)
        
        fig = Figure(figsize=(8,6)) 
        ax = fig.add_subplot(111)
        plot_xmin, plot_xmax = -canvas_width/2, canvas_width/2
        plot_ymin, plot_ymax = -canvas_height/2, canvas_height/2
        ax.imshow(plot_canvas, extent=[plot_xmin, plot_xmax, plot_ymin, plot_ymax], aspect='auto', origin='lower', interpolation='nearest')
        ax.axvline(x=0, color="blue", linestyle="--", lw=1, label="Lens Plane")
        ax.scatter([f_val_lens, -f_val_lens], [0, 0], color="red", marker="x", s=50, label=f"Foci (f={f_val_lens:.0f})", zorder=5)
        ax.set_xlim(plot_xmin, plot_xmax)
        ax.set_ylim(plot_ymin, plot_ymax)
        ax.set_title(f"Converging Lens: Obj Left X={start_x_obj_dist:.0f}, Obj Y Ctr (eff)={effective_start_y_obj:.0f}")
        ax.set_xlabel("X from Lens (px)")
        ax.set_ylabel("Y from Optical Axis (px)")
        ax.legend(fontsize='small', loc='upper right')
        ax.grid(True, linestyle=":", alpha=0.8)
        fig.tight_layout()
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf) 
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Task 6 plot error: {e}", exc_info=True)
        return generate_blank_image() 



import numpy as np

def transform_points_spherical_aberration_t8_thales(x_o_flat, y_o_flat, R_mirror):
    """
    Calculates image coordinates for object points formed by a spherical mirror,
    using the Thales derivation for the general off-axis case.
    The coordinate system origin is the Center of Curvature (C) of the mirror.

    Args:
        x_o_flat (np.ndarray): Flattened array of object x-coordinates.
        y_o_flat (np.ndarray): Flattened array of object y-coordinates.
        R_mirror (float): Radius of curvature of the spherical mirror.

    Returns:
        tuple[np.ndarray, np.ndarray]: Flattened arrays of image x and y coordinates.
    """
    x_i_flat = np.full_like(x_o_flat, np.nan)
    y_i_flat = np.full_like(y_o_flat, np.nan)

    # Case 1: Mirror radius is negligible
    if R_mirror <= 1e-9: # Increased tolerance slightly for safety
        return x_i_flat, y_i_flat

    # Case 2: Object at the Center of Curvature (C)
    # For these points, the image is also at C.
    at_C_mask = np.isclose(x_o_flat, 0) & np.isclose(y_o_flat, 0)
    x_i_flat[at_C_mask] = 0
    y_i_flat[at_C_mask] = 0
    
    # Case 3: Object on the optical axis (x-axis), but not at C
    # Use the exact formula for on-axis points relative to C: xi = -xo*R / (R + 2*xo)
    on_axis_mask = ~at_C_mask & np.isclose(y_o_flat, 0)
    if np.any(on_axis_mask):
        x_o_ax = x_o_flat[on_axis_mask]
        # Denominator for the on-axis formula
        den_ax = R_mirror + 2 * x_o_ax 
        x_i_ax = np.full_like(x_o_ax, np.nan)
        # Avoid division by zero if object is at -R/2 from C (image at infinity)
        safe_ax_den_mask = ~np.isclose(den_ax, 0)
        x_i_ax[safe_ax_den_mask] = -x_o_ax[safe_ax_den_mask] * R_mirror / den_ax[safe_ax_den_mask]
        
        x_i_flat[on_axis_mask] = x_i_ax
        y_i_flat[on_axis_mask] = 0 # Image is also on the axis

    # Case 4: General off-axis object points (not at C, not on x-axis)
    general_mask = ~at_C_mask & ~on_axis_mask
    if np.any(general_mask):
        # Extract relevant object points
        a = x_o_flat[general_mask] # user's 'a'
        b = y_o_flat[general_mask] # user's 'b'
        
        # Initialize image coordinates for this general case
        x_i_gen = np.full_like(a, np.nan)
        y_i_gen = np.full_like(b, np.nan)

        # --- Calculations for Line 1 (Reflected Ray) ---
        # Point of incidence P_m = (x_P, y_P) on mirror x^2+y^2=R^2 for parallel ray at height b
        # x_P = -sqrt(R^2 - b^2)
        sqrt_arg_R_b_sq = R_mirror**2 - b**2
        
        # Mask for valid incidence points (ray must hit the mirror, i.e., |b| <= R)
        # And sqrt_arg must be non-negative
        valid_incidence_mask = (sqrt_arg_R_b_sq >= -1e-9) # Allow small negative due to precision
        
        if np.any(valid_incidence_mask):
            a_v = a[valid_incidence_mask]
            b_v = b[valid_incidence_mask]
            sqrt_arg_v = np.maximum(0, sqrt_arg_R_b_sq[valid_incidence_mask]) # Ensure non-negative
            
            # x_P for valid points
            x_P_v = -np.sqrt(sqrt_arg_v) # This is -\sqrt{R^2-b^2}
            
            # Calculate m_param (user's 'm')
            # m_param = (2*b*sqrt(R^2-b^2)) / (R^2 - 2*b^2)
            numerator_m = 2 * b_v * x_P_v # Note: x_P_v is negative, so this is -2*b*sqrt(...)
            numerator_m = -numerator_m # To match (2*b*sqrt(R^2-b^2))
            
            denominator_m = R_mirror**2 - 2 * b_v**2
            
            m_param = np.full_like(a_v, np.nan)
            
            # Handle cases for m_param calculation
            # Case 4a: Reflected ray is vertical (denominator_m is zero)
            vertical_refl_mask = np.isclose(denominator_m, 0)
            if np.any(vertical_refl_mask):
                # Line 1 is x = x_P_v
                x_i_vert_refl = x_P_v[vertical_refl_mask]
                # Line 2 is y = (b_v/a_v)*x.
                # If a_v[vertical_refl_mask] is also zero, object is on y-axis.
                # Line 2 becomes x=0. If x_P_v is not 0, parallel vertical lines -> NaN (already init)
                # If x_P_v is 0, then b_v must be R, den_m = -R^2 !=0 (contradiction, so x_P_v !=0 if den_m=0)
                
                # Avoid division by zero for a_v
                a_v_vert_refl = a_v[vertical_refl_mask]
                b_v_vert_refl = b_v[vertical_refl_mask]
                
                y_i_vert_refl_temp = np.full_like(a_v_vert_refl, np.nan)
                
                # If object is on y-axis (a_v_vert_refl is zero)
                obj_on_y_axis_vert_mask = np.isclose(a_v_vert_refl, 0)
                # If Line 1 (x=x_P) and Line 2 (x=0) are different and vertical, image at infinity (NaN)
                # This is implicitly handled as x_i_vert_refl is x_P, and if a_v is 0, y_i remains NaN unless x_P is also 0.
                # But x_P cannot be 0 if denominator_m is 0 (unless R=0, handled).
                # So if a_v is 0 and den_m is 0, lines are x=x_P and x=0 (parallel, distinct). Image is NaN.
                
                # If object is not on y-axis (a_v_vert_refl is not zero)
                obj_not_on_y_axis_vert_mask = ~obj_on_y_axis_vert_mask
                if np.any(obj_not_on_y_axis_vert_mask):
                    y_i_vert_refl_temp[obj_not_on_y_axis_vert_mask] = \
                        (b_v_vert_refl[obj_not_on_y_axis_vert_mask] / a_v_vert_refl[obj_not_on_y_axis_vert_mask]) * \
                        x_i_vert_refl[obj_not_on_y_axis_vert_mask]

                # Temporary arrays to store results for this sub-mask
                x_i_gen_v_temp = np.full_like(a_v, np.nan)
                y_i_gen_v_temp = np.full_like(b_v, np.nan)
                
                x_i_gen_v_temp[vertical_refl_mask] = x_i_vert_refl
                y_i_gen_v_temp[vertical_refl_mask] = y_i_vert_refl_temp


            # Case 4b: Reflected ray is not vertical
            non_vertical_refl_mask = ~vertical_refl_mask
            if np.any(non_vertical_refl_mask):
                m_param_nv = numerator_m[non_vertical_refl_mask] / denominator_m[non_vertical_refl_mask]
                
                a_v_nv = a_v[non_vertical_refl_mask]
                b_v_nv = b_v[non_vertical_refl_mask]
                x_P_v_nv = x_P_v[non_vertical_refl_mask]
                sqrt_term_nv = np.sqrt(np.maximum(0, R_mirror**2 - b_v_nv**2)) # Safe sqrt

                # Denominator for x_i: m_param + b/a
                # Handle a_v_nv == 0 (object on y-axis) separately for m_param + b/a
                den_xi = np.full_like(a_v_nv, np.nan)
                
                # Subcase: Object on y-axis (a_v_nv is zero)
                obj_on_y_mask_nv = np.isclose(a_v_nv, 0)
                if np.any(obj_on_y_mask_nv):
                    # Line 2 is x=0, so x_i = 0
                    # y_i from Line 1: y_i = b - m_param * sqrt(R^2-b^2) (using user's formula for line1 and x=0)
                    # User's line1: y - b = -m(x - x_P) => y = b - m(x - x_P)
                    # if x=0, y = b - m(-x_P) = b + m*x_P
                    # m is m_param_nv[obj_on_y_mask_nv]
                    # x_P is x_P_v_nv[obj_on_y_mask_nv]
                    if 'x_i_gen_v_temp' not in locals(): # Initialize if not created by vertical case
                        x_i_gen_v_temp = np.full_like(a_v, np.nan)
                        y_i_gen_v_temp = np.full_like(b_v, np.nan)

                    x_i_gen_v_temp[non_vertical_refl_mask][obj_on_y_mask_nv] = 0
                    y_i_gen_v_temp[non_vertical_refl_mask][obj_on_y_mask_nv] = \
                        b_v_nv[obj_on_y_mask_nv] + \
                        m_param_nv[obj_on_y_mask_nv] * x_P_v_nv[obj_on_y_mask_nv]

                # Subcase: Object not on y-axis (a_v_nv is not zero)
                obj_not_on_y_mask_nv = ~obj_on_y_mask_nv
                if np.any(obj_not_on_y_mask_nv):
                    den_xi_val = m_param_nv[obj_not_on_y_mask_nv] + \
                                 b_v_nv[obj_not_on_y_mask_nv] / a_v_nv[obj_not_on_y_mask_nv]
                    
                    # Avoid division by zero if Line 1 and Line 2 are parallel
                    safe_den_xi_mask = ~np.isclose(den_xi_val, 0)
                    
                    x_i_calc = np.full_like(den_xi_val, np.nan)
                    y_i_calc = np.full_like(den_xi_val, np.nan)

                    if np.any(safe_den_xi_mask):
                        # Numerator for x_i: b - m_param * sqrt(R^2-b^2)
                        num_xi_val = b_v_nv[obj_not_on_y_mask_nv][safe_den_xi_mask] - \
                                     m_param_nv[obj_not_on_y_mask_nv][safe_den_xi_mask] * \
                                     sqrt_term_nv[obj_not_on_y_mask_nv][safe_den_xi_mask]
                        
                        x_i_calc[safe_den_xi_mask] = num_xi_val / den_xi_val[safe_den_xi_mask]
                        y_i_calc[safe_den_xi_mask] = (b_v_nv[obj_not_on_y_mask_nv][safe_den_xi_mask] / \
                                                      a_v_nv[obj_not_on_y_mask_nv][safe_den_xi_mask]) * \
                                                      x_i_calc[safe_den_xi_mask]
                    
                    # Place calculated values into the temporary arrays
                    if 'x_i_gen_v_temp' not in locals():
                        x_i_gen_v_temp = np.full_like(a_v, np.nan)
                        y_i_gen_v_temp = np.full_like(b_v, np.nan)
                    
                    # Get a boolean mask relative to a_v for obj_not_on_y_mask_nv
                    # This is a bit complex due to nested masking.
                    # We need to map results from obj_not_on_y_mask_nv back to non_vertical_refl_mask indices
                    
                    # Create an index array for non_vertical_refl_mask
                    idx_non_vertical = np.where(non_vertical_refl_mask)[0]
                    
                    # Create an index array for obj_not_on_y_mask_nv within non_vertical_refl_mask
                    idx_obj_not_on_y_within_nv = np.where(obj_not_on_y_mask_nv)[0]

                    # Combine indices to update x_i_gen_v_temp and y_i_gen_v_temp
                    final_indices_for_update = idx_non_vertical[idx_obj_not_on_y_within_nv]

                    x_i_gen_v_temp[final_indices_for_update] = x_i_calc
                    y_i_gen_v_temp[final_indices_for_update] = y_i_calc


            # Consolidate results from vertical and non-vertical reflection if both occurred
            if 'x_i_gen_v_temp' in locals() and 'y_i_gen_v_temp' in locals() :
                 # Place results from valid_incidence_mask back into x_i_gen, y_i_gen
                x_i_gen[valid_incidence_mask] = x_i_gen_v_temp
                y_i_gen[valid_incidence_mask] = y_i_gen_v_temp
        
        # Place results from general_mask back into the final flat arrays
        x_i_flat[general_mask] = x_i_gen
        y_i_flat[general_mask] = y_i_gen
        
    return x_i_flat, y_i_flat

def generate_task8_plot_new(R_val, obj_left_x, obj_center_y, obj_world_height, plot_zoom, request_id):
    global global_image_rgba, img_height, img_width, img_aspect_ratio
    try:
        check_interrupt("8", request_id)
        if global_image_rgba is None: return generate_blank_image()
        H_obj_img, W_obj_img = img_height, img_width
        obj_world_width = img_aspect_ratio * obj_world_height
        
        x_obj_corners = np.linspace(obj_left_x, obj_left_x + obj_world_width, W_obj_img + 1)
        y_obj_corners = np.linspace(obj_center_y + obj_world_height / 2, obj_center_y - obj_world_height / 2, H_obj_img + 1)
        x_o_mesh, y_o_mesh = np.meshgrid(x_obj_corners, y_obj_corners)
        x_i_flat, y_i_flat = transform_points_spherical_aberration_t8_thales(x_o_mesh.flatten(), y_o_mesh.flatten(), R_val)
        x_i_mesh, y_i_mesh = x_i_flat.reshape(x_o_mesh.shape), y_i_flat.reshape(y_o_mesh.shape)

        fig = Figure(figsize=(9, 7)); ax = fig.add_subplot(111)
        obj_extent = [obj_left_x, obj_left_x + obj_world_width, obj_center_y - obj_world_height/2, obj_center_y + obj_world_height/2]
        # Assuming global_image_rgba[0,0] is top-left. For imshow 'upper' means [0,0] is top-left.
        ax.imshow(global_image_rgba, extent=obj_extent, origin='upper', aspect='auto', zorder=1)

        mirror_y = np.linspace(-R_val, R_val, 200); mirror_x = -np.sqrt(np.maximum(0, R_val**2 - mirror_y**2))
        ax.plot(mirror_x, mirror_y, 'b-', lw=2, label=f"Mirror (R={R_val:.2f})", zorder=0)
        ax.plot(0,0,'o',ms=7,c='blue',ls='None',label="C(0,0)",zorder=2)
        ax.plot(-R_val/2,0,'x',ms=7,c='red',ls='None',label=f"F(-{R_val/2:.2f},0)",zorder=2)
        ax.plot(-R_val,0,'P',ms=7,c='darkgreen',ls='None',label=f"V(-{R_val:.2f},0)",zorder=2)

        patches, facecolors = [], []
        FILTER_T8, R_sq_tol = 1e-6, R_val**2 + 1e-6
        for r_disp in range(H_obj_img): # r_disp is row in displayed object (0=top)
            # r_src = H_obj_img - 1 - r_disp # If global_image_rgba needs flipping for color source
            r_src = r_disp # Assuming global_image_rgba is already oriented as desired for coloring patches
            for c in range(W_obj_img):
                verts = [(x_i_mesh[r_disp,c],y_i_mesh[r_disp,c]), (x_i_mesh[r_disp,c+1],y_i_mesh[r_disp,c+1]), 
                         (x_i_mesh[r_disp+1,c+1],y_i_mesh[r_disp+1,c+1]), (x_i_mesh[r_disp+1,c],y_i_mesh[r_disp+1,c])]
                if any(np.isnan(v[0]) or np.isnan(v[1]) for v in verts): continue
                if not all(vx <= FILTER_T8 for vx,vy in verts): continue 
                patches.append(Polygon(verts, closed=True)); facecolors.append(global_image_rgba[r_src,c]) # Use r_src for color
        if patches:
            coll = PatchCollection(patches, fc=facecolors, ec='none', zorder=1.5, aa=True); ax.add_collection(coll)

        ax.set_title("Task 8: Concave Mirror (Spherical Aberration)"); ax.set_xlabel("x"); ax.set_ylabel("y")
        ax.axhline(0,c='grey',lw=0.5,ls=':'); ax.axvline(0,c='grey',lw=0.5,ls=':')
        
        all_x_coords = [0,-R_val/2,-R_val,obj_extent[0],obj_extent[1]]+list(mirror_x)
        all_y_coords = [0,0,0,obj_extent[2],obj_extent[3]]+list(mirror_y)
        valid_x_i = x_i_flat[~np.isnan(x_i_flat) & (x_i_flat <= FILTER_T8)]
        valid_y_i = y_i_flat[~np.isnan(y_i_flat) & ~np.isnan(x_i_flat) & (x_i_flat <= FILTER_T8)] # Match condition for x_i
        if len(valid_x_i) > 0: all_x_coords.extend(list(valid_x_i))
        if len(valid_y_i) > 0: all_y_coords.extend(list(valid_y_i))
        
        if all_x_coords and all_y_coords and any(~np.isnan(all_x_coords)) and any(~np.isnan(all_y_coords)):
            min_x,max_x = np.nanmin(all_x_coords),np.nanmax(all_x_coords)
            min_y,max_y = np.nanmin(all_y_coords),np.nanmax(all_y_coords)
            min_x=min(min_x,-R_val*1.1); max_x=max(max_x,R_val*0.2 if R_val > 0 else 0.2); 
            min_y=min(min_y,-R_val*1.1); max_y=max(max_y,R_val*1.1 if R_val > 0 else 1.1)
            cx,cy=(min_x+max_x)/2,(min_y+max_y)/2
            rx_range = (max_x-min_x) / plot_zoom # Inverted zoom logic: smaller zoom value = larger view
            ry_range = (max_y-min_y) / plot_zoom
            
            min_plot_range= (2.2*R_val if R_val > 0 else 1.0) / plot_zoom
            rx_range=max(rx_range, min_plot_range)
            ry_range=max(ry_range, min_plot_range)
            
            ax.set_xlim(cx-rx_range/2,cx+rx_range/2)
            ax.set_ylim(cy-ry_range/2,cy+ry_range/2)
        else: 
            lim_val = (1.5 * (R_val if R_val > 0 else 1.0)) / plot_zoom
            ax.set_xlim(-lim_val, lim_val * 0.5)
            ax.set_ylim(-lim_val, lim_val)

        ax.set_aspect('equal','box'); ax.legend(fontsize='small',loc='best'); ax.grid(True,ls=':',alpha=0.8); fig.tight_layout()
        buf = io.BytesIO(); FigureCanvas(fig).print_png(buf); buf.seek(0); return buf
    except Exception as e: logging.error(f"Task 8 plot error: {e}", exc_info=True); return generate_blank_image()

def transform_points_convex_obj_right_t9(x_o_flat, y_o_flat, R_mirror):
    x_i_flat, y_i_flat = np.full_like(x_o_flat, np.nan), np.full_like(y_o_flat, np.nan)
    if R_mirror <= 0: return x_i_flat, y_i_flat
    # Object is to the right of the pole V(R_mirror, 0). Center of mirror C is at (0,0).
    # So object x coordinates x_o_flat are > R_mirror.
    valid_obj_mask = x_o_flat > R_mirror 
    
    on_axis = valid_obj_mask & np.isclose(y_o_flat, 0)
    if np.any(on_axis):
        x_o_ax = x_o_flat[on_axis]
        # Paraxial approx for convex: 1/u + 1/v = 1/f = -2/R. Object distance u = x_o_ax - R_mirror (dist from V)
        # This function seems to use a different formulation, let's stick to it if it's from original.
        # The provided formula was: den = 2*x_o_ax - R_mirror; x_i = (x_o_ax*R_mirror)/den
        # This implies x_o_ax and x_i are distances from C (0,0).
        # If x_o is object distance from C, and x_i is image distance from C.
        # For convex mirror, if object is at x_o (>R), image is at x_i, y_i.
        # Let's assume the formula used is specific to the problem's coordinate system.
        den = 2*x_o_ax - R_mirror # This is for object distance from C.
        safe = ~np.isclose(den,0)
        x_i_ax = np.full_like(x_o_ax,np.nan); x_i_ax[safe] = (x_o_ax[safe]*R_mirror)/den[safe]
        x_i_flat[on_axis], y_i_flat[on_axis] = x_i_ax, 0

    # Off-axis points:
    # The original formula was: x_M = sqrt(R^2 - y_o^2)
    # den = 2*x_M - R - 2*x_o; common = -R/den; x_i = x_o*common; y_i = y_o*common
    # This seems to be a specific reflection formula. x_M is x-coord of reflection point on mirror for a ray from (x_o, y_o) that travels horizontally to mirror.
    # This is likely incorrect for general rays from (x_o, y_o).
    # A more standard approach for convex mirror (object right of V, C at origin):
    # u = x_o - R (distance from V). f = -R/2.
    # 1/(x_o-R) + 1/v' = -2/R => v' is image dist from V. Image pos x_i_plot = R + v'.
    # Magnification M = -v'/u = y_i / y_o.
    # Given the complexity, I will assume the provided transform_points_convex_obj_right_t9 was intended,
    # but it might have issues. For now, I will use it as is.
    off_axis = valid_obj_mask & ~np.isclose(y_o_flat,0) # No sqrt(R^2-y_o^2) check here, as x_M is calculated differently or not needed by this interpretation.
    
    if np.any(off_axis):
        x_o, y_o = x_o_flat[off_axis], y_o_flat[off_axis]
        # Using paraxial approximation for simplicity here, as the original formula seems problematic.
        # u = object distance from V(R,0). u = x_o - R.
        # f = -R/2 (convex mirror)
        u_dist = x_o - R_mirror
        v_dist_prime = np.full_like(u_dist, np.nan) # image distance from V
        
        safe_u = ~np.isclose(u_dist, -(R_mirror/2)) # Avoid u = -f (object at virtual focus for convex)
        # 1/u + 1/v' = 1/f => v' = uf / (u-f)
        f_convex = -R_mirror / 2.0
        denominator_v = u_dist[safe_u] - f_convex
        safe_denom_v = ~np.isclose(denominator_v, 0)
        
        if np.any(safe_denom_v):
            v_dist_prime[safe_u][safe_denom_v] = (u_dist[safe_u][safe_denom_v] * f_convex) / denominator_v[safe_denom_v]
        
        # Image position relative to C (0,0)
        x_i = R_mirror + v_dist_prime 
        
        magnification = np.full_like(u_dist, 0)
        safe_mag = ~np.isclose(u_dist,0) & ~np.isnan(v_dist_prime)
        magnification[safe_mag] = -v_dist_prime[safe_mag] / u_dist[safe_mag]
        y_i = y_o * magnification
        
        x_i_flat[off_axis], y_i_flat[off_axis] = x_i, y_i
        
    return x_i_flat, y_i_flat

def generate_task9_plot_new(R_val, obj_center_x_from_C, obj_center_y_from_axis, obj_height_factor, plot_zoom, request_id):
    global global_image_rgba, img_height, img_width, img_aspect_ratio
    try:
        check_interrupt("9", request_id)
        if global_image_rgba is None: return generate_blank_image()
        H_img, W_img = img_height, img_width
        obj_h_world = R_val * obj_height_factor
        obj_w_world = img_aspect_ratio * obj_h_world
        
        # obj_center_x_from_C is object's center X relative to C(0,0).
        # Mirror pole V is at (R_val, 0). Object must be to the right of V.
        # So, object's left edge must be > R_val.
        # obj_left_x_from_C = obj_center_x_from_C - obj_w_world / 2
        # Enforce obj_left_x_from_C > R_val  => obj_center_x_from_C > R_val + obj_w_world / 2
        min_obj_center_x = R_val + obj_w_world / 2.0 + 0.01 * R_val # Ensure small gap
        current_obj_center_x = max(obj_center_x_from_C, min_obj_center_x)

        # Corner coordinates of the object relative to C(0,0)
        x_obj_corners_from_C = np.linspace(current_obj_center_x - obj_w_world/2, current_obj_center_x + obj_w_world/2, W_img+1)
        y_obj_corners_from_axis = np.linspace(obj_center_y_from_axis + obj_h_world/2, obj_center_y_from_axis - obj_h_world/2, H_img+1)
        
        xo_mesh_C, yo_mesh_axis = np.meshgrid(x_obj_corners_from_C, y_obj_corners_from_axis)
        
        # Transform points (assuming transform function expects coords relative to C)
        xi_flat_C, yi_flat_axis = transform_points_convex_obj_right_t9(xo_mesh_C.flatten(), yo_mesh_axis.flatten(), R_val)
        xi_mesh_C, yi_mesh_axis = xi_flat_C.reshape(xo_mesh_C.shape), yi_flat_axis.reshape(yo_mesh_axis.shape)

        fig=Figure(figsize=(9,7)); ax=fig.add_subplot(111); fig.subplots_adjust(left=0.08,right=0.82,top=0.92,bottom=0.1)
        
        obj_extent_plot = [current_obj_center_x-obj_w_world/2, current_obj_center_x+obj_w_world/2, 
                           obj_center_y_from_axis-obj_h_world/2, obj_center_y_from_axis+obj_h_world/2]
        ax.imshow(global_image_rgba, extent=obj_extent_plot, origin='upper', aspect='auto', zorder=1.5)

        # Mirror (convex, opens to the left, C at (0,0), V at (R_val,0))
        mirror_y_coords = np.linspace(-R_val*0.999, R_val*0.999, 200) # Avoid exact +/-R for sqrt
        mirror_x_coords = np.sqrt(np.maximum(0, R_val**2 - mirror_y_coords**2)) # Positive sqrt for right half
        ax.plot(mirror_x_coords, mirror_y_coords,'g-',lw=2,label=f"Mirror (R={R_val:.2f})",zorder=0)
        ax.plot(0,0,'o',ms=7,c='blue',ls='None',label="C(0,0)",zorder=2) # Center of Curvature
        # Focal point for convex mirror is virtual, behind mirror, at R/2 from C, or -R/2 from V.
        # If V is at (R,0) and C is at (0,0), f = -R/2. Virtual focus Fv is at (R - R/2) = (R/2, 0) from C.
        ax.plot(R_val/2,0,'x',ms=7,c='darkorange',ls='None',label=f"Virtual Focus Fv({R_val/2:.2f},0)",zorder=2)
        ax.plot(R_val,0,'P',ms=7,c='darkgreen',ls='None',label=f"Pole V({R_val:.2f},0)",zorder=2)

        patches, fcolors_list = [],[]
        for r_disp in range(H_img): # r_disp is row in displayed object/image color source (0=top)
            for c_disp in range(W_img):
                # Vertices of the quadrilateral in the image plane (coords relative to C)
                verts = [(xi_mesh_C[r_disp,c_disp], yi_mesh_axis[r_disp,c_disp]), 
                         (xi_mesh_C[r_disp,c_disp+1], yi_mesh_axis[r_disp,c_disp+1]),
                         (xi_mesh_C[r_disp+1,c_disp+1], yi_mesh_axis[r_disp+1,c_disp+1]), 
                         (xi_mesh_C[r_disp+1,c_disp], yi_mesh_axis[r_disp+1,c_disp])]
                if not any(np.isnan(p[0]) or np.isnan(p[1]) for p in verts):
                    patches.append(Polygon(verts,closed=True))
                    fcolors_list.append(global_image_rgba[r_disp,c_disp]) # Color from original image orientation
        if patches: ax.add_collection(PatchCollection(patches,fc=fcolors_list,ec='none',zorder=1,aa=True))
        
        ax.set_title("Task 9: Convex Mirror (Object Right of Pole)");ax.set_xlabel("x (from C)");ax.set_ylabel("y (from axis)")
        ax.axhline(0,c='k',lw=0.8,ls='-');ax.axvline(0,c='dimgrey',lw=0.6,ls=':') # Optical axis and line through C
        ax.set_aspect('equal','box');ax.legend(fontsize='medium',loc='center left',bbox_to_anchor=(1.01,0.5));ax.grid(True,ls=':',alpha=0.7)

        # Determine plot limits
        all_x_plot = [0, R_val/2, R_val] + list(x_obj_corners_from_C) + list(mirror_x_coords)
        all_y_plot = [0, 0, 0] + list(y_obj_corners_from_axis) + list(mirror_y_coords)
        valid_xi = xi_flat_C[~np.isnan(xi_flat_C)]
        valid_yi = yi_flat_axis[~np.isnan(yi_flat_axis)]
        if len(valid_xi)>0: all_x_plot.extend(list(valid_xi))
        if len(valid_yi)>0: all_y_plot.extend(list(valid_yi))

        if all_x_plot and all_y_plot and any(~np.isnan(all_x_plot)) and any(~np.isnan(all_y_plot)):
            x_min_data, x_max_data = np.nanmin(all_x_plot), np.nanmax(all_x_plot)
            y_min_data, y_max_data = np.nanmin(all_y_plot), np.nanmax(all_y_plot)
            
            plot_center_x, plot_center_y = (x_min_data+x_max_data)/2, (y_min_data+y_max_data)/2
            plot_span = max(x_max_data-x_min_data, y_max_data-y_min_data, 0.5 * R_val if R_val > 0 else 1.0) * 1.25 # Base span
            
            scaled_span = plot_span / plot_zoom # Smaller zoom value = larger view (zoom out)
            
            ax.set_xlim(plot_center_x - scaled_span/2, plot_center_x + scaled_span/2)
            ax.set_ylim(plot_center_y - scaled_span/2, plot_center_y + scaled_span/2)
        else: 
            default_lim = (R_val*1.5 if R_val > 0 else 1.5) / plot_zoom
            ax.set_xlim(-default_lim*0.5, default_lim*1.5)
            ax.set_ylim(-default_lim, default_lim)
            
        fig.tight_layout(rect=[0,0,0.80,1]) # Adjust for legend
        buf=io.BytesIO();FigureCanvas(fig).print_png(buf);buf.seek(0);return buf
    except Exception as e: logging.error(f"Task 9 plot error: {e}", exc_info=True); return generate_blank_image()


def generate_task10_plot(Rf, arc_angle_deg, request_id): # Renamed arc_angle to arc_angle_deg
    global global_image_rgba, img_width, img_height

    try:
        check_interrupt("10", request_id)

        if global_image_rgba is None or img_width == 0 or img_height == 0:
            logging.warning("Task 10: Global image data not available or dimensions are zero.")
            return generate_blank_image()

        # inscribed_radius = sqrt((img_width / 2) ** 2 + (img_height / 2) ** 2) # More precise
        inscribed_radius = float(isqrt(int((img_width / 2) ** 2 + (img_height / 2) ** 2)))

        x_center_proj = 0.0
        # Center of the original flat image display is (0,0).
        # Projection arcs are centered around (x_center_proj, y_center_proj)
        # y_center_proj = -inscribed_radius # Shift projection center down by one inscribed_radius
        y_center_proj = 0.0 # Let's try centering projection at (0,0) for arcs, and see.
                            # Original code had y_center_proj = -img_height / 2, which is also an option.
                            # Let's use the original logic for y_center_proj for now.
        y_center_proj = -img_height / 2.0


        arc_angle_rad = np.deg2rad(arc_angle_deg)
        start_angle_rad = 1.5 * np.pi - arc_angle_rad / 2.0 # Centered around 270 deg (downwards)
        end_angle_rad = 1.5 * np.pi + arc_angle_rad / 2.0

        fig = Figure(figsize=(8, 8)) 
        ax = fig.add_subplot(111)

        R_max_factor_for_plot_extents = Rf + 1.0 # Outermost possible radius factor

        for row_idx in range(img_height): # row_idx = 0 is top row of image
            if row_idx % 10 == 0: 
                check_interrupt("10", request_id)

            num_arc_segments_points = max(10,img_width // 2) # More points for wider images
            
            # current_R_scale: Top of image (row_idx=0) maps to largest radius (farthest)
            # Bottom of image (row_idx=img_height-1) maps to smallest radius (closest, factor 1)
            # This creates the perspective depth.
            current_R_scale = Rf * ((img_height - 1.0 - row_idx) / max(1.0, img_height - 1.0)) + 1.0
            if img_height == 1: current_R_scale = Rf + 1.0


            theta_points = np.linspace(start_angle_rad, end_angle_rad, num_arc_segments_points)
            arc_x_coords = x_center_proj + inscribed_radius * current_R_scale * np.cos(theta_points)
            arc_y_coords = y_center_proj + inscribed_radius * current_R_scale * np.sin(theta_points)

            arc_segments = []
            for i in range(len(theta_points) - 1):
                p1 = (arc_x_coords[i], arc_y_coords[i])
                p2 = (arc_x_coords[i+1], arc_y_coords[i+1])
                arc_segments.append((p1, p2))

            # global_image_rgba[row_idx, :, :3] is the RGB for the current row (top row is row_idx=0)
            source_row_pixels_rgb = global_image_rgba[row_idx, :, :3] 

            interp_target_indices = np.linspace(0, img_width - 1, num_arc_segments_points)
            interpolated_colors_rgb = np.zeros((num_arc_segments_points, 3), dtype=np.float32)

            for ch_idx in range(3): 
                source_indices = np.arange(img_width)
                interpolated_colors_rgb[:, ch_idx] = np.interp(
                    interp_target_indices, source_indices, source_row_pixels_rgb[:, ch_idx]
                )
            
            segment_line_colors = (interpolated_colors_rgb[:-1] + interpolated_colors_rgb[1:]) / 2.0
            segment_line_colors = np.clip(segment_line_colors, 0.0, 1.0) 

            if arc_segments: # Ensure not empty
                lc = LineCollection(arc_segments, colors=segment_line_colors, linewidth=2) # Adjusted linewidth
                ax.add_collection(lc)

        # Display the original flat image for reference, centered at (0,0)
        # Image data global_image_rgba[0,0] is top-left. 'origin=upper' makes imshow display it that way.
        original_image_display_extent = [-img_width / 2.0, img_width / 2.0, 
                                         -img_height / 2.0, img_height / 2.0]
        ax.imshow(global_image_rgba, extent=original_image_display_extent, origin='upper', aspect='auto', alpha=0.5, zorder=-5)
        
        # Circle centered at the flat object's center (0,0) with the inscribed radius
        ref_circle_object_center = Circle((0, 0), inscribed_radius,
                                color="blue", fill=False, linewidth=1, linestyle=':', label=f"Object Inscribed R ({inscribed_radius:.0f}px)")
        ax.add_artist(ref_circle_object_center)
        
        # Circle indicating the projection center and its base radius (smallest arc)
        projection_base_circle = Circle((x_center_proj, y_center_proj), inscribed_radius, # Radius factor is 1 here
                                color="dimgray", fill=False, linewidth=1, linestyle='--', label=f"Projection Base R ({inscribed_radius:.0f}px)")
        ax.add_artist(projection_base_circle)
        
        ax.scatter(x_center_proj, y_center_proj, color="red", marker="P", s=60, zorder=5, label="Projection Origin")
        
        # Determine plot limits based on the drawn content
        # Max radius of any arc: inscribed_radius * R_max_factor_for_plot_extents
        max_abs_radius = inscribed_radius * R_max_factor_for_plot_extents
        
        # Consider the extent of the flat image and the projection arcs
        plot_min_x = min(original_image_display_extent[0], x_center_proj - max_abs_radius)
        plot_max_x = max(original_image_display_extent[1], x_center_proj + max_abs_radius)
        plot_min_y = min(original_image_display_extent[2], y_center_proj - max_abs_radius)
        plot_max_y = max(original_image_display_extent[3], y_center_proj + max_abs_radius) # Max y can be above y_center_proj if arcs go up

        ax.set_xlim(plot_min_x - 10, plot_max_x + 10) # Add some padding
        ax.set_ylim(plot_min_y - 10, plot_max_y + 10)
        
        ax.set_title(f"Anamorphic Projection (Rf Factor: {Rf:.2f}, Arc: {arc_angle_deg:.1f}°)")
        ax.set_xlabel("X Coordinate (pixels)")
        ax.set_ylabel("Y Coordinate (pixels)")
        ax.legend(fontsize='small', loc='best')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.set_aspect('equal', adjustable='box')
        fig.tight_layout() 
        
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        buf.seek(0)
        return buf
        
    except Exception as e:
        logging.error(f"Task 10 plot generation failed: {e}", exc_info=True)
        return generate_blank_image()

def generate_task11d_plot(alpha_deg_slider, request_id): # Renamed alpha to alpha_deg_slider
    try:
        check_interrupt("11d", request_id)
        r_sphere = 1 # Radius of the sphere (droplet) for visualization scale
        alpha_rad = np.deg2rad(alpha_deg_slider) # Sun elevation angle

        def calculate_rainbow_params(frequency_THz, sun_alpha_rad):
            # Refractive index of water (using the formula from Task 1b/11a)
            n = (1 + ((1 / (1.731 - 0.261 * ((frequency_THz / 1000.0)**2)))**0.5))**0.5
            
            # Critical angles of incidence (Theta_crit) for minimum deviation
            # For primary rainbow (k=1 internal reflection in Descartes' model)
            with np.errstate(invalid='ignore', divide='ignore'): # Handle potential domain errors for sqrt/arcsin
                theta_crit_pri_arg = (4.0 - n**2) / 3.0
                theta_crit_pri = np.arcsin(np.sqrt(np.clip(theta_crit_pri_arg, 0, 1))) if theta_crit_pri_arg >=0 and theta_crit_pri_arg <=1 else np.nan

                # For secondary rainbow (k=2 internal reflections)
                theta_crit_sec_arg = (9.0 - n**2) / 8.0
                theta_crit_sec = np.arcsin(np.sqrt(np.clip(theta_crit_sec_arg, 0, 1))) if theta_crit_sec_arg >=0 and theta_crit_sec_arg <=1 else np.nan

            # Minimum deviation angles (Epsilon) relative to anti-solar point
            epsilon_pri_rad = np.nan
            if not np.isnan(theta_crit_pri):
                 # Check if sin(theta_crit_pri)/n is valid for arcsin
                sin_phi_pri = np.sin(theta_crit_pri)/n
                if abs(sin_phi_pri) <=1:
                    phi_pri = np.arcsin(sin_phi_pri)
                    epsilon_pri_rad = 4 * phi_pri - 2 * theta_crit_pri
                else: # Should not happen if theta_crit_pri is valid
                    pass


            epsilon_sec_rad = np.nan
            if not np.isnan(theta_crit_sec):
                sin_phi_sec = np.sin(theta_crit_sec)/n
                if abs(sin_phi_sec) <=1:
                    phi_sec = np.arcsin(sin_phi_sec)
                    epsilon_sec_rad = np.pi - (6 * phi_sec - 2 * theta_crit_sec) # Original was pi - 6*arcsin(sin(Th)/n) + 2*Th
                                                                            # which is pi - (6*phi - 2*Th)
                else:
                    pass


            # Apparent radius of the rainbow arc in the sky, considering sun's elevation
            # Radius_sky = Epsilon (angular radius from anti-solar point)
            # For plotting circles on a 2D plane representing the view:
            # We need the projected radius and center of these circles.
            # The original code's Radius1/2 and Center1/2 seem to be for a specific 2D projection.
            # Let's use Epsilon directly as the angular radius.
            # The plot will show circles whose radii are proportional to sin(Epsilon_apparent).
            # Apparent elevation angle of rainbow from horizon = Epsilon - alpha_rad (for primary, if Epsilon > alpha)
            # Or, more simply, the circles represent cones of light.
            
            # Using the logic from the original snippet for Radius and Center if it's a specific visualization model
            # These are likely radii and y-offsets for circles in a 2D plot
            radius_plot_pri = r_sphere * np.sin(epsilon_pri_rad) * np.cos(sun_alpha_rad) if not np.isnan(epsilon_pri_rad) else np.nan
            radius_plot_sec = r_sphere * np.sin(epsilon_sec_rad) * np.cos(sun_alpha_rad) if not np.isnan(epsilon_sec_rad) else np.nan
            
            # y-offset of the circle's center from the anti-solar point's projection on the "screen"
            # This seems to be related to the vertical shift due to sun's elevation
            # Original: Center = Radius - r * sin(Epsilon - alpha)
            # If Radius is radius_plot, and r is r_sphere
            center_y_offset_pri = radius_plot_pri - r_sphere * np.sin(epsilon_pri_rad - sun_alpha_rad) if not np.isnan(radius_plot_pri) and not np.isnan(epsilon_pri_rad) else np.nan
            center_y_offset_sec = radius_plot_sec - r_sphere * np.sin(epsilon_sec_rad - sun_alpha_rad) if not np.isnan(radius_plot_sec) and not np.isnan(epsilon_sec_rad) else np.nan


            return {
                "plot_radius_primary": radius_plot_pri,
                "plot_center_y_primary": -center_y_offset_pri, # Negative if center is plotted below origin for positive offset
                "plot_radius_secondary": radius_plot_sec,
                "plot_center_y_secondary": -center_y_offset_sec,
                "epsilon_primary_deg": np.rad2deg(epsilon_pri_rad),
                "epsilon_secondary_deg": np.rad2deg(epsilon_sec_rad)
            }

        frequencies_thz = [442.5, 495, 520, 565, 610, 650, 735] # Red to Violet
        color_names = ["red", "orange", "yellow", "green", "cyan", "blue", "darkviolet"]
        
        plot_data = []
        for freq, color_name in zip(frequencies_thz, color_names):
            params = calculate_rainbow_params(freq, alpha_rad)
            plot_data.append({**params, "color": color_name, "freq_label": f"{freq} THz"})
            check_interrupt("11d", request_id)

        fig = Figure(figsize=(7, 7))
        ax = fig.add_subplot(111)
        ax.set_facecolor('lightskyblue') # Sky color

        max_plot_radius = 0.0
        for data_point in plot_data:
            # Primary Rainbow Circle
            if not np.isnan(data_point["plot_radius_primary"]) and not np.isnan(data_point["plot_center_y_primary"]):
                if data_point["plot_radius_primary"] > 0:
                    circle_pri = Circle((0, data_point["plot_center_y_primary"]), 
                                        data_point["plot_radius_primary"], 
                                        color=data_point["color"], linewidth=2, fill=False, alpha=0.8)
                    ax.add_artist(circle_pri)
                    max_plot_radius = max(max_plot_radius, abs(data_point["plot_center_y_primary"]) + data_point["plot_radius_primary"])

            # Secondary Rainbow Circle (colors are reversed, but we draw with the frequency's color)
            if not np.isnan(data_point["plot_radius_secondary"]) and not np.isnan(data_point["plot_center_y_secondary"]):
                if data_point["plot_radius_secondary"] > 0: # Ensure radius is positive
                    circle_sec = Circle((0, data_point["plot_center_y_secondary"]), 
                                        data_point["plot_radius_secondary"], 
                                        color=data_point["color"], linewidth=1.5, fill=False, alpha=0.6, linestyle='--')
                    ax.add_artist(circle_sec)
                    max_plot_radius = max(max_plot_radius, abs(data_point["plot_center_y_secondary"]) + data_point["plot_radius_secondary"])
        
        # Horizon line
        ax.axhline(0, color='darkgreen', linewidth=3, label="Horizon (Observer at O)") 
        # Anti-solar point (ASP) - rainbows are centered around this direction.
        # If sun is at elevation alpha, ASP is at declination -alpha.
        # In this 2D plot, let's mark observer's eye level as y=0.
        # The y-centers of circles are relative to the projection of ASP.
        # If ASP is at y_asp, then circles are at (0, y_asp + data_point["plot_center_y_..."])
        # The current plot_center_y seems to already incorporate this.

        ax.set_aspect("equal", adjustable='box')
        
        # Dynamic limits based on what's drawn
        if max_plot_radius == 0: max_plot_radius = r_sphere # Default if no bows visible
        plot_limit_val = max(max_plot_radius * 1.2, r_sphere * 0.5) # Ensure some view even if small
        
        ax.set_xlim(-plot_limit_val, plot_limit_val)
        # Y-axis: observer at origin, horizon y=0. Rainbows appear above.
        # If plot_center_y can be negative (meaning circle center is below ASP's projection)
        # and ASP's projection itself is below horizon for high sun, then ylim needs care.
        # For now, let's assume positive y is up.
        ax.set_ylim(-plot_limit_val * 0.2, plot_limit_val) # Show a bit below horizon

        ax.set_title(f"Rainbow View (Sun Elevation α = {alpha_deg_slider:.1f}°)")
        ax.set_xlabel("Horizontal View Angle (arbitrary units)")
        ax.set_ylabel("Vertical View Angle (arbitrary units from horizon)")
        ax.grid(True, linestyle=':', alpha=0.4)
        # ax.legend() # Can add legend if needed for horizon etc.

        fig.tight_layout()
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Task 11d plot error: {e}", exc_info=True)
        return generate_blank_image()


########################################
# STATIC TASKS MAPPING
########################################
static_tasks = {
    "1a": generate_task1a_plot, "1b": generate_task1b_plot,
    "2": generate_task2_plot,
    "11a": generate_task11a_plot, "11b": generate_task11b_plot, "11c": generate_task11c_plot,
    "12bi": generate_task12bi_plot, "12bii": generate_task12bii_plot, "12biii": generate_task12biii_plot,
}

########################################
# IMAGE UPLOAD ROUTE
########################################
@app.route('/upload', methods=["POST"])
def upload_file(): 
    global global_image_rgba, img_height, img_width, img_aspect_ratio, H, W
    if "image_file" not in request.files: return redirect(url_for("index"))
    file = request.files["image_file"]
    if file.filename == "": return redirect(url_for("index"))
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        file.save(filepath)
        load_and_process_image(filepath) 
        H, W = img_height, img_width 
        
        # Update slider configurations that depend on image dimensions
        if "5" in interactive_tasks:
            interactive_tasks["5"]["sliders"][0]["max"] = int(3 * img_width)
            interactive_tasks["5"]["sliders"][0]["value"] = int(img_width / 10.0 +1)
            interactive_tasks["5"]["sliders"][0]["step"] = max(1,int(img_width/20))
            interactive_tasks["5"]["sliders"][1]["min"] = int(-img_height) # Slider range
            interactive_tasks["5"]["sliders"][1]["max"] = int(img_height)  # Slider range
            interactive_tasks["5"]["sliders"][1]["step"] = max(1,int(img_height/20))
            interactive_tasks["5"]["sliders"][2]["min"] = int(max(img_width, img_height) * 1.5)
            interactive_tasks["5"]["sliders"][2]["max"] = int(max(img_width, img_height) * 5)
            interactive_tasks["5"]["sliders"][2]["value"] = int(max(img_width, img_height) * 3)

        if "6" in interactive_tasks:
            interactive_tasks["6"]["sliders"][0]["max"] = int(3 * img_width)
            interactive_tasks["6"]["sliders"][0]["value"] = int(1.5*img_width)
            interactive_tasks["6"]["sliders"][0]["step"] = max(1,int(img_width/20))
            interactive_tasks["6"]["sliders"][1]["min"] = -int(1.5 * img_height) # Slider range
            interactive_tasks["6"]["sliders"][1]["max"] = int(1.5 * img_height)  # Slider range
            interactive_tasks["6"]["sliders"][1]["step"] = max(1,int(img_height/20))
            interactive_tasks["6"]["sliders"][3]["max"] = int(2*img_width)
            interactive_tasks["6"]["sliders"][3]["value"] = int(0.75*img_width)
            interactive_tasks["6"]["sliders"][3]["step"] = max(1,int(img_width/20))
            if "extra_context" not in interactive_tasks["6"]: interactive_tasks["6"]["extra_context"] = {}
            interactive_tasks["6"]["extra_context"]["img_width"] = img_width
        
        if "9" in interactive_tasks:
            default_R_t9 = interactive_tasks["9"]["sliders"][0]["value"] 
            default_h_factor_t9 = interactive_tasks["9"]["sliders"][3]["value"] 
            obj_h_world_t9 = default_R_t9 * default_h_factor_t9
            obj_w_world_t9 = img_aspect_ratio * obj_h_world_t9 if img_aspect_ratio > 0 else obj_h_world_t9
            # obj_center_x_from_C > R_val + obj_w_world / 2
            min_obj_center_x_t9 = default_R_t9 + obj_w_world_t9 / 2.0 + 0.01 * default_R_t9
            interactive_tasks["9"]["sliders"][1]["min"] = round(min_obj_center_x_t9, 2) 
            if interactive_tasks["9"]["sliders"][1]["value"] < min_obj_center_x_t9: 
                interactive_tasks["9"]["sliders"][1]["value"] = round(min_obj_center_x_t9,2)

    except Exception as e:
        logging.error(f"Error uploading/processing {filename}: {e}", exc_info=True)
        load_and_process_image(DEFAULT_IMAGE_PATH) 
    
    return redirect(url_for("index"))

########################################
# ROUTE: Handle Plot (Interactive/Static)
########################################
@app.route('/plot/<task_id>')
def plot_task(task_id):
    req_id_param = request.args.get("_req_id", str(uuid.uuid4())) 
    
    if task_id in interactive_tasks:
        active_requests[task_id] = req_id_param 
        try:
            buf = None
            if task_id == "3":
                v_log = float(request.args.get("v", interactive_tasks["3"]["sliders"][0]["value"]))
                n_val = float(request.args.get("n", interactive_tasks["3"]["sliders"][1]["value"]))
                y_val = float(request.args.get("y", interactive_tasks["3"]["sliders"][2]["value"]))
                l_val = float(request.args.get("l", interactive_tasks["3"]["sliders"][3]["value"]))
                buf = generate_task3_plot(v_log, n_val, y_val, l_val, req_id_param)
            elif task_id == "4":
                v_log = float(request.args.get("v_task4", interactive_tasks["4"]["sliders"][0]["value"]))
                n1 = float(request.args.get("n1", interactive_tasks["4"]["sliders"][1]["value"]))
                n2 = float(request.args.get("n2", interactive_tasks["4"]["sliders"][2]["value"]))
                y = float(request.args.get("y_task4", interactive_tasks["4"]["sliders"][3]["value"]))
                l = float(request.args.get("l_task4", interactive_tasks["4"]["sliders"][4]["value"]))
                buf = generate_task4_plot(v_log, n1, n2, y, l, req_id_param)
            elif task_id == "5":
                off_x = float(request.args.get("offset_x", interactive_tasks["5"]["sliders"][0]["value"]))
                off_y = float(request.args.get("offset_y", interactive_tasks["5"]["sliders"][1]["value"])) # This is the slider value
                can_size = float(request.args.get("canvas_size", interactive_tasks["5"]["sliders"][2]["value"]))
                buf = generate_task5_plot(off_x, off_y, can_size, req_id_param)
            elif task_id == "6": # Also Task 7
                st_x = int(request.args.get("start_x", interactive_tasks["6"]["sliders"][0]["value"]))
                st_y = int(request.args.get("start_y", interactive_tasks["6"]["sliders"][1]["value"])) # This is the slider value
                sc = int(request.args.get("scale", interactive_tasks["6"]["sliders"][2]["value"]))
                f = int(request.args.get("f_val", interactive_tasks["6"]["sliders"][3]["value"]))
                buf = generate_task6_plot(st_x, st_y, sc, f, req_id_param)
            elif task_id == "8":
                r = float(request.args.get("R_val_t8", interactive_tasks["8"]["sliders"][0]["value"]))
                ox = float(request.args.get("obj_left_x_t8", interactive_tasks["8"]["sliders"][1]["value"]))
                oy = float(request.args.get("obj_center_y_t8", interactive_tasks["8"]["sliders"][2]["value"]))
                oh = float(request.args.get("obj_world_height_t8", interactive_tasks["8"]["sliders"][3]["value"]))
                pz = float(request.args.get("plot_zoom_t8", interactive_tasks["8"]["sliders"][4]["value"]))
                buf = generate_task8_plot_new(r, ox, oy, oh, pz, req_id_param)
            elif task_id == "9":
                r = float(request.args.get("R_val_t9", interactive_tasks["9"]["sliders"][0]["value"]))
                ocx = float(request.args.get("obj_center_x_t9", interactive_tasks["9"]["sliders"][1]["value"]))
                ocy = float(request.args.get("obj_center_y_t9", interactive_tasks["9"]["sliders"][2]["value"]))
                ohf = float(request.args.get("obj_height_factor_t9", interactive_tasks["9"]["sliders"][3]["value"]))
                pz = float(request.args.get("plot_zoom_t9", interactive_tasks["9"]["sliders"][4]["value"]))
                buf = generate_task9_plot_new(r, ocx, ocy, ohf, pz, req_id_param)
            elif task_id == "10":
                rf_param = float(request.args.get("Rf", interactive_tasks["10"]["sliders"][0]["value"]))
                arc_param = float(request.args.get("arc_angle", interactive_tasks["10"]["sliders"][1]["value"]))
                buf = generate_task10_plot(rf_param, arc_param, req_id_param)
            elif task_id == "11d":
                alpha_param = float(request.args.get("alpha_11d", interactive_tasks["11d"]["sliders"][0]["value"]))
                buf = generate_task11d_plot(alpha_param, req_id_param)
            elif task_id == "12a":
                theta_i = float(request.args.get("ThetaI", interactive_tasks["12a"]["sliders"][0]["value"]))
                alpha_p = float(request.args.get("alpha", interactive_tasks["12a"]["sliders"][1]["value"]))
                scale_12a = float(request.args.get("canvas_scale_12a", interactive_tasks["12a"]["sliders"][2]["value"]))
                buf = generate_task12a_plot(theta_i, alpha_p, scale_12a, req_id_param)
            else:
                return "Interactive task plot generation not fully implemented.", 404
            
            if buf: return send_file(buf, mimetype="image/png")
            else: return send_file(generate_blank_image(), mimetype="image/png")

        except Exception as e:
            logging.error(f"Error in interactive task {task_id} plot: {e}", exc_info=True)
            return send_file(generate_blank_image(), mimetype="image/png")

    elif task_id in static_tasks:
        try:
            buf = static_tasks[task_id]()
            return send_file(buf, mimetype="image/png")
        except Exception as e:
            logging.error(f"Error in static task {task_id} plot: {e}", exc_info=True)
            return send_file(generate_blank_image(), mimetype="image/png")
    else:
        return f"Plot for task {task_id} not defined.", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000)) 
    app.run(debug=True, host="0.0.0.0", port=port)

# main.py
import os
import io
import uuid
import logging
from math import isqrt, cos, sin, radians, pi, log10, acos, atan2, degrees
from time import perf_counter
from flask import Flask, request, redirect, url_for, render_template_string, send_file, jsonify
from werkzeug.utils import secure_filename
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Polygon
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
MAX_DIMENSION = 100  # maximum width or height (in pixels)
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
        # skimage.transform.resize can change dtype and range, ensure [0,1]
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
    # plt.close(fig) # Figure created locally, should be garbage collected. Explicit close can be problematic with FigureCanvasAgg
    buf.seek(0)
    return buf

########################################
# HELPER FUNCTIONS FOR TASK 12 (PRISM MODEL)
########################################
def get_prism_color_for_frequency(f): # Renamed from color to avoid conflict
    if 405e12 <= f < 480e12: return (1, 0, 0) # Red
    elif 480e12 <= f < 510e12: return (1, 127/255, 0) # Orange
    elif 510e12 <= f < 530e12: return (1, 1, 0) # Yellow
    elif 530e12 <= f < 600e12: return (0, 1, 0) # Green
    elif 600e12 <= f < 620e12: return (0, 1, 1) # Cyan
    elif 620e12 <= f < 680e12: return (0, 0, 1) # Blue
    else: return (137/255, 0, 1) # Violet

def draw_triangle_prism(ax, alpha_rad): # Renamed from triangle
    half_base = np.sin(alpha_rad / 2.0)
    height = np.cos(alpha_rad / 2.0)
    
    left_vertex = (-half_base, 0)
    right_vertex = (half_base, 0)
    top_vertex = (0, height)
    
    vertices = [left_vertex, top_vertex, right_vertex, left_vertex]
    x_coords, y_coords = zip(*vertices)
    ax.plot(x_coords, y_coords, 'r-', linewidth=2, zorder=0) # prism behind rays

def get_refractive_index_sellmeier(wavelength_m): # Renamed from GetRefractIndex
    x_um = wavelength_m * 1e6
    a_coeffs = np.array([1.03961212, 0.231792344, 1.01146945])
    b_coeffs = np.array([0.00600069867, 0.0200179144, 103.560653])
    
    n_sq_minus_1 = np.zeros_like(x_um)
    for i in range(len(a_coeffs)):
        n_sq_minus_1 += (a_coeffs[i] * (x_um**2)) / ((x_um**2) - b_coeffs[i] + 1e-9) # Avoid div by zero
    return np.sqrt(np.maximum(1, 1 + n_sq_minus_1)) # Ensure n >= 1


########################################
# TASK 12a PLOT FUNCTION (Dynamic Prism Model) - Revised
########################################
def generate_task12a_plot(ThetaI_deg_slider, alpha_deg_slider, request_id):
    try:
        check_interrupt("12a", request_id)
        
        alpha_rad = np.deg2rad(alpha_deg_slider)     # Prism apex angle
        # ThetaI_deg_slider is angle of incidence from horizontal.
        # Let ray initially aim towards origin (0,0) from left.
        # If prism apex is at (0, cos(a/2)), base on x-axis.
        # A ray from left with angle ThetaI_deg_slider to horizontal has direction ThetaI_rad = np.deg2rad(ThetaI_deg_slider)
        # For simplicity, let incident ray start at x_start = -1.5, and its y be such that it would pass through (0, y_aim_on_prism_face)
        # This is complex. Let's use the original interpretation where ThetaI is relative to the normal of the first face.
        # But the slider is "Incident Angle (deg from horizontal)". This is an absolute angle.
        
        # Let ThetaI_abs_rad be the absolute angle of the incident ray (0 = horizontal right, pi/2 = vertical up)
        ThetaI_abs_rad = np.deg2rad(ThetaI_deg_slider)

        # Prism geometry: apex (0, H_p), base on x-axis [-B_p/2, B_p/2]
        # H_p = cos(alpha_rad/2), B_p/2 = sin(alpha_rad/2) for unit slant height.
        # Normal to left face (points outward, ~2nd quadrant): N_L_angle = pi - alpha_rad/2
        # Normal to right face (points outward, ~1st quadrant): N_R_angle = alpha_rad/2
        N_L_angle = np.pi - alpha_rad / 2.0
        N_R_angle = alpha_rad / 2.0

        frequencies = np.linspace(405e12, 790e12, 50) # Reduced points for speed
        wavelengths_m = 3e8 / frequencies
        n_prism_array = get_refractive_index_sellmeier(wavelengths_m)
        n_air = 1.0

        all_segments_incident = []
        all_segments_internal = []
        all_segments_exit = []
        all_colors = []

        # Define entry point on left face, e.g., halfway up its height.
        # Left face from (-sin(a/2), 0) to (0, cos(a/2)). Midpoint: (-sin(a/2)/2, cos(a/2)/2)
        P1_x = -np.sin(alpha_rad/2.0) * 0.5
        P1_y = np.cos(alpha_rad/2.0) * 0.5 
        
        # Incident ray segment (length 1, ending at P1)
        P0_x = P1_x - 1.0 * np.cos(ThetaI_abs_rad)
        P0_y = P1_y - 1.0 * np.sin(ThetaI_abs_rad)

        for i in range(len(frequencies)):
            check_interrupt("12a", request_id)
            n_prism = n_prism_array[i]
            ray_color = get_prism_color_for_frequency(frequencies[i])
            all_colors.append(ray_color)

            # 1. First Refraction (Air -> Prism) at P1
            # Angle of incidence i1: angle between ray (ThetaI_abs_rad) and normal (N_L_angle)
            # Using vector math: ray_vec . normal_vec = cos(i1_abs)
            # Or, more directly: i1_signed = ThetaI_abs_rad - N_L_angle (angle from normal to ray)
            # We need angle of ray wrt normal, ensuring it's acute for Snell's law magnitude.
            i1_raw = N_L_angle - ThetaI_abs_rad
            i1_raw = pi - i1_raw
            # Normalize i1_raw to [-pi, pi]
            i1_signed = atan2(sin(i1_raw), cos(i1_raw))
            #print(ThetaI_abs_rad, N_L_angle, i1_raw, i1_signed)
            
            # Snell's Law: n_air * sin(i1_signed) = n_prism * sin(r1_signed)
            sin_r1_signed = (n_air / n_prism) * np.sin(i1_signed)
            if abs(sin_r1_signed) > 1.0: # Should not happen for air to prism if i1_signed is correct
                # This indicates an issue, possibly ray missing prism or extreme angle
                # For visualization, assume it passes straight or stop this ray
                P2_x, P2_y = P1_x + 0.1*cos(ThetaI_abs_rad), P1_y + 0.1*sin(ThetaI_abs_rad) # Tiny segment
                all_segments_incident.append([[P0_x, P0_y], [P1_x, P1_y]])
                all_segments_internal.append([[P1_x, P1_y], [P2_x, P2_y]]) # Show as internal for color
                all_segments_exit.append([[P2_x, P2_y], [P2_x, P2_y]]) # No exit
                continue

            r1_signed = np.arcsin(sin_r1_signed)
            
            # Direction of internal ray (d_internal_abs): Normal + angle_from_normal
            d_internal_abs = N_L_angle + r1_signed
            d_internal_real = (N_L_angle + r1_signed + pi) % (2*pi)

            # 2. Find intersection P2 of internal ray with right face
            # Right face passes through (sin(a/2), 0) and (0, cos(a/2))
            # Line P1 to P2: (x - P1_x)/cos(d_internal) = (y - P1_y)/sin(d_internal) = t
            # Right face line: (y-0)*(0-sin(a/2)) = (x-sin(a/2))*(cos(a/2)-0)
            # => -y*sin(a/2) = (x-sin(a/2))*cos(a/2)
            # Substitute x = P1_x + t*cos(d_internal), y = P1_y + t*sin(d_internal)
            # -(P1_y + t*sin(d_internal))*sin(a/2) = (P1_x + t*cos(d_internal) - sin(a/2))*cos(a/2)
            # Solve for t.
            # Denom_t = -sin(d_internal)*sin(a/2) - cos(d_internal)*cos(a/2) = -cos(d_internal - a/2)
            # Numer_t = P1_x*cos(a/2) - sin(a/2)*cos(a/2) + P1_y*sin(a/2)
            denom_t = -np.cos(d_internal_abs - alpha_rad/2.0)
            if abs(denom_t) < 1e-9: # Ray parallel to face, or error
                P2_x, P2_y = P1_x + 1.0*cos(d_internal_abs), P1_y + 1.0*sin(d_internal_abs) # Extend by 1 unit
            else:
                numer_t = P1_x*np.cos(alpha_rad/2.0) - np.sin(alpha_rad/2.0)*np.cos(alpha_rad/2.0) + P1_y*np.sin(alpha_rad/2.0)
                t_to_P2 = numer_t / denom_t
                P2_x = P1_x + t_to_P2 * np.cos(d_internal_abs)
                P2_y = P1_y + t_to_P2 * np.sin(d_internal_abs)

            # 3. Second Refraction (Prism -> Air) at P2
            # Angle of incidence i2: angle between internal ray (d_internal_abs) and normal (N_R_angle)
            i2_raw = d_internal_real - N_R_angle
            i2_signed = atan2(sin(i2_raw), cos(i2_raw)) # Angle from normal N_R to internal ray

            sin_i2_mag = np.abs(np.sin(i2_signed))
            
            d_exit_abs = d_internal_abs # Default if TIR or error
            #print(d_internal_abs, d_internal_real, i2_raw, N_R_angle, i1_signed, r1_signed)
            is_tir = False
            if n_prism * sin_i2_mag > n_air: # TIR condition
                is_tir = True
                # Reflected ray: angle from normal is -i2_signed
                r2_signed_tir = -i2_signed + pi 
                d_exit_abs = N_R_angle + r2_signed_tir
                d_exit_abs %= 2 * pi
            else: # Refraction
                sin_r2_signed = (n_prism / n_air) * np.sin(i2_signed)
                r2_signed = np.arcsin(np.clip(sin_r2_signed, -1, 1))
                d_exit_abs = N_R_angle + r2_signed
            
            # Exit ray segment (length 1, starting at P2)
            P3_x = P2_x + 1.0 * np.cos(d_exit_abs)
            P3_y = P2_y + 1.0 * np.sin(d_exit_abs)

            all_segments_incident.append([[P0_x, P0_y], [P1_x, P1_y]])
            all_segments_internal.append([[P1_x, P1_y], [P2_x, P2_y]])
            all_segments_exit.append([[P2_x, P2_y], [P3_x, P3_y]])

        fig = Figure(figsize=(8, 6))
        fig.patch.set_facecolor('black')
        ax = fig.add_subplot(111, facecolor="black")
        
        # Plot incident rays (usually white, but let's use colors if dispersed for effect, though not physically accurate for incident)
        # For simplicity, make all incident white
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
        ax.set_xlim(-1.6, 1.6)
        ax.set_ylim(-0.8, 1.2)
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        for spine in ax.spines.values(): spine.set_edgecolor('white')
        ax.xaxis.label.set_color('white'); ax.yaxis.label.set_color('white'); ax.title.set_color('white')
        ax.set_aspect('equal', adjustable='box')


        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        # plt.close(fig) # Handled by garbage collector for Figure
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
        <p><strong>Keypress controls (first click the slider then use the key presses):</strong></p>
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
                <button class="small-task-button" onclick="window.location.href='{{ url_for('subtask_page', task_id=key) }}'">{{ task_info.title }}</button>
            {% else %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('handle_task', task_id=key) }}'">{{ task_info.title }}</button>
            {% endif %}
         {% endif %}
      {% endfor %}
  </div>

  <script>
    var requestTimer = null;
    var uniqueRequestId = null; // To track the latest request

    function formatDisplayValue(sliderId, rawValue) {
        let displayValue;
        const floatVal = parseFloat(rawValue);
        if (sliderId === "v" || sliderId === "v_task4") { // Log speed sliders
            displayValue = Math.pow(10, floatVal).toExponential(2);
        } else if (rawValue.includes('.') && Math.abs(floatVal) < 0.01 && floatVal !== 0) {
            displayValue = floatVal.toExponential(2);
        } else if (rawValue.includes('.')) {
            // Count decimal places in step to determine precision, default to 2
            const stepStr = document.getElementById(sliderId).step;
            let precision = 2;
            if (stepStr && stepStr.includes('.')) {
                precision = stepStr.split('.')[1].length;
            } else if (Math.abs(floatVal) < 10 && !Number.isInteger(floatVal)) { // More precision for small numbers
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
      }, 150); // Debounce time
    }

    {% if banned_validation %}
      var IMG_WIDTH_JS = {{ img_width if img_width else 100 }}; 
      var oldValues = {};
      {% for slider in sliders %}
         oldValues["{{ slider.id }}"] = parseFloat(document.getElementById("{{ slider.id }}").value);
      {% endfor %}

      function sliderChangedWithValidation(event) {
        var sliderId = event.target.id;
        var newValue = parseFloat(event.target.value);
        var startXElement = document.getElementById("start_x");
        var fValElement = document.getElementById("f_val");

        if (startXElement && fValElement) {
            var start_x = parseFloat(startXElement.value);
            var f_val = parseFloat(fValElement.value); // Current f_val before this change

            if (sliderId === "start_x") { // If start_x slider is moved
              if (start_x <= f_val && f_val <= start_x + IMG_WIDTH_JS) { // If f_val is in banned region relative to *old* start_x
                // We need to compare newValue (new start_x) with f_val
                if (newValue <= f_val && f_val <= newValue + IMG_WIDTH_JS) { // If f_val is in banned region of *new* start_x
                    if (newValue > oldValues["start_x"]) { fValElement.value = newValue + IMG_WIDTH_JS + 1; } 
                    else { fValElement.value = newValue - 1; } 
                    document.getElementById("f_val_value").innerText = formatDisplayValue("f_val", fValElement.value);
                }
              }
            } else if (sliderId === "f_val") { // If f_val slider is moved
              if (start_x <= newValue && newValue <= start_x + IMG_WIDTH_JS) { // If new f_val (newValue) is in banned region
                if (newValue > oldValues["f_val"]) { fValElement.value = start_x + IMG_WIDTH_JS + 1; }
                else { fValElement.value = start_x - 1; }
                // The value of fValElement is already set, just update display
                document.getElementById("f_val_value").innerText = formatDisplayValue("f_val", fValElement.value);
              }
            }
        }
        oldValues[sliderId] = parseFloat(document.getElementById(sliderId).value); // Update old value for this slider
        updatePlot();
      }
    {% endif %}
    
    {% for slider in sliders %}
      {% if banned_validation %}
        document.getElementById("{{ slider.id }}").addEventListener("input", sliderChangedWithValidation);
      {% else %}
        document.getElementById("{{ slider.id }}").addEventListener("input", updatePlot);
      {% endif %}
    {% endfor %}

    document.querySelectorAll('input[type=range]').forEach(function(slider) {
      slider.addEventListener("keydown", function(e) {
         let step = parseFloat(slider.step);
         if (isNaN(step) || step <= 0) { // Infer step if not standard
            let min = parseFloat(slider.min);
            let max = parseFloat(slider.max);
            step = (max - min) / 100; // Default to 1/100th of range
            if (slider.id === "v" || slider.id === "v_task4") step = 0.01; // Smaller for log
         }
         let value = parseFloat(slider.value);
         let min = parseFloat(slider.min);
         let max = parseFloat(slider.max);
         let keyProcessed = false;

         {% if task_id_for_template == "12a" %}
             if (slider.id === 'ThetaI') {
                 if (e.key.toLowerCase() === 'q') { value = Math.max(min, value - step); keyProcessed = true; }
                 if (e.key.toLowerCase() === 'w') { value = Math.min(max, value + step); keyProcessed = true; }
             } else if (slider.id === 'alpha') { 
                 if (e.key.toLowerCase() === 'a') { value = Math.max(min, value - step); keyProcessed = true; }
                 if (e.key.toLowerCase() === 's') { value = Math.min(max, value + step); keyProcessed = true; }
             }
         {% endif %}
         
         if (!keyProcessed) {
             if(e.key === "ArrowRight" || e.key === "ArrowUp"){ value = Math.min(max, value + step); keyProcessed = true; } 
             else if(e.key === "ArrowLeft" || e.key === "ArrowDown"){ value = Math.max(min, value - step); keyProcessed = true; }
         }

         if (keyProcessed) {
             slider.value = value;
             document.getElementById(slider.id + "_value").innerText = formatDisplayValue(slider.id, String(value));
             updatePlot();
             e.preventDefault();
         }
      });
    });

    document.getElementById("plotImage").addEventListener("load", function() {
      const currentSrc = document.getElementById("plotImage").src;
      // Check if the loaded image's request ID matches the latest one we sent
      if (currentSrc.includes("_req_id=" + uniqueRequestId) || !currentSrc.includes("_req_id=")) {
          document.getElementById("spinner").style.display = "none";
          document.getElementById("loadingText").style.display = "none";
      }
    });
    document.getElementById("plotImage").addEventListener("error", function() {
      // Ensure spinner stops even on error, for the latest request
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
         document.getElementById(animationSliderId + "_value").innerText = formatDisplayValue(animationSliderId, String(startVal));
         updatePlot(); 

         var current = startVal;
         currentAnimation = setInterval(function() {
            current += stepVal;
            if (current > endVal) {
               current = startVal; // Loop animation
               // clearInterval(currentAnimation); currentAnimation = null;
               // document.getElementById("playButton").innerText = "Play Animation";
            }
            slider.value = current;
            document.getElementById(animationSliderId + "_value").innerText = formatDisplayValue(animationSliderId, String(current));
            updatePlot();
         }, interval);
      });
    {% endif %}

    window.onload = function() {
        {% for slider in sliders %}
            document.getElementById("{{ slider.id }}_value").innerText = formatDisplayValue("{{ slider.id }}", document.getElementById("{{ slider.id }}").value);
        {% endfor %}
        
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
    initial_query = "&".join([f"{key}={value}" for key, value in initial_params.items()])
    
    current_img_width = img_width if 'img_width' in globals() and img_width is not None else 100

    context = {
        "sliders": slider_config, "title": title, "plot_endpoint": plot_endpoint,
        "initial_query": initial_query, "banned_validation": banned_validation,
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
        "title": "Task 3 Interactive: Reflection Travel Time",
        "sliders": [
            {"id": "v", "label": "Speed (m/s)", "min": round(log10(3),3), "max": round(log10(3e8),3), "value": round(log10(3e8),3), "step": 0.05, "unit": " m/s"},
            {"id": "n", "label": "Refractive Index", "min": 1, "max": 3, "value": 1, "step": 0.05},
            {"id": "y", "label": "Height (m)", "min": 1, "max": 10, "value": 1, "step": 0.1},
            {"id": "l", "label": "Length (m)", "min": 0.1, "max": 3.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/3",
        "banned_validation": False
    },
    "4": {
        "title": "Task 4 Interactive: Refraction Travel Time",
        "sliders": [
            {"id": "v_task4", "label": "Log10(Speed)", "min": round(log10(3),3), "max": round(log10(3e8),3), "value": round(log10(3e8),3), "step": 0.05, "unit": " m/s"},
            {"id": "n1", "label": "Refractive Index 1", "min": 1, "max": 3, "value": 1.0, "step": 0.05},
            {"id": "n2", "label": "Refractive Index 2", "min": 1, "max": 3, "value": 1.5, "step": 0.05},
            {"id": "y_task4", "label": "Height (m)", "min": 1, "max": 10, "value": 1, "step": 0.1},
            {"id": "l_task4", "label": "Length (m)", "min": 0.1, "max": 3.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/4",
        "banned_validation": False
    },
    "5": {
        "title": "Task 5 Interactive: Virtual Image Plot",
        "sliders": [
            {"id": "offset_x", "label": "Object X Dist from Mirror", "min": 0, "max": int(3 * (img_width if img_width else W)), "value": int((img_width if img_width else W)/10.0 +1), "step": max(1,int(W/20)), "unit":"px"},
            {"id": "offset_y", "label": "Object Y Offset from Center", "min": int(-(img_height if img_height else H)), "max": int(img_height if img_height else H), "value": 0, "step": max(1,int(H/20)), "unit":"px"},
            {"id": "canvas_size", "label": "Canvas Size", "min": int(max(W, H) * 1.5), "max": int(max(W, H) * 5), "value": int(max(W,H)*3), "step": 10, "unit":"px"}
        ],
        "plot_endpoint": "/plot/5",
        "banned_validation": False
    },
    "6": { 
        "title": "Task 6+7: Converging Lens Model",
        "sliders": [
            {"id": "start_x", "label": "Object Start X (from lens)", "min": 0, "max": int(3 * (img_width if img_width else W)), "value": int(1.5*(img_width if img_width else W)), "step": max(1,int(W/20)), "unit":"px"},
            {"id": "start_y", "label": "Object Start Y (from axis)", "min": -int(1.5 * (img_height if img_height else H)), "max": int(1.5 * (img_height if img_height else H)), "value": 0, "step": max(1,int(H/20)), "unit":"px"},
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
        "banned_validation": False 
    },
    "9": {
        "title": "Task 9: Convex Mirror (Object Right of Pole)",
        "sliders": [
            {"id": "R_val_t9", "label": "Mirror Radius (R)", "min": 0.2, "max": 5.0, "value": 1.0, "step": 0.05, "unit":" units"},
            {"id": "obj_center_x_t9", "label": "Object Center X (from C)", "min": 1.0 + 0.35/2 + 0.01, "max": 4.5, "value": 1.8, "step": 0.02, "unit":" units"}, # Min depends on R and obj_width
            {"id": "obj_center_y_t9", "label": "Object Center Y (from axis)", "min": -2.0, "max": 2.0, "value": 0.0, "step": 0.02, "unit":" units"},
            {"id": "obj_height_factor_t9", "label": "Obj Height Factor (rel to R)", "min": 0.1, "max": 1.5, "value": 0.7, "step": 0.05},
            {"id": "plot_zoom_t9", "label": "Plot Zoom", "min": 0.15, "max": 6.0, "value": 1.0, "step": 0.05}
        ],
        "plot_endpoint": "/plot/9",
        "banned_validation": False
    },
    "10": {
        "title": "Task 10 Interactive: Anamorphic Image Mapping",
        "sliders": [
            {"id": "Rf", "label": "Projection Scale (R_effective / R_base)", "min": 1, "max": 10, "value": 3, "step": 0.1},
            {"id": "arc_angle", "label": "Arc Angle", "min": 10, "max": 360, "value": 160, "step": 5, "unit":" deg"}
        ],
        "plot_endpoint": "/plot/10",
        "banned_validation": False
    },
    "11d": {
        "title": "Task 11d Interactive: Rainbow Elevation Angles",
        "sliders": [
            {"id": "alpha_11d", "label": "Sun Elevation Angle (α)", "min": 0, "max": 60, "value": 0, "step": 1, "unit":" deg"}
        ],
        "plot_endpoint": "/plot/11d",
        "banned_validation": False,
        "playable": True
    },
    "12a": { 
        "title": "Task 12a: Interactive Prism Dispersion",
        "sliders": [
            {"id": "ThetaI", "label": "Incident Ray Angle (from horizontal)", "min": 0, "max": 90, "value": 30, "step": 1, "unit":" deg"},
            {"id": "alpha", "label": "Prism Apex Angle", "min": 10, "max": 90, "value": 60, "step": 1, "unit":" deg"}
        ],
        "plot_endpoint": "/plot/12a", 
        "banned_validation": False
    }
}
# Dynamic update for Task 9 slider based on current image aspect ratio
try:
    default_R_t9 = interactive_tasks["9"]["sliders"][0]["value"] 
    default_h_factor_t9 = interactive_tasks["9"]["sliders"][3]["value"] 
    initial_obj_height_t9 = default_R_t9 * default_h_factor_t9
    initial_obj_width_t9 = img_aspect_ratio * initial_obj_height_t9 if img_aspect_ratio > 0 else initial_obj_height_t9
    min_obj_x_t9 = default_R_t9 + initial_obj_width_t9 / 2.0 + 0.01 * default_R_t9
    interactive_tasks["9"]["sliders"][1]["min"] = round(min_obj_x_t9, 2) 
    if interactive_tasks["9"]["sliders"][1]["value"] < min_obj_x_t9:
        interactive_tasks["9"]["sliders"][1]["value"] = round(min_obj_x_t9,2)
except Exception as e:
    logging.warning(f"Could not dynamically set Task 9 slider min: {e}")


########################################
# TASK OVERVIEW AND BUTTON LABELS
########################################
task_overview = {
    "1": {"title": "Task 1", "desc": "Refractive index plots.", "subtasks": {"1a": "Crown Glass Index", "1b": "Water Index"}, "button_text": "Refractive Indices"},
    "1a": {"title": "Task 1a", "desc": "Sellmeier formula for crown glass.", "subtasks": {}, "button_text": "Crown Glass Index"},
    "1b": {"title": "Task 1b", "desc": "Refractive index of water vs frequency.", "subtasks": {}, "button_text": "Water Index Plot"},
    "2": {"title": "Task 2", "desc": "Thin lens equation verification.", "subtasks": {}, "button_text": "Thin Lens Verification"},
    "3": {"title": "Task 3", "desc": "Fermat’s principle for reflection.", "subtasks": {}, "button_text": "Reflection Time"},
    "4": {"title": "Task 4", "desc": "Fermat’s principle for refraction.", "subtasks": {}, "button_text": "Refraction Time"},
    "5": {"title": "Task 5", "desc": "Virtual image in a plane mirror.", "subtasks": {}, "button_text": "Virtual Image"},
    "6": {"title": "Task 6+7", "desc": "Real image by a converging lens.", "subtasks": {}, "button_text": "Converging Lens Image"}, 
    "8": {"title": "Task 8", "desc": "Real image by a concave spherical mirror.", "subtasks": {}, "button_text": "Concave Mirror Image"},
    "9": {"title": "Task 9", "desc": "Virtual image by a convex spherical mirror.", "subtasks": {}, "button_text": "Convex Mirror Image"},
    "10": {"title": "Task 10", "desc": "Anamorphic projection.", "subtasks": {}, "button_text": "Anamorphic Projection"},
    "11": {"title": "Task 11", "desc": "Rainbow elevation angles.", "subtasks": {"11a": "Descartes' Model ε Curves", "11b": "Rainbow Color Mapping", "11c": "Refraction Angle Scatter", "11d": "Interactive Refraction Circles"}, "button_text": "Rainbow Angles"},
    "11a": {"title": "Task 11a", "desc": "Elevation angles using computed ε curves.", "subtasks": {}, "button_text": "ε Curves"},
    "11b": {"title": "Task 11b", "desc": "Rainbow curve color mapping.", "subtasks": {}, "button_text": "Color Mapping"},
    "11c": {"title": "Task 11c", "desc": "Scatter plot for refraction angles.", "subtasks": {}, "button_text": "Refraction Scatter"},
    "11d": {"title": "Task 11d", "desc": "Interactive refraction circles for rainbow.", "subtasks": {}, "button_text": "Interactive Circles"},
    "12": {
        "title": "Task 12", "desc": "Prism light dispersion and angle analysis.",
        "subtasks": { "12a": "Interactive Prism Model", "12b": "Prism Angle Plots" },
        "button_text": "Prism Analysis"
    },
    "12a": { 
        "title": "Task 12a", "desc": "Dynamic model of white light through a prism.", "subtasks": {},
        "button_text": "Interactive Prism" 
    },
    "12b": { 
        "title": "Task 12b", "desc": "Static plots related to prism angles.",
        "subtasks": { 
            "12bi": "Transmission Angle vs Incidence",
            "12bii": "Deflection Angle vs Incidence",
            "12biii": "Deflection vs. Vertex Angle"
        },
        "button_text": "Prism Angle Plots" 
    },
    "12bi": {"title": "Task 12bi: Transmission Angle", "desc": "Transmission angle vs. incidence.", "subtasks": {}, "button_text": "Transmission Angle"},
    "12bii": {"title": "Task 12bii: Deflection Angle", "desc": "Deflection angle vs. incidence.", "subtasks": {}, "button_text": "Deflection Angle"},
    "12biii": {"title": "Task 12biii: Deflection vs. Vertex", "desc": "Deflection for various vertex angles.", "subtasks": {}, "button_text": "Deflection vs. Vertex"}
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
      font-size: 1.1em; margin: 8px; padding: 18px; width: calc(50% - 24px); max-width: 320px;
      text-align: center; text-decoration: none; transition: background-color 0.25s, transform 0.2s;
      box-shadow: 0px 3px 7px rgba(0,0,0,0.12); display: flex; flex-direction: column; justify-content: center; min-height: 70px;
    }
    .button-link:hover { background-color: #0056b3; transform: translateY(-3px); box-shadow: 0px 5px 10px rgba(0,0,0,0.15); }
    .button-link .task-title { font-weight: 500; }
    .button-link .task-button-text { font-size: 0.8em; margin-top: 4px; color: #d0e0ff; }
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
          <span class="task-title">{{ task.title }}</span>
          <span class="task-button-text">{{ task.button_text }}</span>
        </a>
      {% endif %}
    {% endfor %}
  </div>
  
  <div class="upload-form">
    <form method="POST" action="{{ url_for('upload_file') }}" enctype="multipart/form-data">
      <label for="image_file">Upload Image (max {{ max_dimension }}px side):</label><br>
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
      font-size: 1.1em; margin: 8px; padding: 18px; width: 90%; max-width: 400px;
      text-align: center; text-decoration: none; transition: background-color 0.25s, transform 0.2s;
      box-shadow: 0px 3px 6px rgba(0,0,0,0.1);
    }
    .button-link:hover { background-color: #117a8b; transform: translateY(-2px); }
    .button-link .subtask-title { font-weight: 500; }
    .button-link .subtask-desc { font-size: 0.85em; margin-top: 5px; color: #e0f7fa; }
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
         <span class="subtask-title">{{ sub_task_def.button_text if sub_task_def.button_text else sub_task_def.title if sub_task_def.title else subkey }}</span><br>
         <span class="subtask-desc">{{ sub_desc_from_parent }}</span>
      </a>
    {% endfor %}
  </div>
  <div class="nav-buttons-footer">
    <button class="back-button" onclick="window.location.href='{{ url_for('index') }}'">Back to Home</button>
    {% for key, task_info in tasks_overview.items() %}
        {% if key not in ['1a', '1b', '11a', '11b', '11c', '11d', '12a', '12b', '12bi', '12bii', '12biii'] %}
            {% if task_info.subtasks and task_info.subtasks|length > 0 %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('subtask_page', task_id=key) }}'">{{ task_info.title }}</button>
            {% else %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('handle_task', task_id=key) }}'">{{ task_info.title }}</button>
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
                <button class="small-task-button" onclick="window.location.href='{{ url_for('subtask_page', task_id=key) }}'">{{ task_info.title }}</button>
            {% else %}
                <button class="small-task-button" onclick="window.location.href='{{ url_for('handle_task', task_id=key) }}'">{{ task_info.title }}</button>
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
                                      subtasks_for_page=parent_task["subtasks"], #This is a dict {subkey: desc_string}
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
                                      task_id_for_plot=task_id, # For img src
                                      tasks_overview=task_overview,
                                      current_task_id_for_nav=task_id) # For footer nav highlighting (optional)
    elif task_id == "12b": # This is a subtask menu page itself
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
                                       banned_validation=config.get("banned_validation", False),
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
    frequency_THz = np.linspace(405,790,500) # THz
    # Formula for n_water from original: (1+((1/(1.731-0.261*((frequency/1000)**2)))**0.5))**0.5
    # This seems to be a custom or simplified formula. Let's use it.
    # The (frequency/1000) part implies the input frequency was expected in other units if this was for THz.
    # Assuming frequency_THz is correct input for the formula's structure:
    n_water = (1 + ((1 / (1.731 - 0.261 * ((frequency_THz / 1000.0)**2)))**0.5))**0.5

    points = np.array([frequency_THz, n_water]).T.reshape(-1,1,2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = LineCollection(segments, cmap=colourmap, linewidth=3)
    lc.set_array(frequency_THz) # Color lines by frequency
    
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
    u_cm = np.array([20, 25, 30, 35, 40, 45, 50, 55]) # from original
    v_cm = np.array([65.5,40,31,27,25,23.1,21.5,20.5]) # from original
    inv_u = 1.0 / u_cm
    inv_v = 1.0 / v_cm
    m, c = np.polyfit(inv_u, inv_v, 1) # Slope m, intercept c
    
    fig = Figure(figsize=(8,5))
    ax = fig.add_subplot(111)
    ax.scatter(inv_u, inv_v, color="red", zorder=2, label="Data Points")
    ax.plot(inv_u, m * inv_u + c, zorder=1, label=f"Fit: y={m:.3f}x + {c:.3f}")
    # Focal length f = 1/c (if m approx 1) or from 1/f = 1/u + 1/v
    # If thin lens equation 1/u + 1/v = 1/f, then c = 1/f.
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
        n = (1+((1/(1.731-0.261*((freq_THz/1000.0)**2)))**0.5))**0.5 # Using freq_THz
        # Epsilon1 is for secondary rainbow (k=2), Epsilon2 for primary (k=1)
        Epsilon1_sec = pi - 6*np.arcsin(np.sin(Theta_rad)/n) + 2*Theta_rad
        Epsilon2_pri = 4*np.arcsin(np.sin(Theta_rad)/n) - 2*Theta_rad
        
        with np.errstate(invalid='ignore'): # Suppress warnings for sqrt of negative
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
    ax.set_ylim(0, 180) # Deflection angles typically in this range
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

    # Primary rainbow (lower)
    points_pri = np.array([frequency_THz, Epsilon_pri_deg]).T.reshape(-1,1,2)
    segments_pri = np.concatenate([points_pri[:-1], points_pri[1:]], axis=1)
    lc_pri = LineCollection(segments_pri, cmap=colourmap_11b, linewidth=3)
    lc_pri.set_array(frequency_THz)
    # Secondary rainbow (higher)
    points_sec = np.array([frequency_THz, Epsilon_sec_deg]).T.reshape(-1,1,2)
    segments_sec = np.concatenate([points_sec[:-1], points_sec[1:]], axis=1)
    lc_sec = LineCollection(segments_sec, cmap=colourmap_11b, linewidth=3) # Secondary is fainter, but same width for plot
    lc_sec.set_array(frequency_THz) # Colors are inverted for secondary in reality, but map uses frequency
    
    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    ax.add_collection(lc_pri)
    ax.add_collection(lc_sec)
    ax.set_xlim(frequency_THz.min(),frequency_THz.max())
    ax.set_ylim(min(np.nanmin(Epsilon_pri_deg)-2, np.nanmin(Epsilon_sec_deg)-2), 
                max(np.nanmax(Epsilon_pri_deg)+2, np.nanmax(Epsilon_sec_deg)+2))
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
        Theta_crit_pri = np.arcsin(np.sqrt(np.clip((4-n_water**2)/3.0,0,1))) # For primary rainbow
        Theta_crit_sec = np.arcsin(np.sqrt(np.clip((9-n_water**2)/8.0,0,1))) # For secondary rainbow
    
    # Refraction angle phi for these critical incidence angles
    Phi_pri_rad = np.arcsin(np.sin(Theta_crit_pri)/n_water)
    Phi_sec_rad = np.arcsin(np.sin(Theta_crit_sec)/n_water)
    # Critical angle for TIR (used as a reference line, Theta_inc = 90 deg)
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

# --- Task 12b Static Plots ---
def generate_task12bi_plot(): 
    frequency_val = 542.5e12
    wavelength_val = 3e8 / frequency_val
    alpha_val = np.pi/4 # Apex angle A = 45 deg
    ThetaI_rad = np.linspace(0, np.pi/2, 500) 
    n = get_refractive_index_sellmeier(np.array([wavelength_val]))[0]
    
    sin_e_arg = np.sqrt(np.maximum(0, n**2 - np.sin(ThetaI_rad)**2)) * np.sin(alpha_val) - np.sin(ThetaI_rad) * np.cos(alpha_val)
    e_rad = np.arcsin(np.clip(sin_e_arg, -1, 1)) # Final exit angle 'e' (transmission angle relative to normal of exit face)
    
    valid_mask = ~np.isnan(e_rad) & (np.abs(sin_e_arg) <= 1.0) # Ensure valid arcsin input
    ThetaI_deg_valid = np.rad2deg(ThetaI_rad[valid_mask])
    e_deg_valid = np.rad2deg(e_rad[valid_mask])
    
    ThetaMax_deg = 0
    if len(e_deg_valid) > 0:
        # Find where exit angle e is 90 deg (grazing exit)
        # This means sin_e_arg is +/- 1.
        # Find first ThetaI where e_deg is ~90 or ~-90. This is when ray just emerges.
        grazing_indices = np.where(np.isclose(np.abs(e_deg_valid), 90, atol=1.0))[0]
        if len(grazing_indices) > 0:
             ThetaMax_deg = ThetaI_deg_valid[grazing_indices[0]] # Smallest incidence for grazing

    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    if len(ThetaI_deg_valid)>0:
        ax.plot(ThetaI_deg_valid, e_deg_valid, label=f"n ≈ {n:.3f}")
    ax.set_xlabel("Angle of Incidence on First Face (degrees)")
    ax.set_ylabel("Angle of Emergence from Second Face (degrees)")
    title = f"Task 12bi: Emergence Angle vs. Incidence (Apex α={degrees(alpha_val):.0f}°)"
    if ThetaMax_deg > 0:
        # title += f"\nMax Incidence for Emergence ≈ {ThetaMax_deg:.1f}°"
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
    e_deg_valid = np.rad2deg(e_rad[valid_mask])

    ThetaMax_deg, min_delta_deg, ThetaI_min_delta_deg = 0, 0, 0
    if len(delta_deg_valid) > 0:
        grazing_indices = np.where(np.isclose(np.abs(e_deg_valid), 90, atol=1.0))[0]
        if len(grazing_indices) > 0: ThetaMax_deg = ThetaI_deg_valid[grazing_indices[0]]
        
        min_delta_idx = np.nanargmin(delta_deg_valid)
        min_delta_deg = delta_deg_valid[min_delta_idx]
        ThetaI_min_delta_deg = ThetaI_deg_valid[min_delta_idx]

    fig = Figure(figsize=(8,6))
    ax = fig.add_subplot(111)
    if len(ThetaI_deg_valid) > 0:
        ax.plot(ThetaI_deg_valid, delta_deg_valid, label=f"n ≈ {n:.3f}")
    ax.set_xlabel("Angle of Incidence on First Face (degrees)")
    ax.set_ylabel("Angle of Deviation (degrees)")
    title = f"Task 12bii: Deviation vs. Incidence (Apex α={degrees(alpha_val):.0f}°)"
    if ThetaMax_deg > 0 :
        ax.axvline(x=ThetaMax_deg, color='r', linestyle='--', alpha=0.7, label=f"Limit for Emergence ≈ {ThetaMax_deg:.1f}°")
    if min_delta_deg != 0:
        ax.scatter(ThetaI_min_delta_deg, min_delta_deg, color='g', zorder=5, s=40, label=f"Min. Deviation ≈ {min_delta_deg:.1f}°")
    ax.legend(fontsize='small')
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

    for i, alpha_deg_val in enumerate(range(10, 81, 5)):
        alpha_rad_val = np.deg2rad(alpha_deg_val)
        
        sin_e_arg = np.sqrt(np.maximum(0,n**2 - np.sin(ThetaI_rad)**2)) * np.sin(alpha_rad_val) - np.sin(ThetaI_rad) * np.cos(alpha_rad_val)
        with np.errstate(invalid='ignore'): # arcsin can produce nan for invalid inputs
            e_rad = np.arcsin(np.clip(sin_e_arg, -1.0, 1.0))
        delta_rad = ThetaI_rad + e_rad - alpha_rad_val
        
        valid_mask = ~np.isnan(e_rad) & (np.abs(sin_e_arg) <= 1.0)
        ThetaI_plot_deg = np.rad2deg(ThetaI_rad[valid_mask])
        delta_plot_deg = np.rad2deg(delta_rad[valid_mask])
        
        if len(ThetaI_plot_deg) > 0:
            ax.plot(ThetaI_plot_deg, delta_plot_deg, color=colors_12biii[i], label=f'{alpha_deg_val}°')
    
    ax.set_xlabel("Angle of Incidence on First Face (degrees)")
    ax.set_ylabel("Angle of Deviation (degrees)")
    ax.set_title(f"Task 12biii: Deviation vs. Incidence for Various Apex Angles (n ≈ {n:.3f})")
    ax.legend(title="Apex Angle α", bbox_to_anchor=(1.02, 1), loc='upper left', fontsize='small')
    ax.grid(True, linestyle=":", alpha=0.8)
    ax.set_ylim(bottom=min(0, ax.get_ylim()[0] if ax.get_ylim()[0] < 0 else 0), top = max(80, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 80) ) 
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
        x = np.linspace(0.001, l_val-0.001, 300) # Avoid exact ends if y is small
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (np.sqrt(x**2 + y_val**2) / (v_actual / n1_val)) + \
                (np.sqrt((l_val - x)**2 + y_val**2) / (v_actual / n2_val))
        
        fig = Figure(figsize=(8,5))
        ax = fig.add_subplot(111)

        if len(x)>0 and not np.all(np.isnan(t)):
            idx = np.nanargmin(t)
            x_min = x[idx]
            # Angles relative to normal (vertical line at x_min)
            theta1 = np.arctan(x_min / y_val) if y_val != 0 else (np.pi/2 if x_min > 0 else 0)
            theta2 = np.arctan((l_val - x_min) / y_val) if y_val != 0 else (np.pi/2 if (l_val-x_min)>0 else 0)
            
            # Snell's Law check: n1 sin(theta1) = n2 sin(theta2)
            # The plot title used sin(theta)/(v/n). v/n is speed in medium.
            # Fermat's principle implies n1*sin(theta1_surface) = n2*sin(theta2_surface)
            # where theta_surface are angles to normal at boundary.
            # The provided title was more complex. Let's use n*sin(theta).
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

def generate_task5_plot(offset_x_slider, offset_y_slider, canvas_size_val, request_id):
    global global_image_rgba, img_height, img_width
    try:
        check_interrupt("5", request_id)
        if global_image_rgba is None or img_height == 0 or img_width == 0: 
            logging.warning("Task 5: Global image not available.")
            return generate_blank_image()

        S = int(canvas_size_val)
        H_img, W_img = img_height, img_width
        
        fig = Figure(figsize=(7, 7)) 
        ax = fig.add_subplot(111)
        
        canvas_array = np.ones((S, S, 4), dtype=np.float32) # White RGBA background

        # Mirror is at plot X = S/2.
        # Object's left edge X on plot: S/2 + offset_x_slider
        # Object's center Y on plot: S/2 + offset_y_slider (positive slider moves object up)

        obj_plot_left_x = S/2 + offset_x_slider
        obj_plot_bottom_y = (S/2 + offset_y_slider) - H_img / 2.0
        
        # Image's right edge X on plot: S/2 - offset_x_slider
        img_plot_left_x = (S/2 - offset_x_slider) - W_img
        img_plot_bottom_y = obj_plot_bottom_y # Same y as object

        # Draw object
        for r_img in range(H_img): # 0 to H_img-1 (top to bottom of source image)
            if r_img % 20 == 0: check_interrupt("5", request_id) # Check less frequently
            for c_img in range(W_img): # 0 to W_img-1 (left to right of source image)
                color_rgba = global_image_rgba[r_img, c_img]
                
                # Object pixel target on canvas array
                # Plot X maps to canvas column. Plot Y maps to canvas row (flipped).
                canvas_c_obj = int(obj_plot_left_x + c_img)
                canvas_r_obj = int(S - 1 - (obj_plot_bottom_y + (H_img - 1 - r_img)) ) # map r_img (top=0) to plot y (bottom=0) then to array row (top=0)

                if 0 <= canvas_r_obj < S and 0 <= canvas_c_obj < S:
                    canvas_array[canvas_r_obj, canvas_c_obj] = color_rgba
                
                # Image pixel target on canvas array
                canvas_c_img = int(img_plot_left_x + c_img)
                canvas_r_img = canvas_r_obj # Same y mapping

                if 0 <= canvas_r_img < S and 0 <= canvas_c_img < S:
                    canvas_array[canvas_r_img, canvas_c_img] = color_rgba
        
        ax.imshow(canvas_array, extent=[0, S, 0, S], origin='lower', interpolation='nearest')
        ax.axvline(x=S / 2, color="black", linestyle="--", lw=1.0, label="Mirror")
        
        ax.set_xlim(0, S)
        ax.set_ylim(0, S)
        
        # Ticks: 0 for mirror X is S/2. 0 for object Y center is S/2.
        # X-axis: show S/2 as "0 (Mirror)"
        # Y-axis: show S/2 as "0 (Centerline)"
        num_ticks = 5
        x_ticks = np.linspace(0, S, num_ticks)
        y_ticks = np.linspace(0, S, num_ticks)
        x_tick_labels = [f"{val - S/2:.0f}" for val in x_ticks]
        y_tick_labels = [f"{val - S/2:.0f}" for val in y_ticks]
        ax.set_xticks(x_ticks)
        ax.set_xticklabels(x_tick_labels)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_tick_labels)

        ax.set_title(f"Object X from Mirror: {offset_x_slider:.0f}px, Object Y Offset: {offset_y_slider:.0f}px")
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

def generate_task6_plot(start_x_obj, start_y_obj, scale_val, f_val_lens, request_id):
    global global_image_rgba, img_height, img_width
    try:
        check_interrupt("6", request_id)
        if global_image_rgba is None or img_height == 0 or img_width == 0:
            # logging.warning("Task 6: Global image not available or dimensions are zero.")
            return generate_blank_image()

        H_img, W_img = img_height, img_width
        num_channels_on_canvas = 4 # For RGBA

        # Canvas setup (lens at center of this canvas for calculations)
        diag_obj = np.sqrt(W_img**2 + H_img**2)
        canvas_dim_heuristic = max(diag_obj * scale_val, abs(f_val_lens) * 4, abs(start_x_obj)*2) * 1.5
        canvas_height = int(canvas_dim_heuristic)
        canvas_width = int(canvas_dim_heuristic * 1.2) # Make it wider

        # Ensure minimum canvas size to prevent issues
        canvas_height = max(canvas_height, 100) # Min height
        canvas_width = max(canvas_width, 100)  # Min width

        plot_canvas = np.ones((canvas_height, canvas_width, num_channels_on_canvas), dtype=np.float32) # White RGBA

        # Lists to store coordinates of successfully drawn image pixels for interpolation bounds
        drawn_image_pixel_cols = []
        drawn_image_pixel_rows = []

        # Lens is at (canvas_width/2, canvas_height/2) in array coordinates.
        for r_img in range(H_img): # 0 to H_img-1
            if r_img % 10 == 0: check_interrupt("6", request_id)
            for c_img in range(W_img): # 0 to W_img-1
                color = global_image_rgba[r_img, c_img]

                x_o_rel_lens = -(start_x_obj + c_img)
                y_o_rel_lens = start_y_obj + (H_img/2.0 - (r_img+0.5))

                canv_c_obj = int(canvas_width/2 + x_o_rel_lens)
                canv_r_obj = int(canvas_height/2 - y_o_rel_lens)
                if 0 <= canv_r_obj < canvas_height and 0 <= canv_c_obj < canvas_width:
                    plot_canvas[canv_r_obj, canv_c_obj] = color

                u_dist_pixel = start_x_obj + c_img

                if abs(u_dist_pixel - f_val_lens) < 1e-9 or abs(f_val_lens) < 1e-9 or abs(u_dist_pixel) < 1e-9:
                    # Handle cases: object at focal point, zero focal length, or object at lens center for this pixel column
                    # For u_dist_pixel very close to f_val_lens, v_dist_pixel goes to infinity.
                    # For f_val_lens = 0, lens formula is problematic.
                    # For u_dist_pixel = 0 (pixel at lens), magnification formula is problematic.
                    v_dist_pixel = float('inf')
                    magnification = 1 # Default or undefined
                else:
                    v_dist_pixel = (u_dist_pixel * f_val_lens) / (u_dist_pixel - f_val_lens)
                    magnification = -v_dist_pixel / u_dist_pixel

                if v_dist_pixel != float('inf'):
                    x_i_rel_lens = v_dist_pixel
                    y_i_rel_lens = y_o_rel_lens * magnification

                    canv_c_img = int(canvas_width/2 + x_i_rel_lens)
                    canv_r_img = int(canvas_height/2 - y_i_rel_lens) # Y flip for array

                    if 0 <= canv_r_img < canvas_height and 0 <= canv_c_img < canvas_width:
                        plot_canvas[canv_r_img, canv_c_img] = color
                        # Store coordinates for interpolation bounding box
                        drawn_image_pixel_cols.append(canv_c_img)
                        drawn_image_pixel_rows.append(canv_r_img)

        # SECTION FOR INTERPOLATION (fix_row and fix_col)
        # Helper functions for interpolation (defined within to keep them local)
        def fix_row_on_canvas(current_canvas, row_idx, left_bound, right_bound, channels_count):
            if not (0 <= row_idx < current_canvas.shape[0] and 0 <= left_bound <= right_bound < current_canvas.shape[1] and left_bound < right_bound):
                return

            cols_to_interpolate = np.arange(left_bound, right_bound + 1)
            row_data_slice = current_canvas[row_idx, left_bound:right_bound + 1]

            # A pixel is background if all its channels are close to 1.0
            is_pixel_background = np.all(np.isclose(row_data_slice, 1.0), axis=1)
            non_background_mask = ~is_pixel_background

            if non_background_mask.sum() < 2: # Need at least two non-background points to interpolate
                return

            # Indices of non-background columns within the slice [left_bound, right_bound]
            filled_cols_in_slice = cols_to_interpolate[non_background_mask]

            if filled_cols_in_slice.size < 2 or filled_cols_in_slice[0] == filled_cols_in_slice[-1]: # Not enough span
                return

            # Columns over which interpolation will actually occur (from first to last non-background point)
            interpolation_target_cols = np.arange(filled_cols_in_slice[0], filled_cols_in_slice[-1] + 1)

            for ch_idx in range(channels_count):
                # Known points for interpolation for the current channel
                xp_known = filled_cols_in_slice
                fp_known = row_data_slice[non_background_mask, ch_idx]

                interpolated_channel_data = np.interp(interpolation_target_cols, xp_known, fp_known)
                current_canvas[row_idx, interpolation_target_cols, ch_idx] = interpolated_channel_data

        def fix_col_on_canvas(current_canvas, col_idx, top_bound, bottom_bound, channels_count):
            if not (0 <= col_idx < current_canvas.shape[1] and 0 <= top_bound <= bottom_bound < current_canvas.shape[0] and top_bound < bottom_bound):
                return

            rows_to_interpolate = np.arange(top_bound, bottom_bound + 1)
            col_data_slice = current_canvas[top_bound:bottom_bound + 1, col_idx]

            is_pixel_background = np.all(np.isclose(col_data_slice, 1.0), axis=1)
            non_background_mask = ~is_pixel_background

            if non_background_mask.sum() < 2:
                return

            filled_rows_in_slice = rows_to_interpolate[non_background_mask]

            if filled_rows_in_slice.size < 2 or filled_rows_in_slice[0] == filled_rows_in_slice[-1]:
                return

            interpolation_target_rows = np.arange(filled_rows_in_slice[0], filled_rows_in_slice[-1] + 1)

            for ch_idx in range(channels_count):
                xp_known = filled_rows_in_slice
                fp_known = col_data_slice[non_background_mask, ch_idx]

                interpolated_channel_data = np.interp(interpolation_target_rows, xp_known, fp_known)
                current_canvas[interpolation_target_rows, col_idx, ch_idx] = interpolated_channel_data

        # Apply interpolation if image pixels were drawn
        if drawn_image_pixel_cols and drawn_image_pixel_rows:
            min_img_c_bound = max(0, int(min(drawn_image_pixel_cols)))
            max_img_c_bound = min(canvas_width - 1, int(max(drawn_image_pixel_cols)))
            min_img_r_bound = max(0, int(min(drawn_image_pixel_rows)))
            max_img_r_bound = min(canvas_height - 1, int(max(drawn_image_pixel_rows)))

            # Ensure there's a valid range to interpolate over
            if max_img_c_bound > min_img_c_bound and max_img_r_bound > min_img_r_bound:
                # logging.info(f"Task 6: Interpolating image columns from {min_img_c_bound} to {max_img_c_bound}")
                for c_interpolate_idx in range(min_img_c_bound, max_img_c_bound + 1):
                    if (c_interpolate_idx - min_img_c_bound) % 20 == 0: # Check interrupt periodically
                        check_interrupt("6", request_id)
                    fix_col_on_canvas(plot_canvas, c_interpolate_idx, min_img_r_bound, max_img_r_bound, num_channels_on_canvas)

                # logging.info(f"Task 6: Interpolating image rows from {min_img_r_bound} to {max_img_r_bound}")
                for r_interpolate_idx in range(min_img_r_bound, max_img_r_bound + 1):
                    if (r_interpolate_idx - min_img_r_bound) % 20 == 0: # Check interrupt periodically
                        check_interrupt("6", request_id)
                    fix_row_on_canvas(plot_canvas, r_interpolate_idx, min_img_c_bound, max_img_c_bound, num_channels_on_canvas)
        # END OF INTERPOLATION SECTION

        # Clip canvas values to [0,1] as interpolation might slightly exceed this range
        plot_canvas = np.clip(plot_canvas, 0.0, 1.0)

        # Dynamically import Figure and FigureCanvas if not already globally available
        # Or ensure they are imported at the top of the file.
        # For this snippet, assuming they are available in the scope.
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvas
        import io # Ensure io is imported
        import logging # Ensure logging is imported

        fig = Figure(figsize=(8,6)) # Adjust figsize as needed
        ax = fig.add_subplot(111)

        plot_xmin, plot_xmax = -canvas_width/2, canvas_width/2
        plot_ymin, plot_ymax = -canvas_height/2, canvas_height/2

        # Use origin='lower' to have (plot_xmin, plot_ymin) at the bottom-left
        ax.imshow(plot_canvas, extent=[plot_xmin, plot_xmax, plot_ymin, plot_ymax], aspect='auto', origin='lower', interpolation='nearest')

        ax.axvline(x=0, color="blue", linestyle="--", lw=1, label="Lens Plane")
        ax.scatter([f_val_lens, -f_val_lens], [0, 0], color="red", marker="x", s=50, label=f"Foci (f={f_val_lens:.0f})", zorder=5)

        ax.set_xlim(plot_xmin, plot_xmax)
        ax.set_ylim(plot_ymin, plot_ymax)
        ax.set_title(f"Converging Lens: Obj Left X (dist from lens)={start_x_obj:.0f}, Obj Y Ctr={start_y_obj:.0f}")
        ax.set_xlabel("X from Lens (px)")
        ax.set_ylabel("Y from Optical Axis (px)")
        ax.legend(fontsize='small', loc='upper right')
        ax.grid(True, linestyle=":", alpha=0.8)
        fig.tight_layout()

        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf) # Use FigureCanvas directly
        buf.seek(0)
        return buf
    except Exception as e:
        # Ensure logging is imported/configured for this to work
        try:
            import logging
            logging.error(f"Task 6 plot error: {e}", exc_info=True)
        except ImportError:
            print(f"Task 6 plot error: {e}") # Fallback if logging is not set up
        return generate_blank_image() # Ensure generate_blank_image is defined

# --- Task 8: New Concave Mirror ---
def transform_points_spherical_aberration_t8(x_o_flat, y_o_flat, R_mirror):
    x_i_flat = np.full_like(x_o_flat, np.nan)
    y_i_flat = np.full_like(y_o_flat, np.nan)
    if R_mirror <= 1e-6: return x_i_flat, y_i_flat

    at_C_mask = np.isclose(x_o_flat, 0) & np.isclose(y_o_flat, 0)
    x_i_flat[at_C_mask], y_i_flat[at_C_mask] = 0, 0
    
    on_axis_mask = ~at_C_mask & np.isclose(y_o_flat, 0)
    if np.any(on_axis_mask):
        x_o_ax = x_o_flat[on_axis_mask]
        den_ax = R_mirror + 2 * x_o_ax 
        x_i_ax = np.full_like(x_o_ax, np.nan)
        safe_ax = ~np.isclose(den_ax, 0)
        x_i_ax[safe_ax] = -x_o_ax[safe_ax] * R_mirror / den_ax[safe_ax] 
        x_i_flat[on_axis_mask], y_i_flat[on_axis_mask] = x_i_ax, 0
    
    general_mask = ~at_C_mask & ~on_axis_mask
    if np.any(general_mask):
        x_o_gen, y_o_gen = x_o_flat[general_mask], y_o_flat[general_mask]
        x_i_calc, y_i_calc = np.full_like(x_o_gen, np.nan), np.full_like(y_o_gen, np.nan)
        
        valid_y_mask = (y_o_gen**2 <= R_mirror**2 + 1e-9)
        if np.any(valid_y_mask):
            x_o_v, y_o_v = x_o_gen[valid_y_mask], y_o_gen[valid_y_mask]
            y_m = y_o_v
            sqrt_arg = R_mirror**2 - y_m**2
            safe_sqrt_mask = sqrt_arg >= -1e-9
            
            if np.any(safe_sqrt_mask):
                x_o_s, y_o_s, y_m_s = x_o_v[safe_sqrt_mask], y_o_v[safe_sqrt_mask], y_m[safe_sqrt_mask]
                x_m_s = -np.sqrt(np.maximum(0, sqrt_arg[safe_sqrt_mask]))

                L_inc_x, N_unit_x, N_unit_y = -1.0, x_m_s / R_mirror, y_m_s / R_mirror
                dot_L_N = L_inc_x * N_unit_x
                L_rfl_x, L_rfl_y = L_inc_x - 2 * dot_L_N * N_unit_x, -2 * dot_L_N * N_unit_y
                
                numerator_t = x_o_s * y_m_s - y_o_s * x_m_s
                denominator_t = L_rfl_x * y_o_s - L_rfl_y * x_o_s
                
                t_intersect = np.full_like(x_o_s, np.nan)
                safe_intersect_mask = ~np.isclose(denominator_t, 0)
                t_intersect[safe_intersect_mask] = numerator_t[safe_intersect_mask] / denominator_t[safe_intersect_mask]
                
                x_i_temp, y_i_temp = x_m_s + t_intersect * L_rfl_x, y_m_s + t_intersect * L_rfl_y
                
                x_i_valid_y, y_i_valid_y = np.full_like(x_o_v, np.nan), np.full_like(y_o_v, np.nan)
                x_i_valid_y[safe_sqrt_mask], y_i_valid_y[safe_sqrt_mask] = x_i_temp, y_i_temp
                x_i_calc[valid_y_mask], y_i_calc[valid_y_mask] = x_i_valid_y, y_i_valid_y
        x_i_flat[general_mask], y_i_flat[general_mask] = x_i_calc, y_i_calc
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
        x_i_flat, y_i_flat = transform_points_spherical_aberration_t8(x_o_mesh.flatten(), y_o_mesh.flatten(), R_val)
        x_i_mesh, y_i_mesh = x_i_flat.reshape(x_o_mesh.shape), y_i_flat.reshape(y_o_mesh.shape)

        fig = Figure(figsize=(9, 7)); ax = fig.add_subplot(111)
        obj_extent = [obj_left_x, obj_left_x + obj_world_width, obj_center_y - obj_world_height/2, obj_center_y + obj_world_height/2]
        ax.imshow(global_image_rgba, extent=obj_extent, origin='upper', aspect='auto', zorder=1)

        mirror_y = np.linspace(-R_val, R_val, 200); mirror_x = -np.sqrt(np.maximum(0, R_val**2 - mirror_y**2))
        ax.plot(mirror_x, mirror_y, 'b-', lw=2, label=f"Mirror (R={R_val:.2f})", zorder=0)
        ax.plot(0,0,'o',ms=7,c='blue',ls='None',label="C(0,0)",zorder=2)
        ax.plot(-R_val/2,0,'x',ms=7,c='red',ls='None',label=f"F(-{R_val/2:.2f},0)",zorder=2)
        ax.plot(-R_val,0,'P',ms=7,c='darkgreen',ls='None',label=f"V(-{R_val:.2f},0)",zorder=2)

        patches, facecolors = [], []
        FILTER_T8, R_sq_tol = 1e-6, R_val**2 + 1e-6
        for r in range(H_obj_img):
            for c in range(W_obj_img):
                verts = [(x_i_mesh[r,c],y_i_mesh[r,c]), (x_i_mesh[r,c+1],y_i_mesh[r,c+1]), 
                         (x_i_mesh[r+1,c+1],y_i_mesh[r+1,c+1]), (x_i_mesh[r+1,c],y_i_mesh[r+1,c])]
                if any(np.isnan(v[0]) or np.isnan(v[1]) for v in verts): continue
                if not all(vx <= FILTER_T8 for vx,vy in verts): continue # Keep only real images to the left or on C-plane
                patches.append(Polygon(verts, closed=True)); facecolors.append(global_image_rgba[r,c])
        if patches:
            coll = PatchCollection(patches, fc=facecolors, ec='none', zorder=1.5, aa=True); ax.add_collection(coll)

        ax.set_title("Task 8: Concave Mirror (Spherical Aberration)"); ax.set_xlabel("x"); ax.set_ylabel("y")
        ax.axhline(0,c='grey',lw=0.5,ls=':'); ax.axvline(0,c='grey',lw=0.5,ls=':')
        
        all_x = [0,-R_val/2,-R_val,obj_extent[0],obj_extent[1]]+list(mirror_x)+list(x_i_flat[~np.isnan(x_i_flat) & (x_i_flat <= FILTER_T8)])
        all_y = [0,0,0,obj_extent[2],obj_extent[3]]+list(mirror_y)+list(y_i_flat[~np.isnan(x_i_flat) & (x_i_flat <= FILTER_T8)])
        if all_x and all_y and any(~np.isnan(all_x)) and any(~np.isnan(all_y)):
            min_x,max_x = np.nanmin(all_x),np.nanmax(all_x); min_y,max_y = np.nanmin(all_y),np.nanmax(all_y)
            min_x=min(min_x,-R_val*1.1); max_x=max(max_x,R_val*0.2); min_y=min(min_y,-R_val*1.1); max_y=max(max_y,R_val*1.1)
            cx,cy=(min_x+max_x)/2,(min_y+max_y)/2; rx,ry=(max_x-min_x)*plot_zoom,(max_y-min_y)*plot_zoom
            min_range=2.2*R_val*plot_zoom; rx=max(rx,min_range if R_val>0 else 1); ry=max(ry,min_range if R_val>0 else 1)
            ax.set_xlim(cx-rx/2,cx+rx/2); ax.set_ylim(cy-ry/2,cy+ry/2)
        else: lim=1.5*(R_val if R_val>0 else 1)*plot_zoom; ax.set_xlim(-lim,lim*0.5); ax.set_ylim(-lim,lim)
        ax.set_aspect('equal','box'); ax.legend(fontsize='small',loc='best'); ax.grid(True,ls=':',alpha=0.8); fig.tight_layout()
        buf = io.BytesIO(); FigureCanvas(fig).print_png(buf); buf.seek(0); return buf
    except Exception as e: logging.error(f"Task 8 plot error: {e}", exc_info=True); return generate_blank_image()

# --- Task 9: New Convex Mirror ---
def transform_points_convex_obj_right_t9(x_o_flat, y_o_flat, R_mirror):
    x_i_flat, y_i_flat = np.full_like(x_o_flat, np.nan), np.full_like(y_o_flat, np.nan)
    if R_mirror <= 0: return x_i_flat, y_i_flat
    valid_obj_mask = x_o_flat > R_mirror # Object to the right of pole V(R,0)
    
    on_axis = valid_obj_mask & np.isclose(y_o_flat, 0)
    if np.any(on_axis):
        x_o_ax = x_o_flat[on_axis]; den = 2*x_o_ax - R_mirror; safe = ~np.isclose(den,0)
        x_i_ax = np.full_like(x_o_ax,np.nan); x_i_ax[safe] = (x_o_ax[safe]*R_mirror)/den[safe]
        x_i_flat[on_axis], y_i_flat[on_axis] = x_i_ax, 0

    off_axis = valid_obj_mask & ~np.isclose(y_o_flat,0) & ((R_mirror**2 - y_o_flat**2) >= -1e-9)
    if np.any(off_axis):
        x_o, y_o = x_o_flat[off_axis], y_o_flat[off_axis]
        x_M = np.sqrt(np.maximum(0, R_mirror**2 - y_o**2))
        den = 2*x_M - R_mirror - 2*x_o; safe = ~np.isclose(den,0)
        x_i, y_i = np.full_like(x_o,np.nan), np.full_like(y_o,np.nan)
        common = np.full_like(x_o,np.nan); common[safe] = -R_mirror / den[safe]
        x_i[safe], y_i[safe] = x_o[safe]*common[safe], y_o[safe]*common[safe]
        x_i_flat[off_axis], y_i_flat[off_axis] = x_i, y_i
    return x_i_flat, y_i_flat

def generate_task9_plot_new(R_val, obj_center_x, obj_center_y, obj_height_factor, plot_zoom, request_id):
    global global_image_rgba, img_height, img_width, img_aspect_ratio
    try:
        check_interrupt("9", request_id)
        if global_image_rgba is None: return generate_blank_image()
        H_img, W_img = img_height, img_width
        obj_h = R_val*obj_height_factor; obj_w = img_aspect_ratio*obj_h
        min_x_center = R_val + obj_w/2 + 0.01*R_val
        obj_center_x = max(obj_center_x, min_x_center)

        x_corn = np.linspace(obj_center_x-obj_w/2,obj_center_x+obj_w/2,W_img+1)
        y_corn = np.linspace(obj_center_y+obj_h/2,obj_center_y-obj_h/2,H_img+1)
        xo_m,yo_m = np.meshgrid(x_corn,y_corn)
        xi_f,yi_f = transform_points_convex_obj_right_t9(xo_m.flatten(),yo_m.flatten(),R_val)
        xi_m,yi_m = xi_f.reshape(xo_m.shape), yi_f.reshape(yo_m.shape)

        fig=Figure(figsize=(9,7)); ax=fig.add_subplot(111); fig.subplots_adjust(left=0.08,right=0.82,top=0.92,bottom=0.1)
        obj_ext = [obj_center_x-obj_w/2,obj_center_x+obj_w/2,obj_center_y-obj_h/2,obj_center_y+obj_h/2]
        ax.imshow(global_image_rgba,extent=obj_ext,origin='upper',aspect='auto',zorder=1.5)

        mir_y = np.linspace(-R_val*0.99,R_val*0.99,200); mir_x = np.sqrt(np.maximum(0,R_val**2-mir_y**2))
        ax.plot(mir_x,mir_y,'g-',lw=2,label=f"Mirror(R={R_val:.2f})",zorder=0)
        ax.plot(0,0,'o',ms=7,c='blue',ls='None',label="C(0,0)",zorder=2)
        ax.plot(R_val/2,0,'x',ms=7,c='darkorange',ls='None',label=f"Fv({R_val/2:.2f},0)",zorder=2)
        ax.plot(R_val,0,'P',ms=7,c='darkgreen',ls='None',label=f"V({R_val:.2f},0)",zorder=2)

        patches,fcolors=[],[]
        for r in range(H_img):
            for c in range(W_img):
                v=[(xi_m[r,c],yi_m[r,c]),(xi_m[r,c+1],yi_m[r,c+1]),
                   (xi_m[r+1,c+1],yi_m[r+1,c+1]),(xi_m[r+1,c],yi_m[r+1,c])]
                if not any(np.isnan(p[0])or np.isnan(p[1])for p in v):
                    patches.append(Polygon(v,closed=True));fcolors.append(global_image_rgba[r,c])
        if patches: ax.add_collection(PatchCollection(patches,fc=fcolors,ec='none',zorder=1,aa=True))
        
        ax.set_title("Task 9: Convex Mirror (Object Right of Pole)");ax.set_xlabel("x");ax.set_ylabel("y")
        ax.axhline(0,c='k',lw=0.8,ls='-');ax.axvline(0,c='dimgrey',lw=0.6,ls=':')
        ax.set_aspect('equal','box');ax.legend(fontsize='medium',loc='upper left',bbox_to_anchor=(1.01,1));ax.grid(True,ls=':',alpha=0.7)

        all_x=[0,R_val/2,R_val]+list(x_corn)+list(xi_f[~np.isnan(xi_f)])+list(mir_x)
        all_y=[0,0,0]+list(y_corn)+list(yi_f[~np.isnan(yi_f)])+list(mir_y)
        if all_x and all_y and any(~np.isnan(all_x)) and any(~np.isnan(all_y)):
            x_min,x_max=np.nanmin(all_x),np.nanmax(all_x);y_min,y_max=np.nanmin(all_y),np.nanmax(all_y)
            cx,cy=(x_min+x_max)/2,(y_min+y_max)/2;span=max(x_max-x_min,y_max-y_min,0.5*R_val)*(1.25)
            s_span=span/plot_zoom;ax.set_xlim(cx-s_span/2,cx+s_span/2);ax.set_ylim(cy-s_span/2,cy+s_span/2)
        else: lim=R_val*1.5/plot_zoom;ax.set_xlim(-lim*0.5,lim*1.5);ax.set_ylim(-lim,lim)
        fig.tight_layout(rect=[0,0,0.80,1])
        buf=io.BytesIO();FigureCanvas(fig).print_png(buf);buf.seek(0);return buf
    except Exception as e: logging.error(f"Task 9 plot error: {e}", exc_info=True); return generate_blank_image()


def generate_task10_plot(Rf, arc_angle, request_id):
    global global_image_rgba, img_width, img_height

    try:
        # plt.close('all') # Optional: Clears any global pyplot state.
                         # Less critical when using Figure objects directly.

        if global_image_rgba is None or img_width == 0 or img_height == 0:
            logging.warning("Task 10: Global image data not available or dimensions are zero.")
            return generate_blank_image()

        # Use numpy's pi
        current_pi = np.pi

        # Calculate the radius of the circle that inscribes the original image
        # This is used as a base unit for the projection.
        inscribed_radius = isqrt(int((img_width / 2) ** 2 + (img_height / 2) ** 2))
        
        # Center of the projection in plot coordinates
        x_center_proj = 0
        y_center_proj = -img_height / 2 # Projection appears to originate below the image's original center

        # Convert arc_angle to radians and calculate start/end angles for the segments
        start_angle_rad = 1.5 * current_pi - np.deg2rad(arc_angle) / 2
        end_angle_rad = 1.5 * current_pi + np.deg2rad(arc_angle) / 2

        fig = Figure(figsize=(8, 8)) # Adjust figsize as needed, (8,8) is a common square size
        ax = fig.add_subplot(111)

        # R_max is used to determine the overall extent of the drawing for setting plot limits
        R_max_factor = Rf + 1

        # Iterate through each row of the source image
        for row_idx in range(img_height):
            if row_idx % 10 == 0: # Check for interrupt less frequently
                check_interrupt("10", request_id)

            # 'fineness' determines how many segments are used to draw the arc for this image row
            num_arc_segments_points = 300
            
            # 'R_here' scales the radius for the current row's arc, creating the depth effect
            current_R_scale = Rf * ((img_height - row_idx - 1) / img_height) + 1

            # Generate points along the arc for the current row
            theta_points = np.linspace(start_angle_rad, end_angle_rad, num_arc_segments_points)
            arc_x_coords = x_center_proj + inscribed_radius * current_R_scale * np.cos(theta_points)
            arc_y_coords = y_center_proj + inscribed_radius * current_R_scale * np.sin(theta_points)

            # Create line segments from the arc points
            arc_segments = []
            for i in range(len(theta_points) - 1):
                p1 = (arc_x_coords[i], arc_y_coords[i])
                p2 = (arc_x_coords[i+1], arc_y_coords[i+1])
                arc_segments.append((p1, p2))

            # Get RGB pixel data for the current row.
            # Assuming global_image_rgba is HxWx4 (RGBA) and float32 in [0,1] range.
            # We'll use the RGB part for coloring the lines.
            source_row_pixels_rgb = global_image_rgba[row_idx, :, :3]

            # Interpolate colors along the arc segments
            # Indices for interpolation matching the number of arc points
            interp_target_indices = np.linspace(0, img_width - 1, num_arc_segments_points)
            interpolated_colors_rgb = np.zeros((num_arc_segments_points, 3), dtype=np.float32)

            for ch_idx in range(3): # R, G, B
                # Source indices are simply 0 to img_width-1
                source_indices = np.arange(img_width)
                interpolated_colors_rgb[:, ch_idx] = np.interp(
                    interp_target_indices, source_indices, source_row_pixels_rgb[:, ch_idx]
                )
            
            # Colors for LineCollection segments are typically at the center of each segment.
            # Average colors of adjacent points.
            # interp_colors_rgb is already in [0,1] float range.
            segment_line_colors = (interpolated_colors_rgb[:-1] + interpolated_colors_rgb[1:]) / 2.0
            segment_line_colors = np.clip(segment_line_colors, 0.0, 1.0) # Ensure colors stay in [0,1]

            lc = LineCollection(arc_segments, colors=segment_line_colors, linewidth=3)
            ax.add_collection(lc)

        # --- Define plot extents ---
        # Extent for displaying the original (flat) image
        original_image_display_extent = [-img_width / 2, img_width / 2, -img_height / 2, img_height / 2]

        # Calculate the bounding box of the drawn anamorphic projection
        # This helps in setting appropriate plot limits.
        # Based on the outermost arc:
        plot_min_x = x_center_proj - inscribed_radius * R_max_factor
        plot_max_x = x_center_proj + inscribed_radius * R_max_factor
        # For Y, consider the full sweep of the arc
        plot_min_y = y_center_proj - inscribed_radius * R_max_factor
        plot_max_y = y_center_proj + inscribed_radius * R_max_factor # Simplification, max sin can be 1

        # Determine overall width and height needed for the plot view
        # The original code used `xtent` and `ytent` based on max absolute values from center
        view_width_abs = max(abs(plot_min_x), abs(plot_max_x))
        view_height_abs = max(abs(plot_min_y), abs(plot_max_y))
        
        # Full width/height of the content area (doubling the max absolute extent from center)
        content_full_width = int(view_width_abs) * 2 + 2 # Add padding
        content_full_height = int(view_height_abs) * 2 + 2 # Add padding
        
        # Define the extent for the background canvas and plot limits, centered at (0,0)
        plot_area_extent = [
            -content_full_width / 2, content_full_width / 2,
            -content_full_height / 2, content_full_height / 2
        ]
        
        # --- Create and display background canvas ---
        bg_canvas_array_height = int(plot_area_extent[3] - plot_area_extent[2])
        bg_canvas_array_width = int(plot_area_extent[1] - plot_area_extent[0])
        
        # Ensure positive dimensions for the background array
        bg_canvas_array_height = max(bg_canvas_array_height, 10) # Min dimension
        bg_canvas_array_width = max(bg_canvas_array_width, 10)  # Min dimension

        num_img_channels = global_image_rgba.shape[2] # e.g., 4 for RGBA
        # Create a white float background canvas
        background_canvas_array = np.ones((bg_canvas_array_height, bg_canvas_array_width, num_img_channels), dtype=np.float32)
        
        # Display the background canvas. 'origin' and 'aspect' are important.
        ax.imshow(background_canvas_array, extent=plot_area_extent, origin='lower', aspect='auto', zorder=-10)
        
        # --- Display the original image (flat) for reference ---
        # Displayed underneath the anamorphic projection or alongside depending on zorder and alpha
        ax.imshow(global_image_rgba, extent=original_image_display_extent, origin='lower', aspect='auto', alpha=0.8, zorder=-5)
        
        # --- Add decorative elements ---
        # Circle indicating the inscribed radius around the projection center
        # plt.Circle is convenient for creating circle patches.
        ref_circle = plt.Circle((x_center_proj, y_center_proj), inscribed_radius,
                                color="dimgray", fill=False, linewidth=1, linestyle='--', label=f"Inscribed R ({inscribed_radius:.0f}px)")
        ax.add_artist(ref_circle)
        
        # Marker for the projection center
        ax.scatter(x_center_proj, y_center_proj, color="red", marker="P", s=100, zorder=5, label="Projection Origin")
        
        # --- Finalize plot appearance ---
        ax.set_xlim(plot_area_extent[0], plot_area_extent[1])
        ax.set_ylim(plot_area_extent[2], plot_area_extent[3])
        
        ax.set_title(f"Anamorphic Projection (Rf Factor: {Rf:.2f}, Arc: {arc_angle:.1f}°)")
        ax.set_xlabel("X Coordinate (pixels)")
        ax.set_ylabel("Y Coordinate (pixels)")
        ax.legend(fontsize='small', loc='best')
        ax.grid(True, linestyle=':', alpha=0.6)
        
        # Equal aspect ratio is crucial for geometric projections to look correct
        ax.set_aspect('equal', adjustable='box')

        fig.tight_layout() # Adjust subplot parameters for a tight layout.
        
        # --- Output to buffer ---
        buf = io.BytesIO()
        FigureCanvas(fig).print_png(buf)
        # plt.close(fig) # Recommended to free memory if fig is not used elsewhere
        
        buf.seek(0)
        return buf
        
    except Exception as e:
        logging.error(f"Task 10 plot generation failed: {e}", exc_info=True)
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
        # Update slider ranges that depend on image dimensions if they are part of interactive_tasks
        interactive_tasks["5"]["sliders"][0]["max"] = int(3 * img_width)
        interactive_tasks["5"]["sliders"][0]["value"] = int(img_width / 10.0 +1)
        interactive_tasks["5"]["sliders"][0]["step"] = max(1,int(img_width/20))
        interactive_tasks["5"]["sliders"][1]["min"] = int(-img_height)
        interactive_tasks["5"]["sliders"][1]["max"] = int(img_height)
        interactive_tasks["5"]["sliders"][1]["step"] = max(1,int(img_height/20))
        interactive_tasks["5"]["sliders"][2]["min"] = int(max(img_width, img_height) * 1.5)
        interactive_tasks["5"]["sliders"][2]["max"] = int(max(img_width, img_height) * 5)
        interactive_tasks["5"]["sliders"][2]["value"] = int(max(img_width, img_height) * 3)

        interactive_tasks["6"]["sliders"][0]["max"] = int(3 * img_width)
        interactive_tasks["6"]["sliders"][0]["value"] = int(1.5*img_width)
        interactive_tasks["6"]["sliders"][0]["step"] = max(1,int(img_width/20))
        interactive_tasks["6"]["sliders"][1]["min"] = -int(1.5 * img_height)
        interactive_tasks["6"]["sliders"][1]["max"] = int(1.5 * img_height)
        interactive_tasks["6"]["sliders"][1]["step"] = max(1,int(img_height/20))
        interactive_tasks["6"]["sliders"][3]["max"] = int(2*img_width)
        interactive_tasks["6"]["sliders"][3]["value"] = int(0.75*img_width)
        interactive_tasks["6"]["sliders"][3]["step"] = max(1,int(img_width/20))
        interactive_tasks["6"]["extra_context"]["img_width"] = img_width
        
        # Task 9 dynamic slider update after image load
        default_R_t9 = interactive_tasks["9"]["sliders"][0]["value"] 
        default_h_factor_t9 = interactive_tasks["9"]["sliders"][3]["value"] 
        initial_obj_height_t9 = default_R_t9 * default_h_factor_t9
        initial_obj_width_t9 = img_aspect_ratio * initial_obj_height_t9 if img_aspect_ratio > 0 else initial_obj_height_t9
        min_obj_x_t9 = default_R_t9 + initial_obj_width_t9 / 2.0 + 0.01 * default_R_t9
        interactive_tasks["9"]["sliders"][1]["min"] = round(min_obj_x_t9, 2) 
        if interactive_tasks["9"]["sliders"][1]["value"] < min_obj_x_t9: # Adjust current value if new min is higher
            interactive_tasks["9"]["sliders"][1]["value"] = round(min_obj_x_t9,2)

    except Exception as e:
        logging.error(f"Error uploading/processing {filename}: {e}", exc_info=True)
        load_and_process_image(DEFAULT_IMAGE_PATH) # Revert to default
    
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
                off_y = float(request.args.get("offset_y", interactive_tasks["5"]["sliders"][1]["value"]))
                can_size = float(request.args.get("canvas_size", interactive_tasks["5"]["sliders"][2]["value"]))
                buf = generate_task5_plot(off_x, off_y, can_size, req_id_param)
            elif task_id == "6":
                st_x = int(request.args.get("start_x", interactive_tasks["6"]["sliders"][0]["value"]))
                st_y = int(request.args.get("start_y", interactive_tasks["6"]["sliders"][1]["value"]))
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
                rf = float(request.args.get("Rf", interactive_tasks["10"]["sliders"][0]["value"]))
                arc = float(request.args.get("arc_angle", interactive_tasks["10"]["sliders"][1]["value"]))
                buf = generate_task10_plot(rf, arc, req_id_param)
            elif task_id == "11d":
                alpha = float(request.args.get("alpha_11d", interactive_tasks["11d"]["sliders"][0]["value"]))
                buf = generate_task11d_plot(alpha, req_id_param)
            elif task_id == "12a":
                theta_i = float(request.args.get("ThetaI", interactive_tasks["12a"]["sliders"][0]["value"]))
                alpha_p = float(request.args.get("alpha", interactive_tasks["12a"]["sliders"][1]["value"]))
                buf = generate_task12a_plot(theta_i, alpha_p, req_id_param)
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
    port = int(os.environ.get("PORT", 10000)) # Default to 10000 for local dev
    # Set debug=False for production if desired, but True is good for development
    app.run(debug=True, host="0.0.0.0", port=port)
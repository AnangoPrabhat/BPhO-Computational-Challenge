import os
import uuid
import time
import random
import math
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.secret_key = "dev_secret_key_for_vision_app_FINAL_TOUCH" # Fixed for dev

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_DIMENSION = 200
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Optical Constants (Distances in meters, Power in Dioptres)
D_RETINA_FIXED_M = 0.017
P_EMMETROPIC_EYE_LENS_POWER_D = 1 / D_RETINA_FIXED_M
EFFECTIVE_PUPIL_DIAMETER_M = 0.004
GAME_OBJECT_DISTANCE_M = 6.0
# MODIFICATION: Set distance to 0 to simplify the model as requested.
# This makes the corrective lens and eye lens act as a single system.
CORRECTIVE_LENS_TO_EYE_LENS_DISTANCE_M = 0.0 

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def resize_image(image_path, output_path, max_dim):
    try:
        img = Image.open(image_path)
        if img.mode != 'RGBA': img = img.convert('RGBA')
        img.thumbnail((max_dim, max_dim))
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"Error resizing image: {e}")
        return False

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'image' not in request.files: return redirect(request.url)
        file = request.files['image']
        if file.filename == '': return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            user_uuid = session.get('user_uuid')
            if not user_uuid:
                user_uuid = str(uuid.uuid4())
                session['user_uuid'] = user_uuid
            
            user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], user_uuid)
            os.makedirs(user_upload_dir, exist_ok=True)
            original_path = os.path.join(user_upload_dir, "original_" + filename)
            resized_path = os.path.join(user_upload_dir, "resized_object.png")
            file.save(original_path)
            if resize_image(original_path, resized_path, MAX_DIMENSION):
                session['uploaded_image_path'] = os.path.join(user_uuid, "resized_object.png")
            return redirect(url_for('index'))

    uploaded_image_display_path = None
    if 'uploaded_image_path' in session:
         uploaded_image_display_path = url_for('static', filename=f"../{app.config['UPLOAD_FOLDER']}/{session['uploaded_image_path']}")
    return render_template('index.html', uploaded_image_display_path=uploaded_image_display_path, MAX_DIMENSION=MAX_DIMENSION)

@app.route('/simulator')
def simulator():
    image_path = session.get('uploaded_image_path')
    image_for_js = url_for('static', filename=f"../{app.config['UPLOAD_FOLDER']}/{image_path}") if image_path else url_for('static', filename='images/default_object.png')
    optical_constants = {
        'd_retina_fixed_m': D_RETINA_FIXED_M,
        'p_emmetropic_eye_lens_power_D': P_EMMETROPIC_EYE_LENS_POWER_D,
        'corrective_lens_to_eye_lens_distance_m': CORRECTIVE_LENS_TO_EYE_LENS_DISTANCE_M,
    }
    return render_template('simulator.html', image_for_js=image_for_js, optical_constants=optical_constants)

@app.route('/game', methods=['GET'])
def game_start():
    # Myopia = Positive Error, Hyperopia = Negative Error
    p_patient_actual_error = round(random.uniform(-4.0, 6.0), 2)
    session['p_patient_actual_error'] = p_patient_actual_error
    session['game_start_time'] = time.time()
    session['game_duration'] = 180 # seconds
    session['tests_conducted'] = 0
    
    patient_statement = "I believe that my vision is close to normal."
    if p_patient_actual_error > 1.0: # Myopia (positive error)
        patient_statement = "I've been having trouble seeing things far away. I think I might be short-sighted (myopic)."
    elif p_patient_actual_error < -1.0: # Hyperopia (negative error)
        patient_statement = "I find it hard to focus on things up close, and sometimes distant objects are blurry too. I might be long-sighted (hyperopic)."

    session['patient_statement'] = patient_statement
    game_constants = {
        'game_object_distance_m': GAME_OBJECT_DISTANCE_M,
        'd_retina_fixed_m': D_RETINA_FIXED_M,
        'p_emmetropic_eye_lens_power_D': P_EMMETROPIC_EYE_LENS_POWER_D,
        'effective_pupil_diameter_m': EFFECTIVE_PUPIL_DIAMETER_M
    }
    return render_template('game.html', game_duration=session['game_duration'], game_constants=game_constants, patient_statement=patient_statement)

def calculate_image_distance_one_lens(object_dist_m, lens_power_D):
    if abs(lens_power_D) < 1e-9: return object_dist_m
    if object_dist_m == float('inf') or object_dist_m == -float('inf') or abs(object_dist_m) > 1e9:
        return 1 / lens_power_D
    if abs(object_dist_m) < 1e-9:
        return 0.0

    term_1_u = 1 / object_dist_m
    denominator = lens_power_D - term_1_u
    if abs(denominator) < 1e-9: return float('inf')
    return 1 / denominator

def get_final_image_for_eye_system(object_dist_m, p_eye_error_D, p_test_lens_D):
    patient_eye_lens_total_power_D = P_EMMETROPIC_EYE_LENS_POWER_D + p_eye_error_D
    u_for_eye_lens_m = object_dist_m 

    if p_test_lens_D is not None and abs(p_test_lens_D) > 1e-6:
        # With the simplified model, the lenses combine.
        combined_lens_power = p_test_lens_D + patient_eye_lens_total_power_D
        v_final_m = calculate_image_distance_one_lens(object_dist_m, combined_lens_power)
    else:
        v_final_m = calculate_image_distance_one_lens(u_for_eye_lens_m, patient_eye_lens_total_power_D)
    
    return v_final_m

def calculate_blurriness_for_game(p_eye_error_D, p_test_lens_D):
    v_final_from_eye_lens_m = get_final_image_for_eye_system(GAME_OBJECT_DISTANCE_M, p_eye_error_D, p_test_lens_D)
    if v_final_from_eye_lens_m == float('inf'): return float('inf')
    dist_f_retina_m = abs(v_final_from_eye_lens_m - D_RETINA_FIXED_M)
    if abs(v_final_from_eye_lens_m) < 1e-9:
        return float('inf') if dist_f_retina_m > 1e-6 else 0.0
        
    blur_metric = dist_f_retina_m * (EFFECTIVE_PUPIL_DIAMETER_M / abs(v_final_from_eye_lens_m))
    return blur_metric

@app.route('/game/ask_patient', methods=['POST'])
def game_ask_patient():
    if 'p_patient_actual_error' not in session: return jsonify({'error': 'Game not started.'}), 400
    time_elapsed = time.time() - session['game_start_time']
    if time_elapsed > session['game_duration']: return jsonify({'error': 'Time is up!'}), 400

    data = request.get_json()
    try:
        p_test1 = float(data.get('lens1_power'))
        p_test2 = float(data.get('lens2_power'))
    except (ValueError, TypeError): return jsonify({'error': 'Lens powers must be numbers.'}), 400

    p_patient_error = session['p_patient_actual_error']
    blur1 = calculate_blurriness_for_game(p_patient_error, p_test1)
    blur2 = calculate_blurriness_for_game(p_patient_error, p_test2)
    
    session['tests_conducted'] = session.get('tests_conducted', 0) + 1
    lens1_is_objectively_better = blur1 < blur2
    diff_blur_abs = abs(blur1 - blur2)
    
    prob_say_other = 0.01; prob_say_same = 0.03
    if diff_blur_abs < 0.00002: prob_say_other = 0.10; prob_say_same = 0.25
    elif diff_blur_abs < 0.0001: prob_say_other = 0.05; prob_say_same = 0.15
    
    rand_choice = random.random()
    feedback = ""
    if rand_choice < prob_say_other:
        feedback = f"The {'second' if lens1_is_objectively_better else 'first'} lens ({p_test2 if lens1_is_objectively_better else p_test1:+.2f}D) seems a bit less blurry. (Patient seems a little unsure)"
    elif rand_choice < (prob_say_other + prob_say_same):
        feedback = f"Hmm, both lenses ({p_test1:+.2f}D and {p_test2:+.2f}D) look quite similar to me."
    else:
        if abs(blur1 - blur2) < 1e-9 :
             feedback = f"Both lenses ({p_test1:+.2f}D and {p_test2:+.2f}D) look identical."
        elif lens1_is_objectively_better:
            feedback = f"The first lens ({p_test1:+.2f}D) looks less blurry than the second ({p_test2:+.2f}D)."
        else:
            feedback = f"The second lens ({p_test2:+.2f}D) looks less blurry than the first ({p_test1:+.2f}D)."
    
    remaining_time = max(0, session['game_duration'] - time_elapsed)
    return jsonify({'feedback': feedback, 'remaining_time': round(remaining_time)})

@app.route('/game/submit_guess', methods=['POST'])
def game_submit_guess():
    if 'p_patient_actual_error' not in session: return jsonify({'error': 'Game not started.'}), 400
    data = request.get_json()
    try: p_guess = float(data.get('guess'))
    except (ValueError, TypeError): return jsonify({'error': 'Invalid guess format.'}), 400

    p_actual_error = session['p_patient_actual_error']
    
    # MODIFICATION: Reverted to simple correction model as requested.
    ideal_correction = -p_actual_error

    difference = abs(p_guess - ideal_correction)
    score_val = float('inf') if abs(difference) < 1e-9 else (1 / difference if difference != 0 else float('inf'))
    score_display = "Infinity" if math.isinf(score_val) else f"{score_val:.2f}"
    win = difference <= 0.25

    results_payload = {
        'actual_error': f"{p_actual_error:+.2f}",
        'ideal_correction': f"{ideal_correction:+.2f}",
        'your_guess': f"{p_guess:+.2f}",
        'difference_from_ideal': f"{difference:+.2f}",
        'score': score_display, 'win': win
    }
    # Clear session data
    for key in ['p_patient_actual_error', 'game_start_time', 'tests_conducted', 'patient_statement']:
        session.pop(key, None)
    return jsonify(results_payload)

@app.route('/game/get_spoiler_blur_info', methods=['POST'])
def get_spoiler_blur_info():
    if 'p_patient_actual_error' not in session:
        return jsonify({"error": "Game session not found or patient data missing."}), 403
    data = request.get_json()
    try: test_lens_power_D = float(data.get('test_lens_power_D', 0.0))
    except ValueError: return jsonify({"error": "Invalid test lens power."}), 400

    p_eye_error_D = session['p_patient_actual_error']
    blur_value = calculate_blurriness_for_game(p_eye_error_D, test_lens_power_D)
    
    if math.isinf(blur_value): blur_display = "Effectively Infinite"
    elif abs(blur_value) < 1e-6 and blur_value !=0 : blur_display = f"{blur_value:.4e}"
    elif blur_value == 0: blur_display = "0.000000 (Perfect Focus)"
    else: blur_display = f"{blur_value:.6f}"

    return jsonify({
        "test_lens_power_D": test_lens_power_D,
        "blurriness_value": blur_display,
        "note": "Lower value = less blur."
    })

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
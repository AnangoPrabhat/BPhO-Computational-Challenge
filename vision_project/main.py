import os
import uuid
import math
import random
import time
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "dev_secret_key_for_vision_app_FINAL_TOUCH"

# Optical Constants (Distances in meters, Power in Dioptres)
D_RETINA_FIXED_M = 0.017
P_EMMETROPIC_EYE_LENS_POWER_D = 1 / D_RETINA_FIXED_M
GAME_OBJECT_DISTANCE_M = 6.0
CORRECTIVE_LENS_TO_EYE_LENS_DISTANCE_M = 0.015

@app.route('/')
def index():
    """Renders the main page with object selection."""
    return render_template('index.html')

@app.route('/simulator')
def simulator():
    """Renders the vision simulator page."""
    object_type = request.args.get('object', 'arrow')
    object_image_url = ''
    if object_type == 'big_ben':
        # MODIFICATION: Use big_ben.jpg
        object_image_url = url_for('static', filename='images/big_ben.jpg')

    optical_constants = {
        'd_retina_fixed_m': D_RETINA_FIXED_M,
        'p_emmetropic_eye_lens_power_D': P_EMMETROPIC_EYE_LENS_POWER_D,
        'game_object_distance_m': GAME_OBJECT_DISTANCE_M,
        'corrective_lens_to_eye_lens_distance_m': CORRECTIVE_LENS_TO_EYE_LENS_DISTANCE_M,
    }
    return render_template('simulator.html',
                           object_image_url=object_image_url,
                           object_type=object_type,
                           optical_constants=optical_constants)

@app.route('/game', methods=['GET'])
def game_start():
    p_patient_actual_error = round(random.uniform(-4.0, 6.0), 2)
    session['p_patient_actual_error'] = p_patient_actual_error
    session['game_start_time'] = time.time()
    session['game_duration'] = 45

    patient_statement = "I believe that my vision is close to normal."
    if p_patient_actual_error > 1.0:
        patient_statement = "I've been having trouble seeing things far away. I think I might be short-sighted (myopic)."
    elif p_patient_actual_error < -1.0:
        patient_statement = "I find it hard to focus on things up close. I might be long-sighted (hyperopic)."

    session['patient_statement'] = patient_statement

    return render_template('game.html', game_duration=session['game_duration'], patient_statement=patient_statement)

def calculate_image_distance(u, P):
    if abs(u) > 1e9: u = float('inf')
    u_inv = (u == float('inf')) and 0 or 1 / u
    if abs(P - u_inv) < 1e-9: return float('inf')
    return 1 / (P - u_inv)

def calculate_blurriness_for_game(p_eye_error_D, p_test_lens_D):
    relaxed_eye_power = P_EMMETROPIC_EYE_LENS_POWER_D + p_eye_error_D
    
    # 1. Image from test lens
    v_lens = calculate_image_distance(GAME_OBJECT_DISTANCE_M, p_test_lens_D)
    
    # 2. Virtual image from test lens becomes object for the eye
    u_eye = -(v_lens - CORRECTIVE_LENS_TO_EYE_LENS_DISTANCE_M)
    
    # 3. Final image from the relaxed eye (no accommodation for distant objects)
    v_final = calculate_image_distance(u_eye, relaxed_eye_power)

    if v_final == float('inf'): return float('inf')
    
    dist_from_retina = abs(v_final - D_RETINA_FIXED_M)
    return dist_from_retina

@app.route('/game/ask_patient', methods=['POST'])
def game_ask_patient():
    if 'p_patient_actual_error' not in session: return jsonify({'error': 'Game not started.'}), 400
    time_elapsed = time.time() - session.get('game_start_time', 0)
    if time_elapsed > session.get('game_duration', 45): return jsonify({'error': 'Time is up!'}), 400

    data = request.get_json()
    try:
        p_test1 = float(data.get('lens1_power'))
        p_test2 = float(data.get('lens2_power'))
    except (ValueError, TypeError): return jsonify({'error': 'Lens powers must be numbers.'}), 400

    p_patient_error = session['p_patient_actual_error']
    blur1 = calculate_blurriness_for_game(p_patient_error, p_test1)
    blur2 = calculate_blurriness_for_game(p_patient_error, p_test2)
    
    lens1_is_better = blur1 < blur2
    diff_blur = abs(blur1 - blur2)
    
    # Probabilistic patient response
    prob_say_other = 0.01; prob_say_same = 0.03
    if diff_blur < 0.0001: prob_say_other = 0.10; prob_say_same = 0.25
    elif diff_blur < 0.0005: prob_say_other = 0.05; prob_say_same = 0.15
    
    rand_choice = random.random()
    if rand_choice < prob_say_other:
        feedback = f"The {'second' if lens1_is_better else 'first'} lens ({p_test2 if lens1_is_better else p_test1:+.2f}D) seems a bit less blurry. (Patient seems a little unsure)"
    elif rand_choice < (prob_say_other + prob_say_same):
        feedback = f"Hmm, both lenses ({p_test1:+.2f}D and {p_test2:+.2f}D) look quite similar to me."
    else:
        if diff_blur < 1e-9 : feedback = f"Both lenses ({p_test1:+.2f}D and {p_test2:+.2f}D) look identical."
        elif lens1_is_better: feedback = f"The first lens ({p_test1:+.2f}D) looks less blurry than the second ({p_test2:+.2f}D)."
        else: feedback = f"The second lens ({p_test2:+.2f}D) looks less blurry than the first ({p_test1:+.2f}D)."
    
    remaining_time = max(0, session['game_duration'] - time_elapsed)
    # NEW: Return patient error for spoiler diagram
    return jsonify({
        'feedback': feedback, 
        'remaining_time': round(remaining_time),
        'patient_error_D': p_patient_error 
    })


@app.route('/game/submit_guess', methods=['POST'])
def game_submit_guess():
    if 'p_patient_actual_error' not in session: return jsonify({'error': 'Game not started.'}), 400
    data = request.get_json()
    try: p_guess = float(data.get('guess'))
    except (ValueError, TypeError): return jsonify({'error': 'Invalid guess format.'}), 400

    p_actual_error = session['p_patient_actual_error']
    ideal_correction = -p_actual_error
    difference = abs(p_guess - ideal_correction)
    score_val = (1 / difference) if difference > 1e-9 else float('inf')
    score_display = "Infinity" if math.isinf(score_val) else f"{score_val:.2f}"
    win = difference <= 0.25

    results = {
        'actual_error': f"{p_actual_error:+.2f}", 'ideal_correction': f"{ideal_correction:+.2f}",
        'your_guess': f"{p_guess:+.2f}", 'difference_from_ideal': f"{difference:+.2f}",
        'score': score_display, 'win': win
    }
    for key in ['p_patient_actual_error', 'game_start_time']: session.pop(key, None)
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
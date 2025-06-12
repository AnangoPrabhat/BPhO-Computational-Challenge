// game_logic.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Element Grab ---
    const gameStartScreen = document.getElementById('gameStartScreen');
    const startGameBtn = document.getElementById('startGameBtn');
    const gameplayScreen = document.getElementById('gameplayScreen');
    const timerDisplay = document.getElementById('timerDisplay');
    const lens1PowerInput = document.getElementById('lens1Power');
    const lens2PowerInput = document.getElementById('lens2Power');
    const askPatientBtn = document.getElementById('askPatientBtn');
    const patientFeedbackDiv = document.getElementById('patientFeedback');
    const finalGuessSection = document.getElementById('finalGuessSection');
    const finalPrescriptionGuessInput = document.getElementById('finalPrescriptionGuess');
    const submitGuessBtn = document.getElementById('submitGuessBtn');
    const gameResultsDiv = document.getElementById('gameResults');
    const actualPatientErrorP = document.getElementById('actualPatientError');
    const idealCorrectionP = document.getElementById('idealCorrection');
    const yourGuessP = document.getElementById('yourGuess');
    const differenceAmountP = document.getElementById('differenceAmount');
    const gameScoreP = document.getElementById('gameScore');
    const winMessageP = document.getElementById('winMessage');

    // Spoiler Elements
    const toggleSpoilerBtn = document.getElementById('toggleSpoilerBtn');
    const spoilerSection = document.getElementById('spoilerSection');
    const lens1Info = document.getElementById('lens1Info');
    const lens2Info = document.getElementById('lens2Info');
    const lens1FocusInfo = document.getElementById('lens1FocusInfo');
    const lens2FocusInfo = document.getElementById('lens2FocusInfo');


    let timerInterval;
    let timeLeft = INITIAL_GAME_DURATION;

    // --- Game Flow ---
    startGameBtn.addEventListener('click', () => {
        gameStartScreen.style.display = 'none';
        gameplayScreen.style.display = 'block';
        startTimer();
    });

    function updateTimerDisplay() {
        const minutes = Math.floor(timeLeft / 60);
        const seconds = timeLeft % 60;
        timerDisplay.textContent = `Time Remaining: ${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function startTimer() {
        updateTimerDisplay();
        timerInterval = setInterval(() => {
            timeLeft--;
            updateTimerDisplay();
            if (timeLeft <= 0) {
                endGameDueToTime();
            }
        }, 1000);
    }
    
    function setControlsState(disabled) {
        askPatientBtn.disabled = disabled;
        lens1PowerInput.disabled = disabled;
        lens2PowerInput.disabled = disabled;
        toggleSpoilerBtn.disabled = disabled;
    }

    function endGameDueToTime() {
        clearInterval(timerInterval);
        timerDisplay.textContent = "Time's Up!";
        setControlsState(true);
        finalGuessSection.style.display = 'block';
    }

    // --- Event Listeners ---
    askPatientBtn.addEventListener('click', async () => {
        askPatientBtn.disabled = true;
        patientFeedbackDiv.textContent = "Asking patient...";
        
        const lens1 = parseFloatSafe(lens1PowerInput.value);
        const lens2 = parseFloatSafe(lens2PowerInput.value);

        try {
            const response = await fetch('/game/ask_patient', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    lens1_power: lens1, 
                    lens2_power: lens2 
                })
            });
            if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
            
            const data = await response.json();
            patientFeedbackDiv.innerHTML = `<strong>Patient says:</strong> ${data.feedback || data.error || 'Unknown response'}`;
            
            // NEW: If we get the patient error, draw the spoiler diagrams
            if (data.patient_error_D !== undefined && typeof drawGameSpoilerDiagrams === 'function') {
                toggleSpoilerBtn.style.display = 'inline-block';
                const configs = [
                    { patient_error_D: data.patient_error_D, test_lens_D: lens1 },
                    { patient_error_D: data.patient_error_D, test_lens_D: lens2 }
                ];
                const results = drawGameSpoilerDiagrams('gameRayCanvas1', 'gameRayCanvas2', configs);
                lens1Info.textContent = `Lens 1 (${lens1.toFixed(2)} D)`;
                lens2Info.textContent = `Lens 2 (${lens2.toFixed(2)} D)`;
                lens1FocusInfo.textContent = results[0].infoText;
                lens2FocusInfo.textContent = results[1].infoText;
            }

            if (data.remaining_time !== undefined && data.remaining_time <= 0 && timeLeft > 0) {
                endGameDueToTime();
            }
        } catch (error) {
            patientFeedbackDiv.textContent = `Network error: ${error.message}`;
        } finally {
            if (timeLeft > 0) askPatientBtn.disabled = false;
        }
    });

    submitGuessBtn.addEventListener('click', async () => {
        submitGuessBtn.disabled = true;
        finalPrescriptionGuessInput.disabled = true;
        clearInterval(timerInterval);
        try {
            const response = await fetch('/game/submit_guess', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ guess: finalPrescriptionGuessInput.value })
            });
            const results = await response.json();
            if (response.ok) {
                actualPatientErrorP.textContent = `Actual Patient Eye Error: ${results.actual_error} D`;
                idealCorrectionP.textContent = `Ideal Corrective Lens: ${results.ideal_correction} D`;
                yourGuessP.textContent = `Your Guessed Corrective Lens: ${results.your_guess} D`;
                differenceAmountP.textContent = `Difference from Ideal: ${results.difference_from_ideal} D`;
                gameScoreP.textContent = `Score: ${results.score}`;
                winMessageP.textContent = results.win ? "Congratulations! You're within ±0.25D - You Win!" : "Close! Try again next time!";
                winMessageP.className = results.win ? 'win-loss-message win' : 'win-loss-message loss';
                gameResultsDiv.style.display = 'block';
                finalGuessSection.style.display = 'none';
                setControlsState(true);
            } else {
                patientFeedbackDiv.textContent = `Error submitting: ${results.error || 'Unknown error.'}`;
                if (timeLeft > 0) { submitGuessBtn.disabled = false; finalPrescriptionGuessInput.disabled = false; }
            }
        } catch (error) {
            patientFeedbackDiv.textContent = `Network error: ${error.message}`;
            if (timeLeft > 0) { submitGuessBtn.disabled = false; finalPrescriptionGuessInput.disabled = false; }
        }
    });
    
    toggleSpoilerBtn.addEventListener('click', () => {
        spoilerSection.style.display = (spoilerSection.style.display === 'none') ? 'block' : 'none';
    });
});
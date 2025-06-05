// game_logic.js
document.addEventListener('DOMContentLoaded', () => {
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

    // New Spoiler Blur Elements
    const toggleSpoilerBlurBtn = document.getElementById('toggleSpoilerBlurBtn');
    const spoilerBlurContainer = document.getElementById('spoilerBlurContainer');
    const spoilerTestLensPowerInput = document.getElementById('spoilerTestLensPower');
    const getSpoilerBlurBtn = document.getElementById('getSpoilerBlurBtn');
    const spoilerBlurResultP = document.getElementById('spoilerBlurResult');

    let timerInterval;
    let timeLeft = INITIAL_GAME_DURATION;

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
            if (timeLeft <= 0) endGameDueToTime();
        }, 1000);
    }

    function endGameDueToTime() {
        clearInterval(timerInterval);
        timerDisplay.textContent = "Time's Up!";
        askPatientBtn.disabled = true;
        lens1PowerInput.disabled = true;
        lens2PowerInput.disabled = true;
        finalGuessSection.style.display = 'block';
        submitGuessBtn.disabled = false;
        finalPrescriptionGuessInput.disabled = false;
        toggleSpoilerBlurBtn.disabled = true; // Disable spoiler when time is up
        getSpoilerBlurBtn.disabled = true;
    }

    askPatientBtn.addEventListener('click', async () => {
        askPatientBtn.disabled = true;
        patientFeedbackDiv.textContent = "Asking patient...";
        try {
            const response = await fetch('/game/ask_patient', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    lens1_power: parseFloatSafe(lens1PowerInput.value), 
                    lens2_power: parseFloatSafe(lens2PowerInput.value) 
                })
            });
            const data = await response.json();
            patientFeedbackDiv.textContent = `${data.feedback || data.error || 'Unknown response'}`;
            if (data.remaining_time !== undefined && data.remaining_time <= 0 && timeLeft > 0) endGameDueToTime();
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
                winMessageP.textContent = results.win ? "🎉 Congratulations! You're within ±0.25D - You Win! 🎉" : "Close! Try again next time!";
                winMessageP.className = results.win ? 'win-loss-message win' : 'win-loss-message loss';
                gameResultsDiv.style.display = 'block';
                finalGuessSection.style.display = 'none';
                askPatientBtn.disabled = true;
                toggleSpoilerBlurBtn.disabled = true;
                getSpoilerBlurBtn.disabled = true;
            } else {
                patientFeedbackDiv.textContent = `Error submitting: ${results.error || 'Unknown error.'}`;
                if (timeLeft > 0) { submitGuessBtn.disabled = false; finalPrescriptionGuessInput.disabled = false; }
            }
        } catch (error) {
            patientFeedbackDiv.textContent = `Network error: ${error.message}`;
            if (timeLeft > 0) { submitGuessBtn.disabled = false; finalPrescriptionGuessInput.disabled = false; }
        }
    });

    // New Spoiler Blur Logic
    toggleSpoilerBlurBtn.addEventListener('click', () => {
        spoilerBlurContainer.style.display = spoilerBlurContainer.style.display === 'none' ? 'block' : 'none';
    });

    getSpoilerBlurBtn.addEventListener('click', async () => {
        const testLensPower = parseFloatSafe(spoilerTestLensPowerInput.value);
        getSpoilerBlurBtn.disabled = true;
        spoilerBlurResultP.textContent = "Calculating blur...";
        try {
            const response = await fetch('/game/get_spoiler_blur_info', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({test_lens_power_D: testLensPower})
            });
            const data = await response.json();
            if (response.ok) {
                spoilerBlurResultP.textContent = `For Test Lens ${data.test_lens_power_D.toFixed(2)}D: Blurriness ≈ ${data.blurriness_value}. (${data.note})`;
            } else {
                spoilerBlurResultP.textContent = `Error: ${data.error || response.statusText}`;
            }
        } catch (err) {
            spoilerBlurResultP.textContent = `Network error: ${err.message}`;
        } finally {
             if (timeLeft > 0) getSpoilerBlurBtn.disabled = false; // Re-enable if game still active
        }
    });

    // Initialize
    if (gameplayScreen) gameplayScreen.style.display = 'none'; // Ensure gameplay screen is hidden initially
    if (gameStartScreen) gameStartScreen.style.display = 'block';
});
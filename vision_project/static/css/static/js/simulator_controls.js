// simulator_controls.js
document.addEventListener('DOMContentLoaded', () => {
    // Ensure this runs AFTER simulator_draw.js has defined initializeSimulatorCoreConstants
    // and OPTICAL_CONSTANTS is available from the HTML.

    const inherentErrorInput = document.getElementById('inherentError');
    const objectDistanceSlider = document.getElementById('objectDistance');
    const objectDistanceVal = document.getElementById('objectDistanceVal');
    const objectYOffsetSlider = document.getElementById('objectYOffset'); // Now expects world units
    const objectYOffsetVal = document.getElementById('objectYOffsetVal');

    const modeUncorrectedRadio = document.getElementById('modeUncorrected');
    const modeManualRadio = document.getElementById('modeManual');
    const manualLensPowerInput = document.getElementById('manualLensPower');
    const modePrescriptionRadio = document.getElementById('modePrescription');
    const glassesRxInput = document.getElementById('glassesRx');
    const shiftRxSlider = document.getElementById('shiftRx');
    const shiftRxVal = document.getElementById('shiftRxVal');
    const updateBtn = document.getElementById('updateSimulationBtn');

    let firstDrawAttempted = false;

    window.requestRedraw = function() {
        if (!firstDrawAttempted) { // On very first call, ensure constants are set
            if (typeof initializeSimulatorCoreConstants === 'function' && !window.simulatorConstantsInitializedGlobalFlag) {
                if (!initializeSimulatorCoreConstants()) {
                    console.error("Simulator core constants failed to initialize via requestRedraw. Drawing aborted.");
                    return; 
                }
                window.simulatorConstantsInitializedGlobalFlag = true;
            } else if (!window.simulatorConstantsInitializedGlobalFlag) {
                console.warn("requestRedraw called but core constants not ready (initializeSimulatorCoreConstants not found or flag not set).");
                return;
            }
        }
        firstDrawAttempted = true;


        const config = {
            inherentError: parseFloatSafe(inherentErrorInput.value),
            objectDistance: parseFloatSafe(objectDistanceSlider.value, 1),
            objectYOffset: parseFloatSafe(objectYOffsetSlider.value), // Now directly world units (meters)
            lensMode: document.querySelector('input[name="lensMode"]:checked').value,
            manualLensPower: parseFloatSafe(manualLensPowerInput.value),
            glassesRx: parseFloatSafe(glassesRxInput.value),
            shiftRx: parseFloatSafe(shiftRxSlider.value)
        };
        if (config.objectDistance <= 0) config.objectDistance = 0.001; // Avoid zero/negative

        if (typeof drawSimulation === 'function') {
            drawSimulation(config);
        } else {
            console.error("drawSimulation function is not defined at time of call in requestRedraw.");
        }
    }

    function updateSliderValueDisplay(slider, displayElement) {
        let unit = "";
        if (slider === objectDistanceSlider) unit = " m";
        else if (slider === shiftRxSlider) unit = " D";
        else if (slider === objectYOffsetSlider) unit = " m (world offset)"; // Y offset is now in meters
        displayElement.textContent = `${parseFloat(slider.value).toFixed(slider === objectYOffsetSlider ? 3:1)}${unit}`;
    }
    
    // Setup event listeners
    [objectDistanceSlider, objectYOffsetSlider, shiftRxSlider].forEach(slider => {
        if (slider) {
            const display = document.getElementById(slider.id + 'Val');
            if (display) {
                slider.addEventListener('input', () => {
                    updateSliderValueDisplay(slider, display);
                    window.requestRedraw();
                });
                updateSliderValueDisplay(slider, display); // Initial display
            }
        }
    });

    [inherentErrorInput, manualLensPowerInput, glassesRxInput].forEach(input => {
        if (input) input.addEventListener('change', window.requestRedraw);
    });
    
    function toggleLensModeControlsAndRedraw() {
        if(manualLensPowerInput) manualLensPowerInput.disabled = !modeManualRadio.checked;
        if(glassesRxInput) glassesRxInput.disabled = !modePrescriptionRadio.checked;
        if(shiftRxSlider) shiftRxSlider.disabled = !modePrescriptionRadio.checked;
        window.requestRedraw();
    }

    if (modeUncorrectedRadio) modeUncorrectedRadio.onchange = toggleLensModeControlsAndRedraw;
    if (modeManualRadio) modeManualRadio.onchange = toggleLensModeControlsAndRedraw;
    if (modePrescriptionRadio) modePrescriptionRadio.onchange = toggleLensModeControlsAndRedraw;
    if (updateBtn) updateBtn.addEventListener('click', window.requestRedraw);

    // Initial setup and draw
    // Ensure OPTICAL_CONSTANTS are loaded from HTML first by script order
    // Then simulator_draw.js runs and defines initializeSimulatorCoreConstants
    // Then this script runs.
    if (typeof initializeSimulatorCoreConstants === 'function') {
        if (initializeSimulatorCoreConstants()) { // This initializes EYE_LENS_WORLD_X etc.
            window.simulatorConstantsInitializedGlobalFlag = true;
            console.log("Core constants initialized by controls.js, proceeding with first draw setup.");
            if (modeManualRadio) toggleLensModeControlsAndRedraw(); // This will call requestRedraw -> drawSimulation
            else window.requestRedraw(); // Fallback if toggle function isn't called (e.g. uncorrected is default)
        } else {
            console.error("Initial setup: Simulator core constants FAILED to initialize. Simulator will likely not draw correctly.");
        }
    } else {
        console.error("CRITICAL: initializeSimulatorCoreConstants function from simulator_draw.js not found during initial setup. Check script load order.");
        // Attempt to show an error on canvas if possible
        if (ctx) {
            ctx.save(); ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,canvasWidth,canvasHeight);
            ctx.fillStyle="darkred"; ctx.font="bold 14px Arial"; ctx.textAlign="center";
            ctx.fillText("Error: Simulator script did not load correctly. Check console (F12).", canvasWidth/2, canvasHeight/2);
            ctx.restore();
        }
    }
    console.log("Simulator controls initialized.");
});
// simulator_controls.js - Updated for simplified UI and input clamping

"use strict";

document.addEventListener('DOMContentLoaded', () => {
    const inherentErrorInput = document.getElementById('inherentError');
    const glassesRxInput = document.getElementById('glassesRx');

    // This is the single entry point for updating the simulation
    window.requestRedraw = () => {
        if(typeof window.drawSimulation !== 'function') {
            setTimeout(window.requestRedraw, 50);
            return;
        }

        const config = {
            inherentError: parseFloatSafe(inherentErrorInput.value),
            objectDistance: parseFloat(document.getElementById('objectDistance').value) || 1,
            lensMode: document.querySelector('input[name="lensMode"]:checked').value,
            glassesRx: parseFloat(glassesRxInput.value) || 0
        };
        
        window.drawSimulation(config);
    }

    // --- Event Listeners Setup ---
    
    // Add clamping for the inherent error input
    inherentErrorInput.addEventListener('change', () => {
        let value = parseFloatSafe(inherentErrorInput.value);
        const min = -40;
        const max = 40;
        if (value < min) {
            value = min;
        } else if (value > max) {
            value = max;
        }
        inherentErrorInput.value = value;
        window.requestRedraw();

        

        
    });

    glassesRxInput.addEventListener('change', () => {
        let value = parseFloatSafe(glassesRxInput.value);
        const min = -40;
        const max = 40;
        if (value < min) {
            value = min;
        } else if (value > max) {
            value = max;
        }
        glassesRxInput.value = value;
        window.requestRedraw();

        

        
    });

    // Controls that trigger a redraw
    const redrawControls = [
        'inherentError', 'objectDistance', 'glassesRx', 
        'modeUncorrected', 'modeGlasses'
    ];
    redrawControls.forEach(id => {
        const el = document.getElementById(id);
        if(el) el.addEventListener('input', window.requestRedraw);
    });

    // Slider value display
    const objectDistanceSlider = document.getElementById('objectDistance');
    const objectDistanceVal = document.getElementById('objectDistanceVal');
    objectDistanceSlider.addEventListener('input', () => {
        objectDistanceVal.textContent = `${parseFloat(objectDistanceSlider.value).toFixed(1)} m`;
    });
    
    // Enable/disable glasses Rx input based on mode
    document.querySelectorAll('input[name="lensMode"]').forEach(radio => {
        radio.addEventListener('change', () => {
            if (glassesRxInput) {
                glassesRxInput.disabled = (document.getElementById('modeUncorrected').checked);
            }
             window.requestRedraw();
        });
    });

    // Initial setup call
    console.log("Simulator controls initialized.");
    // Set initial state for disabled inputs
    glassesRxInput.disabled = true; 
    window.requestRedraw();
});

// Helper function in case it's not globally available yet
function parseFloatSafe(value, defaultValue = 0.0) {
    const num = parseFloat(value);
    return isNaN(num) ? defaultValue : num;
}
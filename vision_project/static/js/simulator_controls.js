// simulator_controls.js - Updated for simplified UI

"use strict";

document.addEventListener('DOMContentLoaded', () => {
    // This is the single entry point for updating the simulation
    window.requestRedraw = () => {
        if(typeof window.drawSimulation !== 'function') {
            // If the main drawing script isn't ready, try again shortly.
            // This can happen on initial load.
            setTimeout(window.requestRedraw, 50);
            return;
        }

        const config = {
            inherentError: parseFloat(document.getElementById('inherentError').value) || 0,
            objectDistance: parseFloat(document.getElementById('objectDistance').value) || 1,
            lensMode: document.querySelector('input[name="lensMode"]:checked').value,
            glassesRx: parseFloat(document.getElementById('glassesRx').value) || 0
        };
        
        window.drawSimulation(config);
    }

    // --- Event Listeners Setup ---
    
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
    const glassesRxInput = document.getElementById('glassesRx');
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
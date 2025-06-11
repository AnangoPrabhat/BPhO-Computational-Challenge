// simulator_draw.js - v3 - Corrected Scaling, Simplified Model, and UI Fixes

"use strict";

document.addEventListener('DOMContentLoaded', () => {
    if (typeof OPTICAL_CONSTANTS === 'undefined') {
        alert("CRITICAL ERROR: Optical constants not loaded.");
        return;
    }

    // --- Canvas and Context Setup ---
    const canvasZoomedOut = document.getElementById('simulatorCanvasZoomedOut');
    const ctxZoomedOut = canvasZoomedOut ? canvasZoomedOut.getContext('2d') : null;
    const canvasZoomedIn = document.getElementById('simulatorCanvasZoomedIn');
    const ctxZoomedIn = canvasZoomedIn ? canvasZoomedIn.getContext('2d') : null;
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');

    if (!ctxZoomedOut || !ctxZoomedIn) {
        console.error("One or both canvases failed to initialize.");
        return;
    }

    const canvasWidth = canvasZoomedIn.width;
    const canvasHeight = canvasZoomedIn.height;
    
    // --- World Constants & State ---
    const PIXELS_PER_METER = 10000;
    let EYE_LENS_WORLD_X, RETINA_WORLD_X;
    const OBJECT_VISUAL_HEIGHT_WORLD = 0.02;
    let simulatorConstantsInitialized = false;

    // --- Detail View State ---
    let panX_manual = 0;
    let panY_manual = 0;
    let zoomLevel_manual = 15.0; // Start significantly zoomed in
    let isPanning = false;
    let lastPanX_screen, lastPanY_screen;

    // --- Initialization ---
    function initializeSimulator() {
        if (simulatorConstantsInitialized) return true;
        EYE_LENS_WORLD_X = OPTICAL_CONSTANTS.corrective_lens_to_eye_lens_distance_m;
        RETINA_WORLD_X = EYE_LENS_WORLD_X + OPTICAL_CONSTANTS.d_retina_fixed_m;
        
        // Center the detail view on the lens system
        const targetWorldX = EYE_LENS_WORLD_X / 2;
        panX_manual = (canvasWidth / 2) - (targetWorldX * PIXELS_PER_METER * zoomLevel_manual);
        panY_manual = (canvasHeight / 2); // Optical axis is centered vertically

        simulatorConstantsInitialized = true;
        return true;
    }

    // --- Calculation ---
    function calculateThinLensImage(u, h, P) {
        if (Math.abs(P) < 1e-9) return { v: u, h_img: h };
        const u_inv = (Math.abs(u) > 1e9 || !Number.isFinite(u)) ? 0 : 1 / u;
        if (Math.abs(P - u_inv) < 1e-9) return { v: Infinity, h_img: Infinity };
        const v = 1 / (P - u_inv);
        const mag = (Math.abs(u) < 1e-9 || !Number.isFinite(u)) ? 1.0 : (v / u);
        return { v: v, h_img: h * mag, mag: mag };
    }

    function getSceneData(config) {
        const eyePower = OPTICAL_CONSTANTS.p_emmetropic_eye_lens_power_D + config.inherentError;
        const glassesPower = (config.lensMode === 'glasses') ? config.glassesRx : 0.0;

        const object = { x: -config.objectDistance, y: 0, h: OBJECT_VISUAL_HEIGHT_WORLD };
        
        // With the simplified model, lenses are at the same place (x=0) and their powers add up.
        const combinedPower = eyePower + glassesPower;
        
        const finalImage = calculateThinLensImage(config.objectDistance, object.h, combinedPower);
        finalImage.x = finalImage.v;

        // For visualization, we can calculate the intermediate image from the glasses
        let intermediateImage = null;
        if (config.lensMode === 'glasses' && Math.abs(glassesPower) > 1e-9) {
             intermediateImage = calculateThinLensImage(config.objectDistance, object.h, glassesPower);
             intermediateImage.x = intermediateImage.v;
        }

        return { object, finalImage, intermediateImage, eyePower, glassesPower };
    }
    
    // --- Drawing ---
    function drawScene(ctx, view, scene) {
        ctx.save();
        ctx.clearRect(0, 0, canvasWidth, canvasHeight);
        ctx.fillStyle = "#f8f9fa";
        ctx.fillRect(0, 0, canvasWidth, canvasHeight);

        // Set origin to center-left and apply pan/zoom
        ctx.translate(view.panX, view.panY);
        ctx.scale(view.zoom, view.zoom);
        
        const axisY = 0; // Optical axis is now at y=0 in our transformed space
        const PPM = PIXELS_PER_METER;

        // Draw Optical Axis
        ctx.lineWidth = 1 / view.zoom;
        ctx.strokeStyle = '#6c757d';
        ctx.beginPath();
        ctx.moveTo(-1e6, axisY); ctx.lineTo(1e6, axisY);
        ctx.stroke();

        // Draw Retina
        const retinaHeight = 0.04 * PPM;
        ctx.lineWidth = 3 / view.zoom;
        ctx.strokeStyle = '#dc3545';
        ctx.beginPath();
        ctx.moveTo(RETINA_WORLD_X * PPM, -retinaHeight/2);
        ctx.lineTo(RETINA_WORLD_X * PPM, retinaHeight/2);
        ctx.stroke();

        // Draw Object
        const objX = scene.object.x * PPM;
        const objH = scene.object.h * PPM;
        ctx.lineWidth = 2 / view.zoom;
        ctx.strokeStyle = '#28a745';
        const head = objH * 0.25;
        ctx.beginPath();
        ctx.moveTo(objX, axisY); ctx.lineTo(objX, objH);
        ctx.moveTo(objX, objH); ctx.lineTo(objX - head, objH - head);
        ctx.moveTo(objX, objH); ctx.lineTo(objX + head, objH - head);
        ctx.stroke();
        
        // Draw Lenses
        const lensHeight = 0.05 * PPM;
        const lensX = 0; // Both at same location
        const totalPower = scene.eyePower + scene.glassesPower;
        const label = `Lens System (${totalPower.toFixed(2)}D)`;

        ctx.lineWidth = 1.5 / view.zoom;
        ctx.strokeStyle = '#007bff';
        ctx.fillStyle = 'rgba(0, 123, 255, 0.15)';
        ctx.beginPath();
        ctx.moveTo(lensX, -lensHeight/2);
        const curve = lensHeight * 0.1;
        if(totalPower > 0.01) ctx.quadraticCurveTo(lensX + curve, axisY, lensX, lensHeight/2);
        else if(totalPower < -0.01) ctx.quadraticCurveTo(lensX - curve, axisY, lensX, lensHeight/2);
        ctx.lineTo(lensX, -lensHeight/2);
        ctx.closePath();
        ctx.stroke();
        ctx.fill();
        
        // Draw Rays and Images
        // If glasses are on, draw the two-stage process
        if(scene.intermediateImage) {
            // Orange rays: Object -> Intermediate Image
            const i1 = scene.intermediateImage;
            ctx.strokeStyle = '#FF7800'; // Orange
            ctx.lineWidth = 1 / view.zoom;
            ctx.beginPath();
            ctx.moveTo(objX, objH); ctx.lineTo(lensX, objH); // Parallel ray
            if(Number.isFinite(i1.x)) ctx.lineTo(i1.x * PPM, i1.h_img * PPM);
            ctx.moveTo(objX, objH); ctx.lineTo(lensX, axisY); // Center ray
            if(Number.isFinite(i1.x)) ctx.lineTo(i1.x * PPM, i1.h_img * PPM);
            ctx.stroke();
            
            // Purple rays: Intermediate Image -> Final Image
            const i2 = scene.finalImage;
            ctx.strokeStyle = '#B400B4'; // Purple
            ctx.beginPath();
            if(Number.isFinite(i1.x)) {
               ctx.moveTo(lensX, i1.h_img * PPM); // From lens with new height
               if(Number.isFinite(i2.x)) ctx.lineTo(i2.x * PPM, i2.h_img * PPM);
            }
            ctx.stroke();

        } else { // No glasses, just one set of rays
            const i2 = scene.finalImage;
            ctx.strokeStyle = '#B400B4'; // Purple
            ctx.lineWidth = 1 / view.zoom;
            ctx.beginPath();
            ctx.moveTo(objX, objH); ctx.lineTo(lensX, objH);
            if(Number.isFinite(i2.x)) ctx.lineTo(i2.x * PPM, i2.h_img * PPM);
            ctx.moveTo(objX, objH); ctx.lineTo(lensX, axisY);
            if(Number.isFinite(i2.x)) ctx.lineTo(i2.x * PPM, i2.h_img * PPM);
            ctx.stroke();
        }

        // Draw Final Image Point
        const i2 = scene.finalImage;
        if(Number.isFinite(i2.x)) {
            ctx.fillStyle = 'darkblue';
            ctx.beginPath();
            ctx.arc(i2.x * PPM, i2.h_img * PPM, 5 / view.zoom, 0, Math.PI * 2);
            ctx.fill();
        }

        ctx.restore();
    }

    // --- Main Orchestrator ---
    window.drawSimulation = (config) => {
        if (!initializeSimulator()) return;
        const scene = getSceneData(config);
        
        // Auto-zoom view calculation
        const xExtents = [scene.object.x, RETINA_WORLD_X];
        if(Number.isFinite(scene.finalImage.x)) xExtents.push(scene.finalImage.x);
        const minX = Math.min(...xExtents), maxX = Math.max(...xExtents);
        const zoomX = (canvasWidth * 0.9) / ((maxX-minX) * PIXELS_PER_METER);
        const autoZoom = Math.min(zoomX, 50);
        const autoPanX = (canvasWidth/2) - (((minX+maxX)/2) * PIXELS_PER_METER * autoZoom);
        
        const autoView = { zoom: autoZoom, panX: autoPanX, panY: canvasHeight/2 };
        drawScene(ctxZoomedOut, autoView, scene);
        
        // Manual view
        const manualView = { zoom: zoomLevel_manual, panX: panX_manual, panY: panY_manual };
        drawScene(ctxZoomedIn, manualView, scene);

        // Update text
        let infoText = "Image formed at infinity.";
        if(Number.isFinite(scene.finalImage.x)){
            const blur = scene.finalImage.x - RETINA_WORLD_X;
            if(Math.abs(blur) < 0.0001) infoText = "Image is sharply focused on the retina! ✅";
            else infoText = `Image focused ${Math.abs(blur*1000).toFixed(1)} mm ${blur < 0 ? 'in front of' : 'behind'} the retina.`;
        }
        document.getElementById('infoDisplay').textContent = infoText;
    };
    
    // --- Event Listeners ---
    function zoomDetail(factor) {
        const worldMouseX = (canvasWidth / 2 - panX_manual) / zoomLevel_manual;
        const worldMouseY = (canvasHeight / 2 - panY_manual) / zoomLevel_manual;
        zoomLevel_manual *= factor;
        zoomLevel_manual = Math.max(0.1, Math.min(zoomLevel_manual, 200));
        panX_manual = canvasWidth / 2 - worldMouseX * zoomLevel_manual;
        panY_manual = canvasHeight / 2 - worldMouseY * zoomLevel_manual;
        window.requestRedraw();
    }
    zoomInBtn.addEventListener('click', () => zoomDetail(1.4));
    zoomOutBtn.addEventListener('click', () => zoomDetail(1/1.4));
    
    canvasZoomedIn.addEventListener('mousedown', (e) => {
        isPanning = true;
        lastPanX_screen = e.clientX;
        lastPanY_screen = e.clientY;
        canvasZoomedIn.style.cursor = 'grabbing';
    });
    canvasZoomedIn.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        panX_manual += e.clientX - lastPanX_screen;
        panY_manual += e.clientY - lastPanY_screen;
        lastPanX_screen = e.clientX;
        lastPanY_screen = e.clientY;
        window.requestRedraw();
    });
    canvasZoomedIn.addEventListener('mouseup', () => { isPanning = false; canvasZoomedIn.style.cursor = 'grab'; });
    canvasZoomedIn.addEventListener('mouseleave', () => { isPanning = false; canvasZoomedIn.style.cursor = 'default'; });
    canvasZoomedIn.addEventListener('wheel', (e) => {
        e.preventDefault();
        zoomDetail(e.deltaY < 0 ? 1.1 : 1/1.1);
    });
});
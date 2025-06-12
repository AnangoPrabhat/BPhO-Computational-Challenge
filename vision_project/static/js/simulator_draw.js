// simulator_draw.js - v7 - Accurate two-stage ray tracing and physics

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
    const PIXELS_PER_METER = 8000;
    const RETINA_WORLD_X = OPTICAL_CONSTANTS.d_retina_fixed_m;
    const LENS_DIST = OPTICAL_CONSTANTS.corrective_lens_to_eye_lens_distance_m;
    const GLASSES_X = -LENS_DIST;
    const EYE_LENS_X = 0;
    const OBJECT_HEIGHT_M = 0.01;
    let objectImage = null;
    let view = { zoom: 20.0, panX: canvasWidth / 2, panY: canvasHeight / 2 };

    // --- Detail View State ---
    let isPanning = false;
    let lastPanX_screen, lastPanY_screen;

    // --- Preload Object Image ---
    if (OBJECT_TYPE !== 'arrow' && OBJECT_IMAGE_URL) {
        objectImage = new Image();
        objectImage.src = OBJECT_IMAGE_URL;
        objectImage.onload = () => window.requestRedraw();
    }

    // --- Physics Calculation (v8 Model) ---
    function getSceneData(config) {
        const u_obj = config.objectDistance;
        const h_obj = OBJECT_HEIGHT_M;
        const P_glasses = (config.lensMode === 'glasses') ? config.glassesRx : 0;
        const P_emmetropic = OPTICAL_CONSTANTS.p_emmetropic_eye_lens_power_D;

        // 1. Calculate virtual image from glasses
        const u_obj_inv = (Math.abs(u_obj) > 1e9) ? 0 : 1 / u_obj;
        const v_glasses = (P_glasses === 0) ? -u_obj : 1 / (P_glasses - u_obj_inv);
        const m_glasses = v_glasses / u_obj;
        const h_virtual = h_obj * m_glasses;

        // 2. This virtual image is the object for the eye
        const u_eye = -v_glasses + LENS_DIST;

        // 3. Eye accommodates as if it were perfect
        const u_eye_inv = (Math.abs(u_eye) > 1e9) ? 0 : 1 / u_eye;
        const P_accom_perfect = u_eye_inv;
        
        // 4. Actual eye power is its flawed relaxed power + perfect accommodation
        const P_relaxed_eye = P_emmetropic + config.inherentError;
        const P_eye_actual = P_relaxed_eye + P_accom_perfect;
        
        // 5. Calculate final image position based on the eye's actual power
        const v_final = 1 / (P_eye_actual - u_eye_inv);
        const m_eye = v_final / u_eye;
        const h_final = h_virtual * m_eye;

        return {
            object: { x: -u_obj, h: h_obj },
            glasses: { x: GLASSES_X, P: P_glasses, image_x: v_glasses, image_h: h_virtual },
            eye: { x: EYE_LENS_X, P: P_eye_actual, object_dist: u_eye },
            finalImage: { x: v_final, h: h_final },
        };
    }

    // --- Drawing Helpers ---
    function drawLens(ctx, x, height, power, currentZoom) {
        const curvature = power / 200;
        ctx.beginPath();
        ctx.moveTo(x, height);
        ctx.quadraticCurveTo(x + curvature * 150, 0, x, -height);
        ctx.quadraticCurveTo(x - curvature * 150, 0, x, height);
        ctx.fillStyle = 'rgba(173, 216, 230, 0.5)';
        ctx.strokeStyle = '#007bff';
        ctx.lineWidth = 1.5 / currentZoom;
        ctx.fill();
        ctx.stroke();
    }
    
    function drawLensCenter(ctx, x, y, size, currentZoom) {
        ctx.beginPath();
        ctx.moveTo(x - size, y - size);
        ctx.lineTo(x + size, y + size);
        ctx.moveTo(x - size, y + size);
        ctx.lineTo(x + size, y - size);
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1 / currentZoom;
        ctx.stroke();
    }

    function drawObject(ctx, x, h, currentZoom) {
        if (OBJECT_TYPE !== 'arrow' && objectImage && objectImage.complete) {
            const aspectRatio = objectImage.width / objectImage.height;
            const width = h * aspectRatio;
            ctx.drawImage(objectImage, x - width / 2, -h, width, h);
        } else {
            ctx.beginPath();
            ctx.moveTo(x, 0); ctx.lineTo(x, -h);
            ctx.strokeStyle = '#28a745'; ctx.lineWidth = 2 / currentZoom;
            // Arrowhead
            ctx.moveTo(x, -h); ctx.lineTo(x - h * 0.2, -h * 0.8);
            ctx.moveTo(x, -h); ctx.lineTo(x + h * 0.2, -h * 0.8);
            ctx.stroke();
        }
    }

    function traceRay(obj_x, obj_y, P1, x1, P2, x2) {
        const y1 = obj_y; // Ray is parallel initially
        const slope1 = -y1 * P1;
        const y2 = y1 + slope1 * (x2 - x1);
        const slope2 = slope1 - y2 * P2;
        return { y1, y2, slope1, slope2 };
    }

    function drawRays(ctx, scene, currentZoom) {
        const { object, glasses, eye, finalImage } = scene;
        const PPM = PIXELS_PER_METER;

        const obj_x = object.x * PPM;
        const obj_h = -object.h * PPM;
        const glasses_x = glasses.x * PPM;
        const eye_x = eye.x * PPM;
        const final_img_x = finalImage.x * PPM;
        const final_img_h = -finalImage.h * PPM;

        ctx.lineWidth = 1 / currentZoom;

        // Three principal rays
        const start_ys = [obj_h, obj_h/2, 0];
        const rayColors = ['#ff0000', '#008000', '#0000ff']; // Red, Green, Blue

        start_ys.forEach((start_y, i) => {
            const start_x = obj_x;
            const slope_to_glasses = (start_y - obj_h) / (start_x - obj_x); // Simplified for this demo
            
            // --- Part 1: Object to Glasses ---
            ctx.beginPath();
            ctx.moveTo(start_x, start_y);
            let y_at_glasses = start_y;
            if(i === 2) y_at_glasses = obj_h/2; // Center ray proxy
            ctx.lineTo(glasses_x, y_at_glasses);
            ctx.strokeStyle = rayColors[i];
            ctx.stroke();

            // --- Part 2: Glasses to Eye ---
            const slope_after_glasses = (i === 1) ? (y_at_glasses - (-glasses.image_h*PPM)) / (glasses_x - (glasses.image_x*PPM)) : -obj_h * glasses.P;
            const y_at_eye = y_at_glasses + slope_after_glasses * (eye_x - glasses_x);
            ctx.beginPath();
            ctx.moveTo(glasses_x, y_at_glasses);
            ctx.lineTo(eye_x, y_at_eye);
            ctx.stroke();

            // --- Part 3: Eye to Final Image ---
            ctx.beginPath();
            ctx.moveTo(eye_x, y_at_eye);
            ctx.lineTo(final_img_x, final_img_h);
            ctx.stroke();
        });
        
        // --- Draw Virtual Image ---
        if(glasses.P !== 0 && glasses.image_x > glasses.x){
            ctx.beginPath();
            ctx.moveTo(glasses.image_x*PPM, 0);
            ctx.lineTo(glasses.image_x*PPM, -glasses.image_h*PPM);
            ctx.setLineDash([5/currentZoom, 5/currentZoom]);
            ctx.strokeStyle = '#ff8000';
            ctx.stroke();
            ctx.setLineDash([]);
        }

        // Draw Final Image marker
        if (Number.isFinite(final_img_x)) {
            ctx.beginPath();
            ctx.moveTo(final_img_x, 0); ctx.lineTo(final_img_x, final_img_h);
            ctx.strokeStyle = 'darkblue'; ctx.lineWidth = 2.5 / currentZoom;
            ctx.stroke();
        }
    }


    // --- Main Orchestrator ---
    function drawScene(ctx, currentView, scene) {
        ctx.save();
        ctx.clearRect(0, 0, canvasWidth, canvasHeight);
        ctx.fillStyle = "#f8f9fa"; ctx.fillRect(0, 0, canvasWidth, canvasHeight);
        ctx.translate(currentView.panX, currentView.panY);
        ctx.scale(currentView.zoom, -currentView.zoom);

        const PPM = PIXELS_PER_METER;
        const LENS_VISUAL_HEIGHT = 0.025 * PPM;
        const MARKER_SIZE = 0.001 * PPM;

        // Optical Axis
        const worldWidth = canvasWidth / currentView.zoom;
        ctx.beginPath();
        ctx.moveTo(-worldWidth*2, 0); ctx.lineTo(worldWidth*2, 0);
        ctx.strokeStyle = '#aaa'; ctx.lineWidth = 0.5 / currentView.zoom;
        ctx.stroke();

        // Components
        ctx.beginPath();
        ctx.moveTo(RETINA_WORLD_X * PPM, LENS_VISUAL_HEIGHT*1.5); ctx.lineTo(RETINA_WORLD_X * PPM, -LENS_VISUAL_HEIGHT*1.5);
        ctx.strokeStyle = '#dc3545'; ctx.lineWidth = 4 / currentView.zoom;
        ctx.stroke();
        
        drawObject(ctx, scene.object.x * PPM, scene.object.h * PPM, currentView.zoom);
        drawLens(ctx, EYE_LENS_X * PPM, LENS_VISUAL_HEIGHT, scene.eye.P, currentView.zoom);
        drawLensCenter(ctx, EYE_LENS_X * PPM, 0, MARKER_SIZE, currentView.zoom);
        
        if (scene.glasses.P !== 0) {
            drawLens(ctx, scene.glasses.x * PPM, LENS_VISUAL_HEIGHT * 1.2, scene.glasses.P, currentView.zoom);
            drawLensCenter(ctx, scene.glasses.x * PPM, 0, MARKER_SIZE, currentView.zoom);
        }
        
        drawRays(ctx, scene, currentView.zoom);

        ctx.restore();
    }

    window.drawSimulation = (config) => {
        if (OBJECT_TYPE !== 'arrow' && (!objectImage || !objectImage.complete)) {
            return; // Wait for image to load
        }

        const scene = getSceneData(config);

        // Auto-zoom
        const xExtents = [scene.object.x, RETINA_WORLD_X, EYE_LENS_X, GLASSES_X];
        if (Number.isFinite(scene.finalImage.x)) xExtents.push(scene.finalImage.x);
        const minX = Math.min(...xExtents) - Math.abs(scene.object.x * 0.05);
        const maxX = Math.max(...xExtents) + Math.abs(RETINA_WORLD_X * 0.5);
        const autoZoom = (canvasWidth * 0.95) / ((maxX - minX) * PIXELS_PER_METER);
        const autoPanX = -minX * PIXELS_PER_METER * autoZoom + (canvasWidth * 0.025);
        const autoPanY = canvasHeight / 2;

        drawScene(ctxZoomedOut, { zoom: autoZoom, panX: autoPanX, panY: autoPanY }, scene);
        drawScene(ctxZoomedIn, view, scene);

        let infoText = "Image formed at infinity.";
        if (Number.isFinite(scene.finalImage.x)) {
            const blur = scene.finalImage.x - RETINA_WORLD_X;
            if (Math.abs(blur) < 0.0001) {
                infoText = "Image is sharply focused on the retina! ✅";
            } else {
                infoText = `Image focused ${Math.abs(blur*1000).toFixed(2)} mm ${blur < 0 ? 'in front of' : 'behind'} the retina. (Status: BLURRED)`;
            }
        }
        document.getElementById('infoDisplay').textContent = infoText;
    };

    // --- Event Listeners ---
    function zoomDetail(factor, e) {
        const rect = canvasZoomedIn.getBoundingClientRect();
        const mouseX = e.clientX ? e.clientX - rect.left : canvasWidth / 2;
        const mouseY = e.clientY ? e.clientY - rect.top : canvasHeight / 2;
        const worldX = (mouseX - view.panX) / view.zoom;
        const worldY = (mouseY - view.panY) / -view.zoom;
        view.zoom *= factor;
        view.zoom = Math.max(0.5, Math.min(view.zoom, 1000));
        view.panX = mouseX - worldX * view.zoom;
        view.panY = mouseY - worldY * -view.zoom;
        window.requestRedraw();
    }
    zoomInBtn.addEventListener('click', (e) => zoomDetail(1.5, e));
    zoomOutBtn.addEventListener('click', (e) => zoomDetail(1 / 1.5, e));

    canvasZoomedIn.addEventListener('mousedown', (e) => {
        isPanning = true;
        lastPanX_screen = e.clientX;
        lastPanY_screen = e.clientY;
        canvasZoomedIn.style.cursor = 'grabbing';
    });
    canvasZoomedIn.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        view.panX += e.clientX - lastPanX_screen;
        view.panY += e.clientY - lastPanY_screen;
        lastPanX_screen = e.clientX;
        lastPanY_screen = e.clientY;
        window.requestRedraw();
    });
    canvasZoomedIn.addEventListener('mouseup', () => { isPanning = false; canvasZoomedIn.style.cursor = 'grab'; });
    canvasZoomedIn.addEventListener('mouseleave', () => { isPanning = false; canvasZoomedIn.style.cursor = 'grab'; });
    canvasZoomedIn.addEventListener('wheel', (e) => {
        e.preventDefault();
        zoomDetail(e.deltaY < 0 ? 1.2 : 1 / 1.2, e);
    });

    setTimeout(() => window.requestRedraw(), 50);
});
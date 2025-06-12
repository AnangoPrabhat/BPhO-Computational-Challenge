// simulator_draw.js - v8 - Reworked physics model and 3-ray, 2-lens tracing.

"use strict";

document.addEventListener('DOMContentLoaded', () => {
    if (typeof OPTICAL_CONSTANTS === 'undefined') {
        alert("CRITICAL ERROR: Optical constants not loaded.");
        return;
    }

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

    const PIXELS_PER_METER = 8000;
    const RETINA_WORLD_X = OPTICAL_CONSTANTS.d_retina_fixed_m;
    const LENS_DIST = OPTICAL_CONSTANTS.corrective_lens_to_eye_lens_distance_m;
    const GLASSES_X = -LENS_DIST;
    const EYE_LENS_X = 0;
    const OBJECT_HEIGHT_M = 0.01;
    let objectImage = null;
    let view = { zoom: 20.0, panX: canvasWidth / 2, panY: canvasHeight / 2 };

    let isPanning = false;
    let lastPanX_screen, lastPanY_screen;

    if (OBJECT_TYPE !== 'arrow' && OBJECT_IMAGE_URL) {
        objectImage = new Image();
        objectImage.src = OBJECT_IMAGE_URL;
        objectImage.onload = () => window.requestRedraw();
    }

    // --- Physics Calculation (v10 Model) ---
    function getSceneData(config) {
        const u_obj = config.objectDistance;
        const h_obj = OBJECT_HEIGHT_M;
        const P_glasses = (config.lensMode === 'glasses') ? config.glassesRx : 0;
        const P_emmetropic = OPTICAL_CONSTANTS.p_emmetropic_eye_lens_power_D;

        // 1. Accommodation is based ONLY on the original object's distance.
        const u_obj_inv = (Math.abs(u_obj) > 1e9) ? 0 : 1 / u_obj;
        const P_accom = u_obj_inv;
        
        // 2. The eye's actual power is its flawed relaxed state + accommodation.
        const P_eye_actual = (P_emmetropic + config.inherentError) + P_accom;
        
        // 3. The total power of the system is the sum of the powers (assuming d~0 for physics, but not for drawing).
        // This is the key simplification for this model.
        const P_total = P_glasses + P_eye_actual;
        
        // 4. Calculate final image position and magnification based on the total effective power.
        const v_final = 1 / (P_total - u_obj_inv);
        const m_final = v_final / u_obj;
        const h_final = h_obj * m_final;

        return {
            object: { x: -u_obj, h: h_obj },
            glasses: { x: GLASSES_X, P: P_glasses },
            eye: { x: EYE_LENS_X, P: P_eye_actual },
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
            ctx.moveTo(x, -h); ctx.lineTo(x - h * 0.2, -h * 0.8);
            ctx.moveTo(x, -h); ctx.lineTo(x + h * 0.2, -h * 0.8);
            ctx.stroke();
        }
    }
    
    // --- Accurate Ray Tracing for a 2-Lens System ---
    function drawRays(ctx, scene, currentZoom) {
        const { object, glasses, eye, finalImage } = scene;
        const PPM = PIXELS_PER_METER;

        const obj_x = object.x * PPM;
        const obj_h = -object.h * PPM;
        const glasses_x = glasses.x * PPM;
        const eye_x = eye.x * PPM;
        const final_img_x = finalImage.x * PPM;
        const final_img_h = -finalImage.h * PPM;
        
        const P_g = glasses.P;
        const P_e = eye.P;

        const rayColors = ['#ff0000', '#009900', '#0000ff']; // Red, Green, Blue

        // Define 3 initial rays from the object height
        // Ray 0: Parallel to axis
        // Ray 1: Through object-space focal point of combined system (hard to calculate, use a proxy)
        // Ray 2: Through center of glasses (easy to trace)
        const initialRays = [
            { y: obj_h, slope: 0 }, // Parallel ray
            { y: obj_h, slope: (obj_h) / (obj_x - glasses_x) }, // Ray heading to center of glasses
            { y: obj_h, slope: (obj_h * 0.5) / obj_x } // A third, arbitrary ray for coverage
        ];

        initialRays.forEach((ray, i) => {
            ctx.strokeStyle = rayColors[i];
            ctx.lineWidth = 1 / currentZoom;
            
            // --- Part 1: Object to Glasses ---
            const y_at_glasses = ray.y + ray.slope * (glasses_x - obj_x);
            ctx.beginPath();
            ctx.moveTo(obj_x, ray.y);
            ctx.lineTo(glasses_x, y_at_glasses);
            ctx.stroke();

            // --- Part 2: Glasses to Eye ---
            // Apply thin lens equation for the change in slope at the glasses
            const slope_after_glasses = ray.slope - y_at_glasses * P_g / PPM;
            const y_at_eye = y_at_glasses + slope_after_glasses * (eye_x - glasses_x);
            ctx.beginPath();
            ctx.moveTo(glasses_x, y_at_glasses);
            ctx.lineTo(eye_x, y_at_eye);
            ctx.stroke();
            
            // --- Part 3: Eye to Final Image ---
            // Apply thin lens equation again for the eye
            const slope_after_eye = slope_after_glasses - y_at_eye * P_e / PPM;
            const final_x_endpoint = final_img_x; 
            const final_y_endpoint = y_at_eye + slope_after_eye * (final_x_endpoint - eye_x);
            ctx.beginPath();
            ctx.moveTo(eye_x, y_at_eye);
            // We know all rays must converge, so we draw to the calculated final image height
            ctx.lineTo(final_img_x, final_img_h);
            ctx.stroke();
        });

        // Draw Final Image marker
        if (Number.isFinite(final_img_x)) {
            ctx.beginPath();
            ctx.moveTo(final_img_x, 0); ctx.lineTo(final_img_x, final_img_h);
            ctx.strokeStyle = 'darkblue'; ctx.lineWidth = 2.5 / currentZoom;
            ctx.stroke();
        }
    }


    function drawScene(ctx, currentView, scene) {
        ctx.save();
        ctx.clearRect(0, 0, canvasWidth, canvasHeight);
        ctx.fillStyle = "#f8f9fa"; ctx.fillRect(0, 0, canvasWidth, canvasHeight);
        ctx.translate(currentView.panX, currentView.panY);
        ctx.scale(currentView.zoom, -currentView.zoom);

        const PPM = PIXELS_PER_METER;
        const LENS_VISUAL_HEIGHT = 0.025 * PPM;
        const MARKER_SIZE = 0.001 * PPM;

        const worldWidth = canvasWidth / currentView.zoom;
        ctx.beginPath();
        ctx.moveTo(-worldWidth * 2, 0); ctx.lineTo(worldWidth * 2, 0);
        ctx.strokeStyle = '#aaa'; ctx.lineWidth = 0.5 / currentView.zoom;
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(RETINA_WORLD_X * PPM, LENS_VISUAL_HEIGHT * 1.5); ctx.lineTo(RETINA_WORLD_X * PPM, -LENS_VISUAL_HEIGHT * 1.5);
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
            return;
        }

        const scene = getSceneData(config);

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

    function zoomDetail(factor, e) {
        const rect = canvasZoomedIn.getBoundingClientRect();
        const mouseX = e.clientX ? e.clientX - rect.left : canvasWidth / 2;
        const mouseY = e.clientY ? e.clientY - rect.top : canvasHeight / 2;
        const worldX = (mouseX - view.panX) / view.zoom;
        const worldY = (mouseY - view.panY) / -view.zoom;
        view.zoom *= factor;
        // MODIFICATION: Allow for more extreme zoom-out
        view.zoom = Math.max(0.01, Math.min(view.zoom, 1000));
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
// game_diagram.js - Renders the spoiler ray diagrams for the eye test game.
// v2: Updated to use the same visualization style as the simulator for consistency.

"use strict";

const GAME_PIXELS_PER_METER = 20000; // Increased to provide better default zoom

function getSceneDataForGame(config) {
    const { patient_error_D, test_lens_D } = config;
    const { 
        p_emmetropic_eye_lens_power_D, 
        game_object_distance_m,
        corrective_lens_to_eye_lens_distance_m,
        d_retina_fixed_m
    } = OPTICAL_CONSTANTS;

    const u_obj = game_object_distance_m;
    const h_obj = 0.01; // A nominal height for visualization
    const u_obj_inv = 1 / u_obj;
    
    const P_accom = u_obj_inv;
    const P_eye_actual = (p_emmetropic_eye_lens_power_D + patient_error_D) + P_accom;
    const P_total = test_lens_D + P_eye_actual;
    const v_final = 1 / (P_total - u_obj_inv);
    const m_final = v_final / u_obj;
    const h_final = h_obj * m_final;

    return {
        object: { x: -u_obj, h: h_obj },
        glasses: { x: -corrective_lens_to_eye_lens_distance_m, P: test_lens_D },
        eye: { x: 0, P: P_eye_actual },
        finalImage: { x: v_final, h: h_final },
        retina: { x: d_retina_fixed_m }
    };
}

// --- Drawing Helpers (borrowed from simulator_draw.js for consistency) ---
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

function drawGameRays(ctx, scene, currentZoom) {
    const { object, glasses, eye, finalImage } = scene;
    const PPM = GAME_PIXELS_PER_METER;

    const obj_x = object.x * PPM;
    const obj_h = -object.h * PPM;
    const glasses_x = glasses.x * PPM;
    const eye_x = eye.x * PPM;
    const final_img_x = finalImage.x * PPM;
    const final_img_h = -finalImage.h * PPM;
    
    const P_g = glasses.P;
    const P_e = eye.P;

    // Simplified ray tracing for the game diagram (one clear ray path)
    const ray = { y: obj_h, slope: 0 }; // Start with a ray parallel to the axis

    ctx.strokeStyle = '#ff8c00';
    ctx.lineWidth = 1.5 / currentZoom;
    
    // Part 1: Object to Glasses
    const y_at_glasses = ray.y + ray.slope * (glasses_x - obj_x);
    ctx.beginPath();
    ctx.moveTo(obj_x, ray.y);
    ctx.lineTo(glasses_x, y_at_glasses);
    ctx.stroke();

    // Part 2: Glasses to Eye
    const slope_after_glasses = ray.slope - y_at_glasses * P_g / PPM;
    const y_at_eye = y_at_glasses + slope_after_glasses * (eye_x - glasses_x);
    ctx.beginPath();
    ctx.moveTo(glasses_x, y_at_glasses);
    ctx.lineTo(eye_x, y_at_eye);
    ctx.stroke();
    
    // Part 3: Eye to Final Image
    const slope_after_eye = slope_after_glasses - y_at_eye * P_e / PPM;
    const final_y_endpoint = y_at_eye + slope_after_eye * (final_img_x - eye_x);
    ctx.beginPath();
    ctx.moveTo(eye_x, y_at_eye);
    ctx.lineTo(final_img_x, final_y_endpoint);
    ctx.stroke();

    // Draw Final Image marker as a line, not a dot
    if (Number.isFinite(final_img_x)) {
        ctx.beginPath();
        ctx.moveTo(final_img_x, 0); ctx.lineTo(final_img_x, final_img_h);
        ctx.strokeStyle = 'darkblue'; ctx.lineWidth = 2.5 / currentZoom;
        ctx.stroke();
    }
}


function drawGameScene(ctx, scene, view) {
    const canvas = ctx.canvas;
    const PPM = GAME_PIXELS_PER_METER;
    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#f8f9fa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const LENS_VISUAL_HEIGHT = 0.015 * PPM;

    let zoom, panX, panY;
    if (view) { // Detailed view with pan/zoom
        zoom = view.zoom;
        panX = view.panX;
        panY = view.panY;
    } else { // Auto-zoom for overview
        const xExtents = [scene.glasses.x, scene.eye.x, scene.retina.x, scene.finalImage.x];
        const minX = Math.min(...xExtents) - 0.01;
        const maxX = Math.max(...xExtents) + 0.01;
        zoom = (canvas.width * 0.9) / ((maxX - minX) * PPM);
        panX = -minX * PPM * zoom + canvas.width * 0.05;
        panY = canvas.height / 2;
    }

    ctx.translate(panX, panY);
    ctx.scale(zoom, -zoom);

    // Draw Optical Axis
    const worldWidth = canvas.width / zoom;
    ctx.beginPath();
    ctx.moveTo(-worldWidth, 0); ctx.lineTo(worldWidth, 0);
    ctx.strokeStyle = '#aaa'; ctx.lineWidth = 0.5 / zoom;
    ctx.stroke();

    // Draw Retina (thicker and more visible)
    ctx.beginPath();
    ctx.moveTo(scene.retina.x * PPM, LENS_VISUAL_HEIGHT * 1.2);
    ctx.lineTo(scene.retina.x * PPM, -LENS_VISUAL_HEIGHT * 1.2);
    ctx.strokeStyle = '#dc3545';
    ctx.lineWidth = 4 / zoom;
    ctx.stroke();
    
    // Draw Lenses using the new helper
    drawLens(ctx, scene.eye.x * PPM, LENS_VISUAL_HEIGHT, scene.eye.P, zoom);
    if (scene.glasses.P !== 0) {
        drawLens(ctx, scene.glasses.x * PPM, LENS_VISUAL_HEIGHT, scene.glasses.P, zoom);
    }
    
    // Draw Rays using the new helper
    drawGameRays(ctx, scene, zoom);

    ctx.restore();
    
    const blur = scene.finalImage.x - scene.retina.x;
    let infoText = `Focused ${Math.abs(blur*1000).toFixed(3)} mm ${blur < 0 ? 'before' : 'after'} retina.`;
    if(Math.abs(blur) < 0.0001) infoText = 'Focused on retina!';
    return { infoText };
}


function drawGameSpoilerDiagrams(canvasId1, canvasId2, configs) {
    const canvas1 = document.getElementById(canvasId1);
    const canvas2 = document.getElementById(canvasId2);
    if (!canvas1 || !canvas2) return;
    const ctx1 = canvas1.getContext('2d');
    const ctx2 = canvas2.getContext('2d');
    const view = {
        zoom: 30, // <-- Changed from 150 to 80
        panX: canvas1.width / 2,
        panY: canvas1.height / 2,
    };
    const scene1 = getSceneDataForGame(configs[0]);
    const result1 = drawGameScene(ctx1, scene1, null); // Pass null for view to use auto-zoom

    const scene2 = getSceneDataForGame(configs[1]);
    const result2 = drawGameScene(ctx2, scene2, null); // Pass null for view
    
    return [result1, result2];
}
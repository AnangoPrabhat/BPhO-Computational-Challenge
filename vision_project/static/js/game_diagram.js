// game_diagram.js - Renders the spoiler ray diagrams for the eye test game.

"use strict";

function getSceneDataForGame(config) {
    const { patient_error_D, test_lens_D } = config;
    const { 
        p_emmetropic_eye_lens_power_D, 
        game_object_distance_m,
        corrective_lens_to_eye_lens_distance_m,
        d_retina_fixed_m
    } = OPTICAL_CONSTANTS;

    const u_obj = game_object_distance_m;
    const u_obj_inv = 1 / u_obj;
    
    // Using the same physics model as the simulator for consistency
    const P_accom = u_obj_inv;
    const P_eye_actual = (p_emmetropic_eye_lens_power_D + patient_error_D) + P_accom;
    const P_total = test_lens_D + P_eye_actual;
    const v_final = 1 / (P_total - u_obj_inv);

    return {
        object: { x: -u_obj, h: 0.01 },
        glasses: { x: -corrective_lens_to_eye_lens_distance_m, P: test_lens_D },
        eye: { x: 0, P: P_eye_actual },
        finalImage: { x: v_final, h: 0.005 },
        retina: { x: d_retina_fixed_m }
    };
}


function drawGameScene(ctx, scene) {
    const canvas = ctx.canvas;
    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#f8f9fa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const xExtents = [scene.object.x, scene.glasses.x, scene.eye.x, scene.retina.x, scene.finalImage.x];
    const minX = Math.min(...xExtents) - Math.abs(scene.object.x * 0.1);
    const maxX = Math.max(...xExtents) + Math.abs(scene.retina.x * 0.5);
    const zoom = canvas.width / (maxX - minX);
    const panX = -minX * zoom;
    const panY = canvas.height / 2;

    ctx.translate(panX, panY);
    ctx.scale(zoom, -zoom); 
    const lineWidth = (maxX-minX) / canvas.width * 1.5;

    ctx.beginPath();
    ctx.moveTo(minX*1.1, 0); ctx.lineTo(maxX*1.1, 0);
    ctx.strokeStyle = '#ccc'; ctx.lineWidth = lineWidth * 0.5;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(scene.retina.x, -0.015); ctx.lineTo(scene.retina.x, 0.015);
    ctx.strokeStyle = '#dc3545'; ctx.lineWidth = lineWidth * 2;
    ctx.stroke();
    
    ctx.beginPath();
    ctx.moveTo(scene.eye.x, -0.012); ctx.lineTo(scene.eye.x, 0.012);
    ctx.strokeStyle = '#007bff'; ctx.lineWidth = lineWidth;
    ctx.stroke();
    
    ctx.beginPath();
    ctx.moveTo(scene.glasses.x, -0.012); ctx.lineTo(scene.glasses.x, 0.012);
    ctx.strokeStyle = '#6c757d'; ctx.lineWidth = lineWidth;
    ctx.stroke();

    ctx.beginPath();
    ctx.strokeStyle = '#ff8c00';
    ctx.lineWidth = lineWidth * 0.75;
    ctx.moveTo(scene.object.x, scene.object.h);
    const y_at_glasses = scene.object.h;
    ctx.lineTo(scene.glasses.x, y_at_glasses);

    const slope_after_glasses = (0 - y_at_glasses) / (scene.finalImage.x - scene.glasses.x); // Simplified
    const y_at_eye = y_at_glasses + slope_after_glasses * (scene.eye.x - scene.glasses.x);
    ctx.lineTo(scene.eye.x, y_at_eye);

    ctx.lineTo(scene.finalImage.x, 0);
    ctx.stroke();
    
    ctx.beginPath();
    ctx.arc(scene.finalImage.x, 0, lineWidth*2, 0, Math.PI * 2);
    ctx.fillStyle = 'darkblue';
    ctx.fill();

    ctx.restore();
    
    const blur = scene.finalImage.x - scene.retina.x;
    // MODIFICATION: Increased decimal places
    let infoText = `Focused ${Math.abs(blur*1000).toFixed(3)} mm ${blur < 0 ? 'before' : 'after'} retina.`;
    if(Math.abs(blur) < 0.0001) infoText = 'Focused on retina!';
    return { infoText };
}


function drawGameSpoilerDiagrams(canvasId1, canvasId2, configs) {
    const canvas1 = document.getElementById(canvasId1);
    const ctx1 = canvas1.getContext('2d');
    const scene1 = getSceneDataForGame(configs[0]);
    const result1 = drawGameScene(ctx1, scene1);

    const canvas2 = document.getElementById(canvasId2);
    const ctx2 = canvas2.getContext('2d');
    const scene2 = getSceneDataForGame(configs[1]);
    const result2 = drawGameScene(ctx2, scene2);
    
    return [result1, result2];
}
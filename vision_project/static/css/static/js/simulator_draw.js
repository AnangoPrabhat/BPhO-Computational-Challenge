// simulator_draw.js - Pan/Zoom and Robust Ray Tracing

// Ensure OPTICAL_CONSTANTS is loaded from HTML before this script runs.
// It's declared via a <script> tag in simulator.html's <head_extra> block.
if (typeof OPTICAL_CONSTANTS === 'undefined') {
    alert("CRITICAL ERROR: Optical constants not loaded. Simulator cannot run. Check HTML template and console.");
    console.error("OPTICAL_CONSTANTS is undefined. Make sure it's passed correctly from Flask template and the script block order is correct in simulator.html.");
}

const canvas = document.getElementById('simulatorCanvas');
const ctx = canvas ? canvas.getContext('2d') : null;

if (!ctx) {
    alert("CRITICAL ERROR: Canvas context could not be initialized. Simulator cannot run.");
    console.error("Canvas context (ctx) is null. Ensure canvas ID 'simulatorCanvas' is correct and element exists.");
}

const canvasWidth = canvas ? canvas.width : 800;
const canvasHeight = canvas ? canvas.height : 450;

// --- Pan and Zoom State ---
let panX = canvasWidth / 2; 
let panY = canvasHeight / 2;
let zoomLevel = 0.5; // Start a bit zoomed out to see more context initially
let isPanning = false;
let lastPanX_screen, lastPanY_screen;

// --- Drawing parameters ---
let PIXELS_PER_METER = 10000; // Significantly INCREASED for eye detail
const OPTICAL_AXIS_Y_WORLD = 0; 

const CORRECTIVE_LENS_WORLD_X = 0; // Corrective lens at world origin X=0
let EYE_LENS_WORLD_X; 
let RETINA_WORLD_X;   

const LENS_VISUAL_HEIGHT_WORLD = 0.05; // 5cm visual height
const OBJECT_VISUAL_HEIGHT_WORLD = 0.02; // 2cm visual height, can be adjusted

const RAY_COLOR_L1 = 'rgba(255, 120, 0, 0.7)'; // Brighter Orange
const RAY_COLOR_L2 = 'rgba(180, 0, 180, 0.7)'; // Brighter Purple
const IMAGE_POINT_COLOR = 'darkblue'; // More visible image point

let objectImage = new Image();
let objectImageLoaded = false;
let simulatorConstantsInitialized = false;

function initializeSimulatorCoreConstants() {
    if (typeof OPTICAL_CONSTANTS === 'undefined' || OPTICAL_CONSTANTS === null) {
        console.error("initializeSimulatorCoreConstants: OPTICAL_CONSTANTS is still undefined!");
        return false;
    }
    EYE_LENS_WORLD_X = CORRECTIVE_LENS_WORLD_X + OPTICAL_CONSTANTS.corrective_lens_to_eye_lens_distance_m;
    RETINA_WORLD_X = EYE_LENS_WORLD_X + OPTICAL_CONSTANTS.d_retina_fixed_m;
    simulatorConstantsInitialized = true;
    console.log("Simulator core constants INITIALIZED:", {EYE_LENS_WORLD_X, RETINA_WORLD_X, PPM: PIXELS_PER_METER, CL_dist_EL: OPTICAL_CONSTANTS.corrective_lens_to_eye_lens_distance_m, EL_dist_Retina: OPTICAL_CONSTANTS.d_retina_fixed_m});
    return true;
}

// Image Loader
function initSimulatorImage() {
    if (!IMAGE_FOR_JS) {
        console.warn("IMAGE_FOR_JS not defined, cannot load image.");
        // Attempt to draw fallback immediately if requestRedraw is ready
        objectImageLoaded = false; // ensure fallback is used
        if(window.requestRedraw) window.requestRedraw();
        return;
    }
    objectImage.onload = () => { 
        objectImageLoaded = true; 
        console.log("Custom object image loaded:", IMAGE_FOR_JS);
        if(window.requestRedraw) window.requestRedraw(); 
    };
    objectImage.onerror = () => {
        console.warn(`Failed to load custom image: ${IMAGE_FOR_JS}. Using fallback.`);
        objectImage.src = "/static/images/default_object.png"; // Fallback, ensure this is called again on error.
        // Second onload for fallback
        objectImage.onload = () => { 
            objectImageLoaded = true; 
            console.log("Fallback object image loaded.");
            if(window.requestRedraw) window.requestRedraw();
        };
        objectImage.onerror = () => { // Final fallback error
            objectImageLoaded = false; // Will draw placeholder shape
            console.error("CRITICAL: Fallback image also failed to load.");
            if(window.requestRedraw) window.requestRedraw();
        };
    };

    if (IMAGE_FOR_JS.endsWith('default_object.png') || IMAGE_FOR_JS.includes("{{")) { // Check if it's still the template placeholder
        objectImage.src = "/static/images/default_object.png";
    } else {
        objectImage.src = IMAGE_FOR_JS;
    }
}

if (ctx) { // Only initialize if canvas is ready
    initSimulatorImage();
} else {
    console.error("Cannot initialize simulator image: Canvas context not ready.");
}


// --- Drawing Helper Functions ---
function drawLineWorld(currentCtx, x1_w, y1_w, x2_w, y2_w, color = 'black', lineWidth = 1) {
    if (!currentCtx || ![x1_w, y1_w, x2_w, y2_w].every(v => Number.isFinite(v))) {
        // console.warn("Skipping drawLineWorld: Invalid coordinates", {x1_w, y1_w, x2_w, y2_w});
        return;
    }
    currentCtx.beginPath();
    currentCtx.moveTo(x1_w * PIXELS_PER_METER, y1_w * PIXELS_PER_METER);
    currentCtx.lineTo(x2_w * PIXELS_PER_METER, y2_w * PIXELS_PER_METER);
    currentCtx.strokeStyle = color;
    currentCtx.lineWidth = Math.max(0.5, lineWidth / zoomLevel); // Ensure min width
    currentCtx.stroke();
}

function drawTextWorld(currentCtx, text, x_w, y_w, color = 'black', baseFontSize = 10, textAlign = 'left') {
    if (!currentCtx || !Number.isFinite(x_w) || !Number.isFinite(y_w)) return;
    const fontSize = Math.max(5, baseFontSize / zoomLevel); // Min font size
    currentCtx.fillStyle = color;
    currentCtx.font = `${fontSize}px Arial`;
    currentCtx.textAlign = textAlign;
    currentCtx.fillText(text, x_w * PIXELS_PER_METER, y_w * PIXELS_PER_METER);
}

function drawCircleWorld(currentCtx, x_w, y_w, radius_w, color = 'black', fill = true) {
    if (!currentCtx || ![x_w, y_w, radius_w].every(Number.isFinite) || radius_w <=0) return;
    currentCtx.beginPath();
    currentCtx.arc(x_w * PIXELS_PER_METER, y_w * PIXELS_PER_METER, radius_w * PIXELS_PER_METER, 0, 2 * Math.PI);
    if (fill) {
        currentCtx.fillStyle = color;
        currentCtx.fill();
    } else {
        currentCtx.strokeStyle = color;
        currentCtx.lineWidth = Math.max(0.5, 1 / zoomLevel);
        currentCtx.stroke();
    }
}

function clearCanvasAndTransform() {
    if (!ctx) return;
    ctx.save();
    // Reset transform to draw background in screen space
    ctx.setTransform(1, 0, 0, 1, 0, 0); 
    ctx.fillStyle = "#e9f0f8"; // Lighter blue, more subtle
    ctx.fillRect(0, 0, canvasWidth, canvasHeight);
    
    // Apply pan and zoom for subsequent world drawing
    ctx.translate(panX, panY);
    ctx.scale(zoomLevel, zoomLevel);
}

function restoreCanvasTransform() {
    if (!ctx) return;
    ctx.restore();
}

function drawOpticalAxisWorld() {
    if (!ctx) return;
    const RENDER_MARGIN_WORLD = 1.0; // Render axis 1m beyond visible screen edge
    const visibleWorldXMin_NoMargin = (-panX / zoomLevel) / PIXELS_PER_METER;
    const visibleWorldXMax_NoMargin = (canvasWidth - panX) / zoomLevel / PIXELS_PER_METER;
    drawLineWorld(ctx, visibleWorldXMin_NoMargin - RENDER_MARGIN_WORLD, OPTICAL_AXIS_Y_WORLD, visibleWorldXMax_NoMargin + RENDER_MARGIN_WORLD, OPTICAL_AXIS_Y_WORLD, '#808080', 1.5);
}

function drawLensVisualWorld(x_w, label, power_D) {
    if (!ctx) return;
    const visual_h_w = LENS_VISUAL_HEIGHT_WORLD;
    const endCurvature_w = visual_h_w * 0.1; // Curvature relative to height
    
    ctx.beginPath();
    ctx.moveTo(x_w, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2); // Using world coords directly for path
    if (power_D > 0.01) { // Converging
        ctx.quadraticCurveTo(x_w + endCurvature_w, OPTICAL_AXIS_Y_WORLD, x_w, OPTICAL_AXIS_Y_WORLD + visual_h_w / 2);
        ctx.quadraticCurveTo(x_w - endCurvature_w, OPTICAL_AXIS_Y_WORLD, x_w, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2);
    } else if (power_D < -0.01) { // Diverging
        const bodyOffset_w = endCurvature_w * 0.3;
        ctx.moveTo(x_w + bodyOffset_w, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2);
        ctx.quadraticCurveTo(x_w - endCurvature_w + bodyOffset_w, OPTICAL_AXIS_Y_WORLD, x_w + bodyOffset_w, OPTICAL_AXIS_Y_WORLD + visual_h_w / 2);
        ctx.lineTo(x_w - bodyOffset_w, OPTICAL_AXIS_Y_WORLD + visual_h_w / 2);
        ctx.quadraticCurveTo(x_w + endCurvature_w - bodyOffset_w, OPTICAL_AXIS_Y_WORLD, x_w - bodyOffset_w, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2);
    } else { // Plano or very weak
        const bodyWidth_w = 0.002;
        ctx.rect(x_w - bodyWidth_w / 2, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2, bodyWidth_w, visual_h_w);
    }
    ctx.closePath();
    
    // Apply PIXELS_PER_METER scaling *only at stroke/fill time* if helpers don't handle it
    // The path commands should use world units. Helper functions scale during their stroke/fill.
    // This requires drawLensVisualWorld to use PIXELS_PER_METER internally or pass world coords to helpers.
    // The current helpers DO scale, so this is fine.

    ctx.strokeStyle = '#0060c0'; // Darker blue
    ctx.lineWidth = Math.max(0.5, 1.5 / zoomLevel);
    ctx.stroke(); // Path is defined in world units if helpers weren't used. Here, helpers handle scaling.
    
    // To use helpers for path definition:
    // Re-do with drawLineWorld and quadraticCurveToWorld if available.
    // For now, this mixed approach (path in world, then scaled stroke) is tricky.
    // Better: Define path in world, then apply transform & scale path.
    // OR: Stick to helpers for all drawing.
    // Let's try to use scaled drawing logic within this function itself.

    const path = new Path2D(); // For complex shapes
    path.moveTo(x_w * PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD - visual_h_w / 2) * PIXELS_PER_METER);
    if (power_D > 0.01) {
        path.quadraticCurveTo((x_w + endCurvature_w) * PIXELS_PER_METER, OPTICAL_AXIS_Y_WORLD * PIXELS_PER_METER, x_w * PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD + visual_h_w / 2) * PIXELS_PER_METER);
        path.quadraticCurveTo((x_w - endCurvature_w) * PIXELS_PER_METER, OPTICAL_AXIS_Y_WORLD * PIXELS_PER_METER, x_w * PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD - visual_h_w / 2) * PIXELS_PER_METER);
    } else if (power_D < -0.01) {
        const bodyOffset_w = endCurvature_w * 0.3;
        path.moveTo((x_w + bodyOffset_w)*PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD - visual_h_w / 2)*PIXELS_PER_METER);
        path.quadraticCurveTo((x_w - endCurvature_w + bodyOffset_w)*PIXELS_PER_METER, OPTICAL_AXIS_Y_WORLD*PIXELS_PER_METER, (x_w + bodyOffset_w)*PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD + visual_h_w / 2)*PIXELS_PER_METER);
        path.lineTo((x_w - bodyOffset_w)*PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD + visual_h_w / 2)*PIXELS_PER_METER);
        path.quadraticCurveTo((x_w + endCurvature_w - bodyOffset_w)*PIXELS_PER_METER, OPTICAL_AXIS_Y_WORLD*PIXELS_PER_METER, (x_w - bodyOffset_w)*PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD - visual_h_w / 2)*PIXELS_PER_METER);
    } else {
        const bodyWidth_w = 0.002;
        path.rect((x_w - bodyWidth_w/2)*PIXELS_PER_METER, (OPTICAL_AXIS_Y_WORLD - visual_h_w / 2)*PIXELS_PER_METER, bodyWidth_w*PIXELS_PER_METER, visual_h_w*PIXELS_PER_METER);
    }
    path.closePath();
    ctx.strokeStyle = '#0060c0';
    ctx.lineWidth = Math.max(0.5, 1.5 / zoomLevel);
    ctx.stroke(path);
    ctx.fillStyle = 'rgba(135, 206, 250, 0.25)'; // Lighter blue fill
    ctx.fill(path);

    drawTextWorld(ctx, `${label} (${power_D.toFixed(2)}D)`, x_w, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2 - 0.015, '#202040', 11, 'center');
}


function drawRetinaVisualWorld() {
    if (!ctx || !simulatorConstantsInitialized) return;
    const visual_h_w = LENS_VISUAL_HEIGHT_WORLD * 0.9;
    drawLineWorld(ctx, RETINA_WORLD_X, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2, RETINA_WORLD_X, OPTICAL_AXIS_Y_WORLD + visual_h_w / 2, '#c00000', 3); // Darker red
    drawTextWorld(ctx, 'Retina', RETINA_WORLD_X + 0.002, OPTICAL_AXIS_Y_WORLD - visual_h_w / 2 - 0.005, '#c00000', 11, 'left');
}

function drawObjectVisualWorld(object_dist_from_cl_plane_m, object_y_offset_world, object_visual_height_world) {
    if (!ctx || !simulatorConstantsInitialized) return { x_w: 0, y_tip_w: 0, h_w: 0, y_center_w: OPTICAL_AXIS_Y_WORLD };
    const object_x_w = CORRECTIVE_LENS_WORLD_X - object_dist_from_cl_plane_m;
    const object_y_center_w = OPTICAL_AXIS_Y_WORLD - object_y_offset_world; 
    const object_y_tip_w = object_y_center_w - object_visual_height_world / 2;

    if (objectImageLoaded && objectImage.complete && objectImage.naturalWidth !== 0 && objectImage.naturalHeight !== 0) {
        const aspectRatio = objectImage.naturalWidth / objectImage.naturalHeight;
        const displayHeight_px = object_visual_height_world * PIXELS_PER_METER; // Height in current scaled pixels
        const displayWidth_px = displayHeight_px * aspectRatio;
        try {
            //drawImage takes screen coords (already transformed by pan/zoom)
            //so we need to scale world to screen pixels for width/height
            ctx.drawImage(objectImage, 
                (object_x_w - (object_visual_height_world * aspectRatio)/2) * PIXELS_PER_METER, 
                object_y_tip_w * PIXELS_PER_METER, 
                displayWidth_px, 
                displayHeight_px);
        } catch (e) { drawFallbackObjectWorld(object_x_w, object_y_tip_w, object_visual_height_world); }
    } else {
        drawFallbackObjectWorld(object_x_w, object_y_tip_w, object_visual_height_world);
    }
    return { x_w: object_x_w, y_tip_w: object_y_tip_w, h_w: object_visual_height_world, y_center_w: object_y_center_w };
}

function drawFallbackObjectWorld(x_w, y_tip_w, height_w) {
    const arrowHeadSize_w = height_w * 0.25;
    drawLineWorld(ctx, x_w, y_tip_w, x_w, y_tip_w + height_w, '#008000', 2); 
    drawLineWorld(ctx, x_w, y_tip_w, x_w - arrowHeadSize_w / 2, y_tip_w + arrowHeadSize_w, '#008000', 2);
    drawLineWorld(ctx, x_w, y_tip_w, x_w + arrowHeadSize_w / 2, y_tip_w + arrowHeadSize_w, '#008000', 2);
}

function calculateThinLensImage(u_m, h_obj_m, P_D) {
    if (Math.abs(P_D) < 1e-9) return { v_m: u_m, h_img_m: h_obj_m, mag: 1.0 }; // No power
    let v_m;
    const term_1_u = (u_m === Infinity || u_m === -Infinity || Math.abs(u_m) > 1e9) ? 0 : (1 / u_m);
    if (Math.abs(u_m) < 1e-9) { // Object at lens
        v_m = 0; // Image at lens
    } else if (Math.abs(P_D - term_1_u) < 1e-9) { 
        v_m = Infinity; 
    } else {
        v_m = 1 / (P_D - term_1_u);
    }
    let mag = 1.0;
    if (!(u_m === Infinity || u_m === -Infinity || Math.abs(u_m) < 1e-9 || Math.abs(u_m) > 1e9)) {
      mag = v_m / u_m;
    } else if (Math.abs(u_m) < 1e-9) { mag = 1.0; }
    return { v_m: v_m, h_img_m: h_obj_m * mag, mag: mag };
}

function drawPrincipalRaysForLensWorld(obj_y_tip_w, obj_x_w, u_m, P_D, lens_x_w, h_obj_for_calc_m, ray_color) {
    if (!ctx || !simulatorConstantsInitialized || (Math.abs(P_D) < 1e-9 && u_m === Infinity)) return null;

    const { v_m, h_img_m, mag } = calculateThinLensImage(u_m, h_obj_for_calc_m, P_D);
    const f_m = (Math.abs(P_D) < 1e-9) ? Infinity : 1 / P_D;

    const img_x_w = lens_x_w + v_m;
    const obj_tip_y_rel_axis_w = obj_y_tip_w - OPTICAL_AXIS_Y_WORLD;
    const img_tip_y_rel_axis_w = obj_tip_y_rel_axis_w * mag; // Magnification includes inversion
    const img_y_tip_w = OPTICAL_AXIS_Y_WORLD + img_tip_y_rel_axis_w;

    const RENDER_RAY_LIMIT_X = 10; // meters in world units for ray extension
    const visibleWorldXMin = (-panX / zoomLevel) / PIXELS_PER_METER - RENDER_RAY_LIMIT_X;
    const visibleWorldXMax = (canvasWidth - panX) / zoomLevel / PIXELS_PER_METER + RENDER_RAY_LIMIT_X;

    // Ray 1: Parallel from object tip to lens, then refracts
    drawLineWorld(ctx, obj_x_w, obj_y_tip_w, lens_x_w, obj_y_tip_w, ray_color, 1);
    if (Math.abs(f_m) !== Infinity) { // Lens has power
        if (Math.abs(v_m) !== Infinity) { // Converges/diverges to image point
            drawLineWorld(ctx, lens_x_w, obj_y_tip_w, img_x_w, img_y_tip_w, ray_color, 1);
        } else { // Image at infinity (obj was at F_obj), ray exits parallel to axis
            const extend_to = lens_x_w + Math.sign(P_D) * RENDER_RAY_LIMIT_X; // Extend in direction of light
            drawLineWorld(ctx, lens_x_w, obj_y_tip_w, extend_to, obj_y_tip_w, ray_color, 1);
        }
    } else { // No lens power, ray continues straight
        drawLineWorld(ctx, lens_x_w, obj_y_tip_w, lens_x_w + Math.sign(obj_x_w < lens_x_w ? 1 : -1 ) * RENDER_RAY_LIMIT_X , obj_y_tip_w, ray_color, 1);
    }

    // Ray 2: From object tip through lens center (approx for thin lens), undeviated
    if (Math.abs(v_m) !== Infinity) {
        drawLineWorld(ctx, obj_x_w, obj_y_tip_w, img_x_w, img_y_tip_w, ray_color, 0.8);
    } else { // Image at infinity, ray exits with slope
         // Slope from object tip, through lens center. Point on lens is (lens_x_w, obj_y_tip_w - (obj_x_w - lens_x_w) * slope_to_center)
         // Simpler: ray from object tip passes through (lens_x_w, OPTICAL_AXIS_Y_WORLD) if object itself was on axis.
         // For off-axis object, the ray aims for lens center then continues with same slope.
        const slope = (obj_y_tip_w - OPTICAL_AXIS_Y_WORLD) / (obj_x_w - lens_x_w); // Slope from obj tip to lens center
        if(Math.abs(obj_x_w - lens_x_w) < 1e-9) { // object is at lens plane
             drawLineWorld(ctx, lens_x_w, obj_y_tip_w, lens_x_w + RENDER_RAY_LIMIT_X, obj_y_tip_w, ray_color, 0.8); // Exits parallel
        } else {
            const y_at_extend = OPTICAL_AXIS_Y_WORLD + slope * (RENDER_RAY_LIMIT_X); // Y if extended from lens center
            drawLineWorld(ctx, obj_x_w, obj_y_tip_w, lens_x_w + RENDER_RAY_LIMIT_X, OPTICAL_AXIS_Y_WORLD + slope * (RENDER_RAY_LIMIT_X), ray_color, 0.8);
        }
    }
    
    if (Math.abs(v_m) !== Infinity) {
      drawCircleWorld(ctx, img_x_w, img_y_tip_w, 0.0015, IMAGE_POINT_COLOR);
    }
    return { x_w: img_x_w, y_tip_w: img_y_tip_w, h_m: Math.abs(h_img_m), v_m: v_m, mag: mag };
}

function drawSimulation(config) {
    if (!ctx) { console.error("Canvas context missing in drawSimulation"); return; }
    if (!simulatorConstantsInitialized) { // Defer if constants not ready
        if (!initializeSimulatorCoreConstants()) {
            console.error("Failed to initialize optical constants. Aborting draw.");
            ctx.save(); ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,canvasWidth,canvasHeight);
            ctx.fillStyle="red"; ctx.font="14px Arial"; ctx.textAlign="center";
            ctx.fillText("Error: Simulator constants not loaded. Check console.", canvasWidth/2, canvasHeight/2);
            ctx.restore();
            return;
        }
    }
    console.log("DrawSimulation Start:", {config, panX, panY, zoomLevel, PPM: PIXELS_PER_METER});

    clearCanvasAndTransform();
    drawOpticalAxisWorld();
    drawRetinaVisualWorld();

    const u_obj_for_L1_m = config.objectDistance; 
    const object_h_calc_m = OBJECT_VISUAL_HEIGHT_WORLD;
    const object_y_offset_world = config.objectYOffset; // Now directly in meters
    const objectVisual = drawObjectVisualWorld(u_obj_for_L1_m, object_y_offset_world, object_h_calc_m);
    const object_tip_y_world = objectVisual.y_center_w - object_h_calc_m / 2 * Math.sign(objectVisual.y_center_w - OPTICAL_AXIS_Y_WORLD || 1); // Tip relative to its center

    let P_corrective_D = 0;
    let hasCorrectiveLens = false;
    if (config.lensMode === 'manual') {
        P_corrective_D = config.manualLensPower;
        hasCorrectiveLens = Math.abs(P_corrective_D) > 1e-6;
    } else if (config.lensMode === 'prescription') {
        P_corrective_D = config.glassesRx + config.shiftRx;
        hasCorrectiveLens = true; 
    }
    
    const P_eye_actual_D = OPTICAL_CONSTANTS.p_emmetropic_eye_lens_power_D + config.inherentError;

    if (hasCorrectiveLens) {
        drawLensVisualWorld(CORRECTIVE_LENS_WORLD_X, "Corrective Lens", P_corrective_D);
    }
    drawLensVisualWorld(EYE_LENS_WORLD_X, "Eye Lens", P_eye_actual_D);

    let finalImageProperties;
    let infoText = "";

    if (hasCorrectiveLens) {
        const image1 = drawPrincipalRaysForLensWorld(object_tip_y_world, objectVisual.x_w, u_obj_for_L1_m, P_corrective_D, CORRECTIVE_LENS_WORLD_X, object_h_calc_m, RAY_COLOR_L1);
        if (image1) {
            drawTextWorld(ctx, 'I1', image1.x_w + 0.005, image1.y_tip_w - 0.005, '#555', 9);
            const u_obj_for_L2_m = EYE_LENS_WORLD_X - image1.x_w; 
            finalImageProperties = drawPrincipalRaysForLensWorld(image1.y_tip_w, image1.x_w, u_obj_for_L2_m, P_eye_actual_D, EYE_LENS_WORLD_X, image1.h_m, RAY_COLOR_L2);
            if (finalImageProperties) drawTextWorld(ctx, 'Final (I2)', finalImageProperties.x_w + 0.005, finalImageProperties.y_tip_w - 0.005, IMAGE_POINT_COLOR, 9);
        } else { infoText = "Could not form intermediate image I1."; }
    } else {
        const dist_obj_to_eye_lens_m = EYE_LENS_WORLD_X - objectVisual.x_w;
        finalImageProperties = drawPrincipalRaysForLensWorld(object_tip_y_world, objectVisual.x_w, dist_obj_to_eye_lens_m, P_eye_actual_D, EYE_LENS_WORLD_X, object_h_calc_m, RAY_COLOR_L2);
        if (finalImageProperties) drawTextWorld(ctx, 'Final Image', finalImageProperties.x_w + 0.005, finalImageProperties.y_tip_w - 0.005, IMAGE_POINT_COLOR, 9);
    }
    
    restoreCanvasTransform(); 

    if (finalImageProperties && finalImageProperties.v_m !== undefined) {
        const dist_final_img_from_eye_lens_m = finalImageProperties.v_m;
        const dist_img_from_retina_m = dist_final_img_from_eye_lens_m - OPTICAL_CONSTANTS.d_retina_fixed_m;
        
        if (dist_final_img_from_eye_lens_m === Infinity) infoText = "Final image formed at infinity.";
        else if (Math.abs(dist_img_from_retina_m) < 0.00005) { // Stricter tolerance: 0.05mm
             infoText = "Image sharply focused on the retina! ✅";
        } else {
            const front_or_behind = dist_img_from_retina_m < 0 ? "in front of" : "behind";
            infoText = `Image focused ${Math.abs(dist_img_from_retina_m * 1000).toFixed(1)} mm ${front_or_behind} the retina.`;
        }
    } else if (!infoText) { // Only set if not already set by I1 failure
         infoText = "Final image location indeterminate.";
    }
    
    const infoDisplayElement = document.getElementById('infoDisplay');
    if (infoDisplayElement) infoDisplayElement.textContent = infoText;
    console.log("Draw finished. Info:", infoText);
}

// --- Pan and Zoom Event Handlers ---
if (canvas) {
    canvas.addEventListener('mousedown', (e) => {
        isPanning = true;
        lastPanX_screen = e.clientX;
        lastPanY_screen = e.clientY;
        canvas.style.cursor = 'grabbing';
    });
    canvas.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        const dx_screen = e.clientX - lastPanX_screen;
        const dy_screen = e.clientY - lastPanY_screen;
        panX += dx_screen; // PanX and PanY are screen space offsets
        panY += dy_screen;
        lastPanX_screen = e.clientX;
        lastPanY_screen = e.clientY;
        requestRedrawIfNeeded();
    });
    canvas.addEventListener('mouseup', () => { isPanning = false; canvas.style.cursor = 'grab'; });
    canvas.addEventListener('mouseleave', () => { isPanning = false; canvas.style.cursor = 'default'; });
    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const zoomIntensity = 0.05; // Slower zoom
        const scroll = e.deltaY < 0 ? (1 + zoomIntensity) : (1 - zoomIntensity);
        
        const rect = canvas.getBoundingClientRect();
        const mouseX_screen = e.clientX - rect.left;
        const mouseY_screen = e.clientY - rect.top;

        // Adjust pan to keep mouse point fixed during zoom
        // Old world coords of mouse point: ( (mouseX_screen - panX) / zoomLevel, (mouseY_screen - panY) / zoomLevel )
        // New pan should be: mouseX_screen - new_world_coords_of_mouse_X * newZoomLevel
        const worldMouseX_before = (mouseX_screen - panX) / zoomLevel;
        const worldMouseY_before = (mouseY_screen - panY) / zoomLevel;

        zoomLevel *= scroll;
        zoomLevel = Math.max(0.02, Math.min(zoomLevel, 50)); // Wider zoom limits

        panX = mouseX_screen - worldMouseX_before * zoomLevel;
        panY = mouseY_screen - worldMouseY_before * zoomLevel;
        
        requestRedrawIfNeeded();
    });
     canvas.style.cursor = 'grab';
}
// common.js - Shared utility functions

function parseFloatSafe(value, defaultValue = 0.0) {
    const num = parseFloat(value);
    return isNaN(num) ? defaultValue : num;
}

function drawLine(ctx, x1, y1, x2, y2, color = 'black', lineWidth = 1) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
}

function drawText(ctx, text, x, y, color = 'black', font = '10px Arial', textAlign = 'left', textBaseline = 'alphabetic') {
    ctx.fillStyle = color;
    ctx.font = font;
    ctx.textAlign = textAlign;
    ctx.textBaseline = textBaseline;
    ctx.fillText(text, x, y);
}

function drawCircle(ctx, x, y, radius, color = 'black', fill = true) {
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, 2 * Math.PI);
    if (fill) {
        ctx.fillStyle = color;
        ctx.fill();
    } else {
        ctx.strokeStyle = color;
        ctx.stroke();
    }
}
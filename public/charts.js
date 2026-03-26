/* ═══════════════════════════════════════════════════════════════════════════
   Stego Explorer — Canvas chart helpers (dark theme)
   Pure-JS drawing utilities for horizontal bars, grouped bars, etc.
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Theme tokens (must match style.css) ──────────────────────────────────── */

var CHART_THEME = {
    bg:       '#0D1526',
    grid:     '#1C2C48',
    gridMid:  '#263A5C',
    text:     '#8A9BB8',
    textDim:  '#5A6E8A',
    track:    '#131E33',
    font:     "'DM Mono', 'SF Mono', monospace",
    fontBody: "'Source Sans 3', system-ui, sans-serif"
};


/**
 * Draw a rounded rectangle path on the canvas context.
 */
function roundedRect(ctx, x, y, w, h, r) {
    if (!Array.isArray(r)) r = [r, r, r, r];
    while (r.length < 4) r.push(r[r.length - 1]);
    var tl = r[0], tr = r[1], br = r[2], bl = r[3];

    ctx.beginPath();
    ctx.moveTo(x + tl, y);
    ctx.lineTo(x + w - tr, y);
    ctx.arcTo(x + w, y, x + w, y + tr, tr);
    ctx.lineTo(x + w, y + h - br);
    ctx.arcTo(x + w, y + h, x + w - br, y + h, br);
    ctx.lineTo(x + bl, y + h);
    ctx.arcTo(x, y + h, x, y + h - bl, bl);
    ctx.lineTo(x, y + tl);
    ctx.arcTo(x, y, x + tl, y, tl);
    ctx.closePath();
}


/**
 * Horizontal bar chart (dark themed).
 */
function drawHorizontalBars(canvas, labels, values, colors) {
    var dpr = window.devicePixelRatio || 1;
    var W = canvas.parentElement.clientWidth || 500;
    var H = canvas.height || 200;

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';

    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    var labelWidth = Math.max(100, labels.reduce(function (m, l) {
        return Math.max(m, l.length * 7);
    }, 0));
    var pad = { t: 10, r: 64, b: 10, l: labelWidth };
    var chartWidth = W - pad.l - pad.r;
    var n = labels.length;
    var groupHeight = H / n;
    var barHeight = Math.min(20, groupHeight - 12);

    ctx.clearRect(0, 0, W, H);

    // Dashed baseline at 0.5
    var baselineX = pad.l + 0.5 * chartWidth;
    ctx.strokeStyle = CHART_THEME.gridMid;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(baselineX, pad.t);
    ctx.lineTo(baselineX, H - pad.b);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = CHART_THEME.textDim;
    ctx.font = '10px ' + CHART_THEME.font;
    ctx.textAlign = 'center';
    ctx.fillText('0.5', baselineX, pad.t - 2 < 8 ? 10 : pad.t - 2);

    // Bars
    labels.forEach(function (lbl, i) {
        var cy = pad.t + i * groupHeight + groupHeight / 2;
        var v = Math.max(0, Math.min(1, values[i]));
        var bw = v * chartWidth;

        // Label
        ctx.fillStyle = CHART_THEME.text;
        ctx.font = '11px ' + CHART_THEME.font;
        ctx.textAlign = 'right';
        ctx.fillText(lbl, pad.l - 10, cy + 4);

        // Track
        ctx.fillStyle = CHART_THEME.track;
        roundedRect(ctx, pad.l, cy - barHeight / 2, chartWidth, barHeight, 3);
        ctx.fill();

        // Value bar
        ctx.fillStyle = colors[i] || '#5BA3D9';
        roundedRect(ctx, pad.l, cy - barHeight / 2, bw || 2, barHeight, 3);
        ctx.fill();

        // Value label
        ctx.fillStyle = CHART_THEME.text;
        ctx.font = '11px ' + CHART_THEME.font;
        ctx.textAlign = 'left';
        ctx.fillText(v.toFixed(3), pad.l + bw + 8, cy + 4);
    });
}


/**
 * Grouped vertical bar chart (dark themed).
 */
function drawGroupedBars(canvas, labels, datasets) {
    var dpr = window.devicePixelRatio || 1;
    var W = canvas.parentElement.clientWidth || 500;
    var H = canvas.height || 200;

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';

    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    var pad = { t: 24, r: 16, b: 54, l: 40 };
    var chartWidth = W - pad.l - pad.r;
    var chartHeight = H - pad.t - pad.b;
    var n = labels.length;
    var nd = datasets.length;
    var groupWidth = chartWidth / n;
    var barWidth = Math.min(24, Math.max(6, (groupWidth - 14) / nd));

    ctx.clearRect(0, 0, W, H);

    // Horizontal grid lines
    [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
        var y = pad.t + chartHeight * (1 - v);
        ctx.strokeStyle = v === 0.5 ? CHART_THEME.gridMid : CHART_THEME.grid;
        ctx.lineWidth = 1;
        ctx.setLineDash(v === 0.5 ? [3, 3] : []);
        ctx.beginPath();
        ctx.moveTo(pad.l, y);
        ctx.lineTo(pad.l + chartWidth, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = CHART_THEME.textDim;
        ctx.font = '10px ' + CHART_THEME.font;
        ctx.textAlign = 'right';
        ctx.fillText(v.toFixed(2), pad.l - 6, y + 3);
    });

    // Bars
    labels.forEach(function (lbl, gi) {
        var gx = pad.l + gi * groupWidth + groupWidth / 2;

        datasets.forEach(function (ds, di) {
            var v = Math.max(0, Math.min(1, ds.vals[gi] || 0));
            var bx = gx + (di - (nd - 1) / 2) * (barWidth + 3) - barWidth / 2;

            ctx.fillStyle = ds.color;
            ctx.globalAlpha = 0.85;
            roundedRect(ctx, bx, pad.t + chartHeight * (1 - v), barWidth, v * chartHeight || 2, [3, 3, 0, 0]);
            ctx.fill();
            ctx.globalAlpha = 1;
        });

        // X-axis label
        ctx.fillStyle = CHART_THEME.text;
        ctx.font = '10px ' + CHART_THEME.font;
        ctx.textAlign = 'center';
        var shortLabel = lbl.length > 10 ? lbl.slice(0, 9) + '\u2026' : lbl;
        ctx.fillText(shortLabel, gx, H - pad.b + 14);
    });

    // Legend
    var lx = pad.l;
    var ly = H - 6;
    ctx.font = '10px ' + CHART_THEME.fontBody;

    datasets.forEach(function (ds) {
        ctx.fillStyle = ds.color;
        ctx.globalAlpha = 0.85;
        roundedRect(ctx, lx, ly - 7, 10, 7, 2);
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = CHART_THEME.text;
        ctx.textAlign = 'left';
        ctx.fillText(ds.label, lx + 14, ly);
        lx += ctx.measureText(ds.label).width + 28;
    });
}

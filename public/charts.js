// canvas chart helpers (dark theme)

const CHART_THEME = {
    bg:       '#05183c',
    grid:     '#1a2d54',
    gridMid:  '#2b4680',
    text:     '#8f9fb7',
    textDim:  '#5b74b1',
    track:    '#06122d',
    font:     "monospace",
    fontBody: "'Inter', system-ui, sans-serif"
};

function roundedRect(ctx, x, y, w, h, r) {
    if (!Array.isArray(r)) r = [r, r, r, r];
    while (r.length < 4) r.push(r[r.length - 1]);
    ctx.beginPath();
    ctx.moveTo(x + r[0], y);
    ctx.lineTo(x + w - r[1], y);
    ctx.arcTo(x + w, y, x + w, y + r[1], r[1]);
    ctx.lineTo(x + w, y + h - r[2]);
    ctx.arcTo(x + w, y + h, x + w - r[2], y + h, r[2]);
    ctx.lineTo(x + r[3], y + h);
    ctx.arcTo(x, y + h, x, y + h - r[3], r[3]);
    ctx.lineTo(x, y + r[0]);
    ctx.arcTo(x, y, x + r[0], y, r[0]);
    ctx.closePath();
}

function drawHorizontalBars(canvas, labels, values, colors) {
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth || 500, H = canvas.height || 200;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);

    const lw = Math.max(100, labels.reduce((m, l) => Math.max(m, l.length * 7), 0));
    const pad = { t: 10, r: 64, b: 10, l: lw };
    const cw = W - pad.l - pad.r, n = labels.length, gh = H / n, bh = Math.min(20, gh - 12);
    ctx.clearRect(0, 0, W, H);

    const bx = pad.l + 0.5 * cw;
    ctx.strokeStyle = CHART_THEME.gridMid; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(bx, pad.t); ctx.lineTo(bx, H - pad.b); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = CHART_THEME.textDim; ctx.font = '10px ' + CHART_THEME.font; ctx.textAlign = 'center';
    ctx.fillText('0.5', bx, 10);

    labels.forEach((lbl, i) => {
        const cy = pad.t + i * gh + gh / 2, v = Math.max(0, Math.min(1, values[i])), bw = v * cw;
        ctx.fillStyle = CHART_THEME.text; ctx.font = '11px ' + CHART_THEME.font; ctx.textAlign = 'right';
        ctx.fillText(lbl, pad.l - 10, cy + 4);
        ctx.fillStyle = CHART_THEME.track; roundedRect(ctx, pad.l, cy - bh / 2, cw, bh, 3); ctx.fill();
        ctx.fillStyle = colors[i] || '#7bd0ff'; roundedRect(ctx, pad.l, cy - bh / 2, bw || 2, bh, 3); ctx.fill();
        ctx.fillStyle = CHART_THEME.text; ctx.font = '11px ' + CHART_THEME.font; ctx.textAlign = 'left';
        ctx.fillText(v.toFixed(3), pad.l + bw + 8, cy + 4);
    });
}

function drawGroupedBars(canvas, labels, datasets) {
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth || 500, H = canvas.height || 200;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);

    const pad = { t: 24, r: 16, b: 54, l: 40 };
    const cw = W - pad.l - pad.r, ch = H - pad.t - pad.b;
    const n = labels.length, nd = datasets.length, gw = cw / n;
    const bw = Math.min(24, Math.max(6, (gw - 14) / nd));
    ctx.clearRect(0, 0, W, H);

    [0, 0.25, 0.5, 0.75, 1].forEach((v) => {
        const y = pad.t + ch * (1 - v);
        ctx.strokeStyle = v === 0.5 ? CHART_THEME.gridMid : CHART_THEME.grid;
        ctx.lineWidth = 1; ctx.setLineDash(v === 0.5 ? [3, 3] : []);
        ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + cw, y); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = CHART_THEME.textDim; ctx.font = '10px ' + CHART_THEME.font; ctx.textAlign = 'right';
        ctx.fillText(v.toFixed(2), pad.l - 6, y + 3);
    });

    labels.forEach((lbl, gi) => {
        const gx = pad.l + gi * gw + gw / 2;
        datasets.forEach((ds, di) => {
            const v = Math.max(0, Math.min(1, ds.vals[gi] || 0));
            const x = gx + (di - (nd - 1) / 2) * (bw + 3) - bw / 2;
            ctx.fillStyle = ds.color; ctx.globalAlpha = 0.85;
            roundedRect(ctx, x, pad.t + ch * (1 - v), bw, v * ch || 2, [3, 3, 0, 0]); ctx.fill();
            ctx.globalAlpha = 1;
        });
        ctx.fillStyle = CHART_THEME.text; ctx.font = '10px ' + CHART_THEME.font; ctx.textAlign = 'center';
        ctx.fillText(lbl.length > 10 ? lbl.slice(0, 9) + '\u2026' : lbl, gx, H - pad.b + 14);
    });

    let lx = pad.l;
    const ly = H - 6;
    ctx.font = '10px ' + CHART_THEME.fontBody;
    datasets.forEach((ds) => {
        ctx.fillStyle = ds.color; ctx.globalAlpha = 0.85;
        roundedRect(ctx, lx, ly - 7, 10, 7, 2); ctx.fill(); ctx.globalAlpha = 1;
        ctx.fillStyle = CHART_THEME.text; ctx.textAlign = 'left';
        ctx.fillText(ds.label, lx + 14, ly);
        lx += ctx.measureText(ds.label).width + 28;
    });
}

// results tab — RQ1-RQ5 cards, quality metrics, charts

function buildQualityMetricsCard(qualityRows) {
    const scored = qualityRows.filter(r => r.psnr !== '' || r.ssim !== '');
    if (!scored.length) return '';
    const levelMap = {};
    scored.forEach(r => {
        const lvl = r.payload_level || 'unknown';
        if (!levelMap[lvl]) levelMap[lvl] = { psnrSum: 0, ssimSum: 0, psnrN: 0, ssimN: 0 };
        if (r.psnr !== '' && !isNaN(Number(r.psnr)) && isFinite(Number(r.psnr))) {
            levelMap[lvl].psnrSum += Number(r.psnr); levelMap[lvl].psnrN++;
        }
        if (r.ssim !== '' && !isNaN(Number(r.ssim))) {
            levelMap[lvl].ssimSum += Number(r.ssim); levelMap[lvl].ssimN++;
        }
    });
    const levelOrder = ['low', 'medium', 'high'];
    const levels = levelOrder.filter(l => levelMap[l])
        .concat(Object.keys(levelMap).filter(l => levelOrder.indexOf(l) === -1));
    const tableRows = levels.map(lvl => {
        const d = levelMap[lvl];
        const psnr = d.psnrN ? d.psnrSum / d.psnrN : null;
        const ssim = d.ssimN ? d.ssimSum / d.ssimN : null;
        return `<tr>
            <td class="rq-bd-det">${escapeHtml(lvl)}</td>
            <td class="rq-bd-val">${psnr != null ? psnr.toFixed(2) + ' dB' : '\u2014'}</td>
            <td class="rq-bd-val">${ssim != null ? ssim.toFixed(4) : '\u2014'}</td>
            <td class="rq-bd-val" style="color:var(--secondary-dim)">${d.psnrN}</td>
        </tr>`;
    }).join('');
    return `<div class="rq-card">
        <div class="rq-head">
            <div class="rq-head-left"><span class="rq-num">QC</span><span class="rq-title">Embedding Quality</span></div>
            <span class="rq-type rq-type--verification">Quality Control</span>
        </div>
        <p class="rq-question">PSNR and SSIM measure imperceptibility \u2014 higher values indicate less visible distortion from embedding.</p>
        <table class="rq-breakdown">
            <thead><tr><th>Payload Level</th><th>Mean PSNR</th><th>Mean SSIM</th><th>Samples</th></tr></thead>
            <tbody>${tableRows}</tbody>
        </table>
    </div>`;
}

function buildPrototypeBanner(cfg) {
    const profile = (cfg || {}).profile || '';
    return `<proto-banner profile="${escapeAttr(profile)}"></proto-banner>`;
}

function buildResultsTab(data, detailStats) {
    if (!data.has_results) {
        return `<div class="empty-state"><h3>No results yet</h3><p>Run the pipeline with detectors enabled to generate metrics for the research questions.</p></div>`;
    }

    const detectorRows  = toArray((data.metrics || {}).detector);
    const sourceRows    = toArray((data.metrics || {}).source);
    const conditionRows = toArray((data.metrics || {}).condition);
    const qualityRows   = toArray((data.metrics || {}).quality);
    const detectors     = uniqueValues(detectorRows, 'detector');
    const methods       = uniqueValues(conditionRows, 'method');

    function avgAuc(rows) {
        const v = rows.filter(r => r.roc_auc && !isNaN(Number(r.roc_auc)));
        if (!v.length) return null;
        return v.reduce((s, r) => s + Number(r.roc_auc), 0) / v.length;
    }
    function fmtAuc(v) { return v != null ? v.toFixed(3) : '\u2014'; }
    function aucCls(v) {
        if (v == null) return '';
        return v > 0.85 ? 'rq-auc--good' : (v > 0.65 ? 'rq-auc--mid' : 'rq-auc--low');
    }
    function pct(v) { return v != null ? Math.round(v * 100) : 0; }
    function deltaHtml(a, b) {
        if (a == null || b == null) return '';
        const d = b - a;
        const cls = Math.abs(d) < 0.005 ? 'rq-delta--neutral' : (d > 0 ? 'rq-delta--pos' : 'rq-delta--neg');
        return `<span class="rq-delta ${cls}">\u0394 ${d >= 0 ? '+' : ''}${d.toFixed(3)}</span>`;
    }
    function sourceAuc(det, src) {
        const r = sourceRows.find(r => r.detector === det && r.source === src);
        return r ? Number(r.roc_auc) : null;
    }
    function pooledMl(det) {
        const vals = [sourceAuc(det, 'ml_a'), sourceAuc(det, 'ml_b')].filter(v => v != null);
        return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
    }
    function condAuc(f) {
        return avgAuc(conditionRows.filter(r => {
            for (const k in f) { if (f[k] !== undefined && r[k] !== f[k]) return false; }
            return true;
        }));
    }

    function rqCard(num, title, type, question, body, hasData) {
        const tCls = 'rq-type--' + type.toLowerCase();
        if (!hasData) body = `<div class="rq-no-data">Insufficient data for this analysis in the current run.</div>`;
        return `<div class="rq-card">
            <div class="rq-head">
                <div class="rq-head-left"><span class="rq-num">${num}</span><span class="rq-title">${escapeHtml(title)}</span></div>
                <span class="rq-type ${tCls}">${escapeHtml(type)}</span>
            </div>
            <p class="rq-question">${question}</p>
            ${body}
        </div>`;
    }

    function pairVis(lA, aucA, clsA, noteA, lB, aucB, clsB, noteB) {
        return `<div class="rq-pair">
            <div class="rq-side"><div class="rq-side-label ${clsA}">${escapeHtml(lA)}</div>
                <div class="rq-side-num ${aucCls(aucA)}">${fmtAuc(aucA)}</div>
                <div class="rq-side-bar"><div class="rq-side-fill rq-fill-${clsA}" style="width:${pct(aucA)}%"></div></div>
                ${noteA ? `<div class="rq-side-note">${noteA}</div>` : ''}
            </div>
            <div class="rq-vs">${deltaHtml(aucA, aucB)}</div>
            <div class="rq-side"><div class="rq-side-label ${clsB}">${escapeHtml(lB)}</div>
                <div class="rq-side-num ${aucCls(aucB)}">${fmtAuc(aucB)}</div>
                <div class="rq-side-bar"><div class="rq-side-fill rq-fill-${clsB}" style="width:${pct(aucB)}%"></div></div>
                ${noteB ? `<div class="rq-side-note">${noteB}</div>` : ''}
            </div>
        </div>`;
    }

    function bdTable(lA, lB, clsA, clsB, fnA, fnB) {
        const rows = detectors.map(d => {
            const a = fnA(d), b = fnB(d);
            return `<tr>
                <td class="rq-bd-det">${escapeHtml(fmtDetector(d))}</td>
                <td class="rq-bd-val ${aucCls(a)}">${fmtAuc(a)}</td>
                <td class="rq-bd-val ${aucCls(b)}">${fmtAuc(b)}</td>
                <td class="rq-bd-delta">${deltaHtml(a, b)}</td>
            </tr>`;
        }).join('');
        return `<table class="rq-breakdown">
            <thead><tr><th>Detector</th><th class="${clsA}">${escapeHtml(lA)}</th><th class="${clsB}">${escapeHtml(lB)}</th><th>\u0394</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    }

    // RQ1: Real vs ML
    const oReal = avgAuc(sourceRows.filter(r => r.source === 'real'));
    const oMlA  = avgAuc(sourceRows.filter(r => r.source === 'ml_a'));
    const oMlB  = avgAuc(sourceRows.filter(r => r.source === 'ml_b'));
    const mlVals = [oMlA, oMlB].filter(v => v != null);
    const oMl   = mlVals.length ? mlVals.reduce((s, v) => s + v, 0) / mlVals.length : null;
    const rq1 = pairVis('Real', oReal, 'src-real', 'COCO + Flickr30k', 'ML (pooled)', oMl, 'src-ml', 'avg SDXL + FLUX.1') +
        bdTable('Real', 'ML', 'src-real', 'src-ml', d => sourceAuc(d, 'real'), pooledMl);

    // RQ2: ML-A vs ML-B
    const hasRq2 = oMlA != null && oMlB != null;
    const rq2 = pairVis('ML-A (SDXL)', oMlA, 'src-mla', 'Stable Diffusion XL 1.0', 'ML-B (FLUX.1)', oMlB, 'src-mlb', 'FLUX.1-schnell') +
        bdTable('ML-A', 'ML-B', 'src-mla', 'src-mlb', d => sourceAuc(d, 'ml_a'), d => sourceAuc(d, 'ml_b'));

    // RQ3: Payload interaction
    const payloadLevels = uniqueValues(conditionRows, 'payload_level');
    const lvlOrder = ['low', 'medium', 'high'];
    const ordLvls = lvlOrder.filter(l => payloadLevels.indexOf(l) !== -1)
        .concat(payloadLevels.filter(l => lvlOrder.indexOf(l) === -1));
    const LEVEL_CLR = { low: 'var(--green)', medium: 'var(--amber)', high: 'var(--error)' };
    let rq3;
    if (ordLvls.length > 1) {
        rq3 = `<div class="rq3-grid">${ordLvls.map(lvl => {
            const overall = condAuc({ payload_level: lvl });
            const c = LEVEL_CLR[lvl] || 'var(--primary)';
            const perDet = detectors.map(det => {
                const a = condAuc({ detector: det, payload_level: lvl });
                return `<div class="rq3-det-row"><span class="rq3-det-name">${escapeHtml(fmtDetector(det))}</span><span class="rq3-det-val ${aucCls(a)}">${fmtAuc(a)}</span></div>`;
            }).join('');
            return `<div class="rq3-level-card"><div class="rq3-level-label" style="color:${c}">${escapeHtml(lvl)}</div>
                <div class="rq3-level-auc ${aucCls(overall)}">${fmtAuc(overall)}</div>
                <div class="rq-side-bar"><div class="rq-side-fill" style="width:${pct(overall)}%;background:${c}"></div></div>
                <div class="rq3-det-list">${perDet}</div></div>`;
        }).join('')}</div>`;
    } else {
        const singleLvl = ordLvls[0] || 'none';
        const singleAuc = ordLvls.length ? condAuc({ payload_level: singleLvl }) : null;
        rq3 = `<p class="rq-note">Only one payload level (<strong>${escapeHtml(singleLvl)}</strong>) in this run. Run the full design with low / medium / high to analyze payload interaction.</p>` +
            (singleAuc != null ? `<div class="rq3-grid"><div class="rq3-level-card" style="max-width:220px"><div class="rq3-level-label">${escapeHtml(singleLvl)}</div><div class="rq3-level-auc ${aucCls(singleAuc)}">${fmtAuc(singleAuc)}</div>
            <div class="rq-side-bar"><div class="rq-side-fill" style="width:${pct(singleAuc)}%;background:var(--primary)"></div></div></div></div>` : '');
    }

    // RQ4: Embedding branch
    const hasRq4 = methods.length > 1;
    let rq4;
    if (hasRq4) {
        const oLsb = condAuc({ method: 'lsb' }), oDct = condAuc({ method: 'dct' });
        rq4 = pairVis('LSB (Spatial)', oLsb, 'method-lsb', 'PNG carriers', 'DCT (Frequency)', oDct, 'method-dct', 'JPEG Q=95 carriers');
        const lsbDets = detectors.filter(d => conditionRows.some(r => r.detector === d && r.method === 'lsb' && r.roc_auc));
        const dctDets = detectors.filter(d => conditionRows.some(r => r.detector === d && r.method === 'dct' && r.roc_auc));
        rq4 += `<div class="rq4-branches">
            <div class="rq4-branch"><div class="rq4-branch-label method-lsb">Spatial Detectors</div>
                ${lsbDets.map(d => { const a = condAuc({detector:d,method:'lsb'}); return `<div class="rq3-det-row"><span class="rq3-det-name">${escapeHtml(fmtDetector(d))}</span><span class="rq3-det-val ${aucCls(a)}">${fmtAuc(a)}</span></div>`; }).join('')}
            </div>
            <div class="rq4-branch"><div class="rq4-branch-label method-dct">Frequency Detectors</div>
                ${dctDets.map(d => { const a = condAuc({detector:d,method:'dct'}); return `<div class="rq3-det-row"><span class="rq3-det-name">${escapeHtml(fmtDetector(d))}</span><span class="rq3-det-val ${aucCls(a)}">${fmtAuc(a)}</span></div>`; }).join('')}
            </div>
        </div>`;
    } else {
        rq4 = `<p class="rq-note">Only one embedding method (<strong>${escapeHtml(methods[0] || 'none')}</strong>) in this run. Run with both LSB and DCT to compare spatial vs. frequency branches.</p>`;
    }

    // RQ5: Encryption invariance
    const oPlain = condAuc({ encryption: 'plain' }), oEnc = condAuc({ encryption: 'encrypted' });
    const hasRq5 = oPlain != null && oEnc != null;
    let rq5;
    if (hasRq5) {
        const d5 = Math.abs(oEnc - oPlain);
        const finding = d5 < 0.01
            ? 'Encryption shows no meaningful effect on detectability (\u0394 < 0.01), which is what we\'d expect if detectors react to distortion rather than payload content.'
            : `Encryption has a noticeable effect here (\u0394 = ${d5.toFixed(3)}), which shouldn\'t happen if detectors only respond to embedding distortion.`;
        rq5 = pairVis('Plain', oPlain, 'enc-plain', 'unencrypted payload', 'AES-256-CBC', oEnc, 'enc-encrypted', 'encrypted payload') +
            bdTable('Plain', 'Encrypted', 'enc-plain', 'enc-encrypted',
                d => condAuc({ detector: d, encryption: 'plain' }),
                d => condAuc({ detector: d, encryption: 'encrypted' })) +
            `<p class="rq-finding">${finding}</p>`;
    } else {
        rq5 = `<p class="rq-note">Both plain and encrypted payloads are needed. Run with encryption enabled to test invariance.</p>`;
    }

    const chartDetector = `<div class="rq-chart-wrap"><canvas id="chart-detector" height="200"></canvas></div>`;
    const chartSource   = `<div class="rq-chart-wrap"><canvas id="chart-source" height="200"></canvas></div>`;
    const chartEnc      = `<div class="rq-chart-wrap"><canvas id="chart-encryption" height="180"></canvas></div>`;

    return (
        rqCard('RQ1', 'Carrier Source', 'Primary',
            'Does carrier source (real photographs vs. ML-generated images) affect steganographic detectability under matched embedding settings?',
            rq1 + chartSource, sourceRows.length > 0) +
        rqCard('RQ2', 'Generator Effect', 'Primary',
            'Within ML-generated carriers, does the choice of generator (ML-A vs. ML-B) affect detectability?',
            rq2 + chartDetector, hasRq2) +
        rqCard('RQ3', 'Payload Interaction', 'Exploratory',
            'Does payload size change the detectability gap between carrier sources?',
            rq3, true) +
        rqCard('RQ4', 'Embedding Branch', 'Exploratory',
            'Do the spatial branch (LSB+PNG) and frequency branch (DCT-LSB+JPEG) show different carrier-source effects?',
            rq4, true) +
        rqCard('RQ5', 'Encryption Invariance', 'Verification',
            'Does AES-256-CBC encryption of the payload affect detectability?',
            rq5 + chartEnc, true) +
        buildQualityMetricsCard(qualityRows)
    );
}

function drawAllCharts(data) {
    const detectorRows = toArray((data.metrics || {}).detector);
    const sourceRows = toArray((data.metrics || {}).source);
    const conditionRows = toArray((data.metrics || {}).condition);
    const detectorNames = uniqueValues(detectorRows, 'detector');

    const detectorCanvas = document.getElementById('chart-detector');
    if (detectorCanvas && detectorRows.length) {
        drawHorizontalBars(
            detectorCanvas,
            detectorRows.map(row => row.detector),
            detectorRows.map(row => Number(row.roc_auc || 0)),
            detectorRows.map((_, i) => DETECTOR_PALETTE[i % DETECTOR_PALETTE.length])
        );
    }

    const sourceCanvas = document.getElementById('chart-source');
    if (sourceCanvas && sourceRows.length) {
        drawGroupedBars(sourceCanvas, detectorNames, ['real', 'ml_a', 'ml_b'].map(source => ({
            label: source,
            color: SOURCE_COLORS[source],
            vals: detectorNames.map(detector => {
                const row = sourceRows.find(item => item.detector === detector && item.source === source);
                return row ? Number(row.roc_auc || 0) : 0;
            })
        })));
    }

    const encryptionCanvas = document.getElementById('chart-encryption');
    if (encryptionCanvas && conditionRows.length) {
        drawGroupedBars(encryptionCanvas, detectorNames, ['plain', 'encrypted'].map(encryption => ({
            label: encryption,
            color: ENCRYPTION_COLORS[encryption],
            vals: detectorNames.map(detector => {
                const rows = conditionRows.filter(item => item.detector === detector && item.encryption === encryption && item.roc_auc);
                if (!rows.length) return 0;
                return rows.reduce((sum, item) => sum + Number(item.roc_auc || 0), 0) / rows.length;
            })
        })));
    }
}

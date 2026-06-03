# Final Presentation — Per-Slide Speaker Notes

Bullet points for each slide in `final_presentation_slides_v2.pdf`, written in plain language. Use this to rehearse what to say, what numbers matter, and *why* we made each design decision. Stats jargon is explained the first time it appears.

---

## Stats vocabulary (used throughout)

- **AUC (ROC Area Under Curve)** — a single number from 0.5 to 1.0 that says "how well does this detector separate stego from cover?". **0.5 = coin flip; 1.0 = perfect**. We report AUC because it doesn't depend on picking a threshold.
- **Δ-AUC (delta AUC)** — the *difference* in detector quality between two carrier sources (e.g. real photos vs. ML images). Sign tells you who is easier to detect.
- **Stratum** — one "cell" of the experiment: e.g. *detector = RS, payload = low*. We have 15 such cells (5 detectors × 3 payloads).
- **DeLong test** — the standard statistical test for comparing two AUCs computed on the *same* covers. "Same covers" lets the test be much more sensitive than testing them independently.
- **Holm correction** — when you run 15 tests at once, some will look "significant" by pure chance. Holm tightens the threshold to keep that error rate low across the family.
- **Practical-significance gate (δ_min = 0.05)** — a result can be *statistically* significant (p < 0.05) but *practically* tiny (e.g. Δ = 0.001). We required |Δ-AUC| ≥ 0.05 to call something a real effect. This number was pre-registered in our proposal — we can't move the goalposts after the fact.
- **pAUC** — *partial* AUC. Only the left part of the ROC (low false-positive rate) matters in practice; full AUC includes regions a real screener would never use.

---

## Slide 1 — Title

- Title screen. Nothing to say.
- **Decision recap:** stuck with the original proposal title; project scope was preserved end-to-end.

## Slide 2 — Agenda

- Six steps: motivation → research questions → experimental design → statistics → results → limitations & contribution.
- Total: ~25 slides; aim for ~30–40 sec per content slide.

## Slide 3 — Motivation Recap

- **One-line setup:** "Detectability of hidden messages depends on the cover image's statistics, not just the embedding algorithm."
- Photographic carriers dominate every steganalysis benchmark — but diffusion-generated images are everywhere now and have *different* statistical fingerprints.
- Closest prior work (Méreur 2024) studies AI carriers but uses adaptive embedding and reports a different metric (P_E, classifier-error rate). We use AUC and basic embedders, so the question is unaddressed.
- **Core question highlighted in the box:** "Do detectors trained on photographs still work when the carrier is an ML image?"

## Slide 4 — Research Questions

- **RQ1 (primary):** Does carrier source (real vs ML) affect detectability?
- **RQ2 (primary):** Within ML carriers, does the choice of generator (SDXL vs FLUX) matter?
- **RQ3 (exploratory):** Does payload size change the gap between real and ML?
- **RQ4 (exploratory):** Do spatial detectors and frequency detectors react differently?
- **RQ5 (verification, *expected null*):** Does AES encryption of the payload change detectability? We expect "no" — detectors react to embedding artefacts, not plaintext.
- **Decision rationale:** "Primary" = pre-registered, runs with strict Holm correction. "Exploratory" = secondary, uses confidence intervals instead. "Verification" tests a sanity-check assumption.

## Slide 5 — Caption-Matched Carriers, 3×2×3×2 Factorial

- **Diagram explains the experimental setup.** For each caption ("a brown cat on a wooden chair") we get 3 covers: one real photo, one SDXL image, one FLUX image. Then 12 stego variants per source (2 methods × 3 payloads × 2 encryptions).
- Per group: 3 covers + 36 stegos = 39 images. With 1,000 groups → 39,000 images.
- **Caption matching is the key control:** every source sees the same semantic content. Any AUC gap can only come from *how* each source represents that content (pixel statistics), not from one set having mostly cats and the other mostly cars.
- **Decision rationale:** grayscale 512×512, dual storage (PNG + JPEG). PNG needed for spatial detectors (lossless); JPEG Q=95 needed for DCT detectors. Q=95 is the highest practical quality and matches the embedder's re-save quality.

## Slide 6 — Embedding Methods

- **Spatial — LSB substitution:** replace the last bit of each pixel with a payload bit. Lossless storage required (PNG). Detected by RS, χ², Sample Pairs.
- **Frequency — DCT-LSB (JSteg-style):** in each 8×8 block, flip the last bit of *non-zero* AC coefficients. Skip DC (top-left) and ±1 coefficients (would be revealed by Westfeld's pair trick). JPEG Q=95.
- **Decision rationale:** these are the two textbook approaches the proposal required. Both are *training-free*, so any AUC effect we see is about carrier statistics, not classifier overfitting.

## Slide 7 — Detector Mechanisms

- **Pairs-of-Values (PoV) histogram intuition (left diagram):** LSB embedding equalises the counts of paired values like (2k, 2k+1). On a cover the bars within each pair are uneven; on a stego they flatten. The χ² test measures exactly this flattening.
- **Five detectors:**
  - **RS** (Fridrich 2001) — pixel-group ratios
  - **χ²-spatial** (Westfeld 1999) — the PoV test
  - **Sample Pairs** (Dumitrescu 2003) — adjacent-pixel multiset traces
  - **χ²-DCT** (Westfeld 1999) — PoV on AC coefficients
  - **Calibration χ²** (Fridrich 2003) — compares the DCT histogram to a re-compressed reference
- **Why training-free matters:** no learned weights means an AUC gap between sources cannot be blamed on training-set mismatch.

## Slide 8 — Pipeline Structure

- Five sequential stages: **Data → Manifests → Embedding → Detection → Analysis**.
- Each stage outputs files that the next stage reads. Stages can be re-run independently.
- **Decision rationale (run isolation):** every run lives in its own `runs/<id>/` directory with a frozen `config.json`. This makes results reproducible and re-runs idempotent (already-done work is skipped).

## Slide 9 — Web Platform and Live Monitoring

- Local Python HTTP server (stdlib only — no Flask/Django) + single-page browser client (no build step).
- Endpoints: list, launch, preview, kill, detail. Launching spawns the runner as a subprocess; stdout is streamed to the browser via Server-Sent Events.
- The launch drawer computes a live **power estimate** (Hanley–McNeil) in JavaScript: it tells you ahead of time whether the planned run is big enough to catch a real effect.
- **Decision rationale:** building a UI helped iterate fast — see runs progress, kill bad ones early, browse stego galleries without leaving the browser. The Toolbox tab (encode/decode/analyze) reuses the same backend.

## Slide 10 — Statistical Analysis

- **DeLong test (right diagram):** scores two ROC curves on the same cover set, computes the *paired* Δ-AUC. Pairing makes the test more powerful because the noise from individual covers cancels.
- **Holm correction:** 15 strata per RQ → Holm tightens p-values so the family-wide false-positive rate stays ≤ 0.05.
- **Equivalence margin for RQ5 (±0.025 AUC):** for the null result we need to *prove* no effect exists, not just fail to find one. ±0.025 means "if the true effect is below 1/40 of full AUC range, treat it as zero".
- **Power:** with N = 1,000 groups, we can reliably detect effects ≥ δ_min = 0.05. Anything smaller is in our blind spot — and is also too small to matter operationally.

## Slide 11 — Run Artefacts and Reproducibility

- The 1,000-group run produced: 6,000 covers, 36,000 stegos, 180,000 detector predictions, 19 metric CSVs, 53 figures, RQ verdicts in JSON + Markdown. ~4.5 GB total, ~2h49m wall-clock.
- **Reproducibility checklist:** seeded at every stage (split, payload, embedding, ML generation), frozen config per run, manifest-driven, idempotent, 245 automated tests, all code open-source.
- **Decision rationale:** this slide intentionally comes *before* the results — so the audience knows the numbers are reproducible scaffolding, not hand-picked outputs.

## Slide 12 — Stego Image Quality (PSNR / SSIM)

- **PSNR (peak signal-to-noise ratio, dB) and SSIM (structural similarity, 0–1):** standard measures of how much the stego image differs from its cover. PSNR ≥ 40 dB and SSIM ≥ 0.99 are the conventional "visually invisible" floor.
- Our numbers: PSNR 50–64 dB, SSIM ≥ 0.998 *for every condition*. Visually imperceptible by a wide margin.
- **PSNR is roughly equivalent across real / ml_a / ml_b** (58.1 / 59.2 / 59.1 dB).
- **Decision rationale:** if PSNR differed across sources, an "ML easier to detect" finding might mean "ML stego is more distorted". This slide proves that's not the case — the embedding budget is the same per pixel, the difference is in carrier statistics.

## Slide 13 — Headline AUC by Carrier Source and Detector

- Grouped bar chart: for each of the 5 detectors, three bars (real, ml_a/SDXL, ml_b/FLUX). AUC scale 0.5–1.0.
- **Bottom line in the orange box:** four of five detectors find ML *easier* than real (orange/blue bars taller than dark grey). The **χ²-spatial detector is the lone outlier — on LSB, diffusion outputs are *harder* to detect**.
- This single chart sets up the rest of the talk: there *is* a carrier-source effect, but its sign depends on the detector.

## Slide 14 — RQ1: Real vs. Pooled ML

- **Test:** Paired DeLong per stratum, Holm-adjusted across 15 strata.
- **Pooled Δ-AUC: −0.0150** (negative = ML easier). 95% CI [−0.0165, −0.0135] — narrow, far from zero.
- **Significant after Holm: 11 / 15** (most strata).
- **Practically relevant (|Δ| ≥ 0.05): 4 / 11** — only four strata clear the pre-registered practical threshold, all on the ML-easier side.
- **Verdict: "mixed"** — direction-consistent at the practical gate, but most effects are too small to matter.
- The strip chart shows each detector × payload as a dot; the grey band is the "trivial" zone |Δ| < 0.05. The four dots outside the band on the ML-easier side come from **three independent detector families** — that agreement matters more than the count.

## Slide 15 — RQ1: Per-Stratum AUC Scatter

- **Same 15 strata, plotted as x = real AUC, y = ML AUC.** Dot above the diagonal → ML easier; below → real easier.
- **Shape encodes the detector** (circle / square / triangle / diamond / pentagon); **fill colour encodes payload** (dark = low, light = medium, orange = high).
- The orange band is the ±0.05 practical margin.
- **What to point out:** all three *triangles* (χ²-spatial) sit below the diagonal — the lone "real easier" detector. The four dots outside the band (RS/low, sample-pairs/low, χ²-DCT/med, χ²-DCT/high) are the practically-relevant ML-easier wins.

## Slide 16 — RQ2: SDXL vs. FLUX within ML

- **Test:** Paired DeLong on caption-matched SDXL/FLUX pairs.
- **Pooled Δ-AUC: +0.0007** — essentially zero.
- **Significant after Holm: 3 / 15**; **practically relevant: 0 / 3**.
- **Verdict: "trivial"** — a few strata are statistically significant only because the sample is large; *none* clear δ_min = 0.05.
- **Interpretation:** the two generators are *interchangeable* in their detector signature. Whichever diffusion model you pick, the carrier statistics look the same to classical detectors.
- The strip plot looks the same as RQ1's but every dot sits inside the grey trivial band — exactly the point.

## Slide 17 — RQ2: Per-Stratum AUC Scatter

- Same encoding as slide 15 but axes are SDXL vs FLUX.
- **What to point out:** every dot hugs the diagonal. The three *squares* (χ²-DCT) are slightly off-diagonal toward SDXL-easier — max gap ≈ 0.04, below the practical threshold.

## Slide 18 — RQ3: Payload Interaction with Source

- **Question:** does the real-vs-ML gap change with payload size?
- **Numbers (real − ML AUC gap):** low = **−0.046**, medium = **−0.024**, high = **−0.017**.
- **Pattern: monotone, decreasing magnitude with payload.** The carrier-source signal is *strongest at low payload* — exactly the regime a real steganalyst cares about (subtle embeddings).
- **Verdict: "supported"** — the trend is consistent across detectors and payload levels.
- **Reading the chart:** four ML-easier detectors plotted as muted light-blue lines (form a cluster), χ²-spatial as a dashed dark line (the outlier going the other way), pooled trend as a bold orange line.
- **Mechanism:** at high payload, the per-pixel modification noise dominates the carrier-origin fingerprint. At low payload, the embedding is subtle enough that carrier statistics drive the detector decision.

## Slide 19 — RQ4: Spatial vs. Frequency Branch

- **Metric (ΔΔ-AUC):** the difference of the differences — (spatial branch's source gap) − (frequency branch's source gap).
- **Pooled ΔΔ: +0.0150** (CI [+0.008, +0.022]). Strata excluding 0 in CI: 2 / 3; practically relevant: 1 / 2.
- **Verdict: "mixed"** — the dominant branch *flips with payload*. Spatial branch dominates at low payload (ΔΔ = −0.066, practical); frequency branch dominates at high payload (ΔΔ = +0.042, statistically significant but trivial).
- **Reading the chart:** two side-by-side bars per payload level (spatial = blue, frequency = orange), both negative (because both branches see ML easier).
- **Takeaway:** *which* branch shows the strongest source effect depends on the embedding rate. There's no universal "best branch for distinguishing real from ML carriers".

## Slide 20 — RQ5: Encryption Invariance (Verification)

- **Test:** Paired DeLong between plain and AES-256-CBC stego on shared cover groups. Equivalence margin **±0.025 AUC**.
- **Strata within margin: 45 / 45.** Pooled Δ-AUC ≈ 0.
- **Verdict: "supported — encryption is invariant"** (this is the *expected* null).
- **Why this matters:** if encryption changed detectability, it would mean detectors are reacting to *plaintext patterns* (e.g. ASCII regularity) rather than embedding distortion. The clean null confirms they react to the right thing.
- **Reading the chart:** 45 dots near the diagonal in a tight cluster; orange band = ±0.025 equivalence margin.

## Slide 21 — Supplementary: Partial AUC at FPR ≤ 0.10

- **Motivation:** full AUC integrates the *entire* ROC, including regions a real screener would never use (e.g. accepting 50% false-positive rate). pAUC only counts the operationally useful part — false-positive rate ≤ 10%.
- **Why FPR ≤ 0.10:** McClish (1989) standard; matches steganalysis screening practice; fits our ROC curve shapes.
- **What changes under pAUC:**
  - Effect sizes **3–5× larger**. sample-pairs/low jumps from Δ = −0.10 (full AUC) to Δ = **−0.31** (pAUC).
  - **RQ1 verdict: mixed → supported**; RQ2: trivial → supported.
  - **χ²-spatial flip dissolves** — the "diffusion easier on real" effect was a high-FPR artefact, invisible in the operationally-relevant tail.
- **Why this matters:** the headline (full-AUC) results were already informative, but the pAUC view is *the right operational metric* — and it confirms the same direction with much sharper effects.

## Slide 22 — Supplementary: RQ1 Per-Stratum pAUC Scatter

- Same scatter encoding as slide 15, but the axes are *real pAUC* and *ML pAUC*.
- **Headline visual:** the dots are spread *much further* from the diagonal than under full AUC. sample-pairs/low and rs/low sit deep in the ML-easier zone.
- **The three triangles (χ²-spatial) collapse back onto the diagonal** — visual confirmation that the flip was a full-AUC artefact, not a real low-FPR effect.

## Slide 23 — Limitations

- **Acknowledged deviations from the proposal:**
  - ml_b: PixArt-α was unavailable on the HF Inference API → switched to FLUX.1-schnell. Both are diffusion models with similar pretraining objectives, so the comparison still makes sense.
  - Payload fill rates revised from {0.25, 0.50, 0.75} → **{0.05, 0.15, 0.30}** to avoid detector *saturation* (every detector at near-perfect AUC = no useful signal to compare). The lower regime is also more operationally realistic.
- **Scope bounds:** two generator families only (can't disentangle architecture from training data); grayscale; classical detectors only; RQ4's branch pooling is asymmetric (3 spatial vs 2 frequency detectors — accounted for in inverse-variance weighting).

## Slide 24 — Contribution and Minimum Deliverable

- **What this study contributes (3 bullets):** caption-matched dataset across three carrier sources; training-free AUC-based comparison with proper statistical machinery (DeLong + Holm + practical-gate); pre-computed RQ verdicts and power analysis as reproducible artefacts.
- **Minimum deliverable from the proposal:** one encryption scheme (AES-256-CBC) ✓; two embedding approaches (spatial LSB + frequency DCT-LSB) ✓; defensible answers to RQ1 & RQ2 ✓.

## Slide 25 — Phase 3 Extensions

- **In flight:** N = 3,000 full-design re-run (~7 h) — tighter confidence intervals, independent confirmation of RQ1 & RQ2 verdicts on a 3× larger sample.
- **Concrete next steps (each ~1 day):**
  - Lower payload tier (0.01 / 0.02 bpp) added via `rerun_with_existing_covers.py`. Should widen the source gap on strong detectors (RS, sample-pairs).
  - Promote **pAUC@FPR≤0.10 to a co-primary metric** — the supplementary contrasts (slide 21) become a headline result.
  - JPEG-quality sweep (Q ∈ {75, 85, 95}): does the carrier-source effect survive lossy recompression?
- **Mechanism investigations:**
  - PoV-histogram skewness per source — directly measure ∑ₖ |n_{2k} − n_{2k+1}| on cover histograms with *no* embedding. Validates the diffusion-flatness explanation for the χ²-spatial flip.
  - KL divergence or MMD between source distributions vs Δ-AUC per detector — turn the per-detector story into a quantitative one.
- **Smaller cleanups:** colour mode (YCbCr-Y storage); promote the χ²-spatial finding to a discussion paragraph in the report with the PoV-skewness evidence.

## Slide 26 — Thank You / Q&A

- Closing slide. Mention code and run artefacts live under `runs/<id>/`.

---

## Common Q&A traps

- **"Why is χ²-spatial the only detector that disagrees?"** Diffusion outputs have unusually *balanced* (2k, 2k+1) pixel-bit histograms (their tone curves are smoother than natural photos). χ²-spatial reads this as "looks like stego" *before* you embed anything — so when you do embed, the chi-square statistic doesn't move as much, and real photos look easier to attack. The supplementary pAUC analysis confirms this is a high-FPR artefact: in the operationally useful left-tail, the flip disappears.
- **"Why didn't you use machine-learning detectors?"** Two reasons. (1) Our research question is about *carrier statistics*, not classifier capacity. A trained classifier could fit to the source label directly and tell us nothing about whether the carrier itself matters. (2) Training-free detectors keep the experimental design clean — any AUC gap is unambiguously attributable to carrier statistics, not training-set composition.
- **"AUC seems abstract — how does this translate to a real attack?"** AUC = "if I pick a random cover and a random stego, what's the probability my detector ranks the stego higher?". An AUC of 0.99 (RS at high payload, ML carrier) means a steganalyst would correctly rank 99 out of 100 random pairs. The Δ-AUC of 0.05 says ML stego is *5 percentage points more likely* to be ranked correctly than a real-photo stego — material at operational scales.
- **"Why δ_min = 0.05?"** Pre-registered in the proposal. It's the smallest effect we considered "worth a paragraph" — large enough to be operationally meaningful, small enough not to demand huge sample sizes. We can't move this number after the fact without losing scientific credibility.
- **"Why 1,000 groups?"** The Hanley–McNeil power calculation said this is enough to detect δ = 0.05 with ≥ 80% power at α = 0.05. The 3,000-group rerun is a stress test, not a sample-size correction.
- **"What does the pAUC change to the χ²-spatial result mean?"** It means the "ML harder to detect on LSB" headline was real *in some technical sense* but lived in the part of the ROC curve nobody operationally cares about. Once you focus on FPR ≤ 0.10 — where a real steganalyst would actually run — the effect vanishes. Honest reporting of the full-AUC flip + the pAUC dissolution is the takeaway.

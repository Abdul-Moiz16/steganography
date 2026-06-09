# Post-Training Checklist

> **Status:** to be executed once the cloud SRNet+DCTR training run completes
> (estimated finish: ~14:30 CET 27 May 2026; trigger: `runs/training_v1/srnet_done.marker` on Vast.ai instance).
>
> **Total wall-clock for full post-training workflow:** ~2.5–3 hours of focused
> work plus an overnight HuggingFace upload.

---

## 0. Academic decision — Option 1 (separate analysis), no exceptions

Two doubts you raised, both answered here before any commands are run.

### 0.1 Reproducibility plan

Three artefacts to preserve, three places to put them:

| Artefact | Size | Where | Why |
|---|---|---|---|
| **Trained checkpoints** (6 files: 3×SRNet + 3×DCTR) | ~150 MB | **HuggingFace Model Hub** (`maastrichtuniversity/m22-stego-srnet-dctr-v1`) | Public download, free tier, model-card support |
| **Training-set manifests + caption-exclusion list** | ~3 MB | **Git** (commit to `srnet-dctr-baselines` branch under `models/training_v1/training_manifests/`) | Lives with the code, version-controlled, no extra accounts |
| **DOI-archival snapshot** (everything: checkpoints + manifests + scripts + report v2) | ~200 MB | **Zenodo** (auto-import from GitLab tag `v1.0-final` via Zenodo–GitLab integration) | Citable DOI required for journal/conference submission |

We DO NOT preserve the 30 GB training images themselves — they are
deterministically regeneratable from the manifests + the documented
HuggingFace Inference API + the seeds. Cost: $0 to keep around, $0.72/day
if we left them on Vast.ai.

### 0.2 Should the learned analysis be merged into the primary (Option 2) or kept separate (Option 1)?

**Decision: Option 1 (separate analysis).** Three reasons grounded in the original proposal.

1. **The proposal explicitly pre-registered this exact split.** From `docs/proposals/proposal_updated_3.tex` line 195:
   > *"**Extension (time-permitting):** SRNet retrained on \[a separate corpus\] embedded with spatial LSB and DCT-LSB. This would add a trained detector to both branches **and be reported separately.**"*

   And from line 245:
   > *"We use classical detectors for the primary analysis because the project focuses on steganography and cryptography rather than building deep models."*

   Option 2 would silently rewrite the primary analysis after seeing the data, which is the classic p-hacking failure mode the pre-registration was designed to prevent.

2. **Bonferroni–Holm correction is sample-size-dependent.** The pre-registered primary analysis has 18 strata (6 classical detectors × 3 payloads). Adding 6 learned-detector strata makes it 24 → the per-stratum α threshold tightens by ~33%, which could flip a borderline classical verdict post-hoc. A reviewer would (correctly) flag this.

3. **The publishability story is stronger with separation.** The paper's contribution is NOT "we built a better detector" — it's "we ran a rigorous, pre-registered comparison of carrier-source detectability using training-free detectors, AND we corroborated/refined the findings with state-of-the-art learned baselines trained on caption-matched (not BOSSBase) data, thereby addressing the cover-source-mismatch confound that has historically muddled this question." Framing the learned analysis as a **robustness check** is a much harder argument to attack than framing it as a primary contribution.

**What "separate analysis" looks like in the v2 paper:**

- Section V.A–V.I (RQ1–RQ5 primary results): unchanged from v1, classical detectors only, byte-identical numbers and figures.
- Section V.J (NEW supplementary): "Learned-Detector Robustness Check" with its own per-RQ contrast tables. Explicitly states this is a sensitivity analysis on the pre-registered findings.
- Discussion section: one paragraph relating learned-detector results back to each primary verdict (corroborate / refine / contradict).
- The placeholder PDF table structure in `final_report.tex` already supports this exactly.

---

## Phase A — Retrieve artefacts from Vast.ai

Wall-clock: ~5 minutes.

- [ ] **A.1** Confirm SRNet training finished cleanly:
  ```bash
  ssh -p $VAST_PORT root@$VAST_HOST 'ls -lh /workspace/m2-2_steganography/runs/training_v1/srnet_done.marker /workspace/m2-2_steganography/models/srnet_lsb_*.pt /workspace/m2-2_steganography/models/dctr_dct_*.pkl'
  ```
  Expected: `srnet_done.marker` exists, 3 `.pt` files (~50 MB each), 3 `.pkl` files (~2 MB each).

- [ ] **A.2** SCP all artefacts back to laptop (the ~30 GB training images stay on cloud — manifests + checkpoints are enough for reproducibility):
  ```bash
  cd /Users/davidwickerhf/Projects/university/m2-2_steganography
  mkdir -p models/training_v1

  scp -P $VAST_PORT root@$VAST_HOST:/workspace/m2-2_steganography/models/srnet_lsb_*.pt   models/training_v1/
  scp -P $VAST_PORT root@$VAST_HOST:/workspace/m2-2_steganography/models/srnet_lsb_*.summary.json   models/training_v1/
  scp -P $VAST_PORT root@$VAST_HOST:/workspace/m2-2_steganography/models/dctr_dct_*.pkl   models/training_v1/
  scp -P $VAST_PORT root@$VAST_HOST:/workspace/m2-2_steganography/models/dctr_dct_*.summary.json   models/training_v1/
  scp -P $VAST_PORT -r root@$VAST_HOST:/workspace/m2-2_steganography/runs/training_v1/manifests   models/training_v1/training_manifests
  scp -P $VAST_PORT -r root@$VAST_HOST:/workspace/m2-2_steganography/logs/training_v1_srnet   models/training_v1/srnet_logs
  scp -P $VAST_PORT -r root@$VAST_HOST:/workspace/m2-2_steganography/logs/training_v1       models/training_v1/dctr_logs
  ```

- [ ] **A.3** Verify integrity:
  ```bash
  ls -lh models/training_v1/
  # Expected: 3×.pt (~50 MB each), 3×.pkl (~2 MB each), 6×.summary.json, manifests/, srnet_logs/, dctr_logs/
  ```

- [ ] **A.4** Print val-AUCs from summary.json files for sanity check:
  ```bash
  for f in models/training_v1/srnet_lsb_*.summary.json models/training_v1/dctr_dct_*.summary.json; do
    python -c "
  import json
  d = json.load(open('$f'))
  arch = 'srnet' if 'best_val_auc' in d else 'dctr'
  auc = d.get('best_val_auc', d.get('val_auc'))
  print(f'{arch}/{d[\"config\"][\"method\"]}/{d[\"config\"][\"payload\"]}: val_auc={auc:.4f}, n_train={d.get(\"n_train\")}, hash={d[\"training_run_hash\"]}')"
  done
  ```
  Healthy ranges: SRNet at 0.85–0.99 across cells, DCTR at 0.85–0.99. If anything is < 0.55, investigate before proceeding.

- [ ] **A.5** Commit the manifests + summaries to git for permanent provenance:
  ```bash
  git add models/training_v1/training_manifests/ models/training_v1/*.summary.json
  git commit -m "Add SRNet+DCTR training-run manifests and per-cell summaries (provenance)"
  git push origin srnet-dctr-baselines
  ```

---

## Phase B — Destroy the Vast.ai instance

Wall-clock: ~30 seconds. **Critical for cost control** ($0.72/day storage if you forget).

- [ ] **B.1** Verify retrieval succeeded (A.3 passed)
- [ ] **B.2** Browser: Vast.ai → Instances → trash icon → confirm.
- [ ] **B.3** Verify instance is gone (refresh Instances page).
- [ ] **B.4** Confirm balance is no longer being drained (Billing page).

---

## Phase C — Apply trained detectors to the test run

Wall-clock: ~30–45 minutes on laptop.

The inference scripts produce CSVs matching the existing `predictions.csv` schema. They include a **leakage guard** that refuses to score if the test-run manifest hash matches the training-run hash.

- [ ] **C.1** Activate local Python env:
  ```bash
  cd /Users/davidwickerhf/Projects/university/m2-2_steganography
  source .venv/bin/activate
  ```

- [ ] **C.2** Apply SRNet (3 cells, all LSB stegos in the test run):
  ```bash
  python scripts/inference/apply_srnet_to_run.py \
      --run runs/prototype_full_20260513_005357_p8765 \
      --models models/training_v1/srnet_lsb_low_v1.pt \
               models/training_v1/srnet_lsb_medium_v1.pt \
               models/training_v1/srnet_lsb_high_v1.pt \
      --out runs/prototype_full_20260513_005357_p8765/predictions/predictions_srnet.csv
  ```
  Expected: ~5–15 min depending on MPS vs CPU. Output CSV has one row per (cover or stego, encryption variant), ~108k rows total.

- [ ] **C.3** Apply DCTR (3 cells, all DCT stegos):
  ```bash
  python scripts/inference/apply_dctr_to_run.py \
      --run runs/prototype_full_20260513_005357_p8765 \
      --models models/training_v1/dctr_dct_low_v1.pkl \
               models/training_v1/dctr_dct_medium_v1.pkl \
               models/training_v1/dctr_dct_high_v1.pkl \
      --out runs/prototype_full_20260513_005357_p8765/predictions/predictions_dctr.csv \
      --n-workers $(sysctl -n hw.ncpu)
  ```
  Expected: ~15–25 min CPU-bound.

- [ ] **C.4** Verify the two new CSVs have the expected row counts:
  ```bash
  wc -l runs/prototype_full_20260513_005357_p8765/predictions/predictions_srnet.csv \
        runs/prototype_full_20260513_005357_p8765/predictions/predictions_dctr.csv
  ```
  Expected: each ~108,001 lines (108,000 cover+stego rows + header).

- [ ] **C.5** Spot-check no detector="srnet"/"dctr" rows are duplicated:
  ```bash
  python -c "
  import pandas as pd
  for f in ['predictions_srnet.csv', 'predictions_dctr.csv']:
      df = pd.read_csv(f'runs/prototype_full_20260513_005357_p8765/predictions/{f}')
      dup = df.duplicated(['group_id','source','method','payload_level','encryption','label']).sum()
      print(f'{f}: rows={len(df)}, detectors={df.detector.unique().tolist()}, dups={dup}')
      assert dup == 0, f'duplicates in {f}'
  "
  ```

---

## Phase D — Supplementary learned-detector analysis (Option 1)

Wall-clock: ~15–30 minutes.

**Critical:** this analysis writes to `runs/.../metrics_learned/` and `runs/.../figures_learned/` — it does NOT touch the existing `metrics/` and `figures/`. The v1 paper's classical-detector numbers stay frozen.

- [ ] **D.1** Identify the analysis entrypoint (probably `run.py` or `src/analysis/`):
  ```bash
  grep -lE "predictions\.csv|delong|bonferroni" src/**/*.py scripts/**/*.py 2>/dev/null | head
  ```

- [ ] **D.2** Run the analysis pipeline pointed at the two learned-detector CSVs, output to parallel dirs:
  ```bash
  # exact CLI flags TBD — adjust based on what the analysis entrypoint expects
  python -m src.analysis.run_analysis \
      --predictions-csv runs/prototype_full_20260513_005357_p8765/predictions/predictions_srnet.csv \
                        runs/prototype_full_20260513_005357_p8765/predictions/predictions_dctr.csv \
      --out-metrics  runs/prototype_full_20260513_005357_p8765/metrics_learned/ \
      --out-figures  runs/prototype_full_20260513_005357_p8765/figures_learned/ \
      --label "supplementary-learned"
  ```

  If the existing analysis pipeline does NOT accept multiple input CSVs, write a small wrapper that concatenates them into one before passing through:
  ```bash
  { cat runs/.../predictions/predictions_srnet.csv ;
    tail -n +2 runs/.../predictions/predictions_dctr.csv ; } \
    > /tmp/predictions_learned.csv
  python -m src.analysis.run_analysis --predictions-csv /tmp/predictions_learned.csv ...
  ```

- [ ] **D.3** Verify outputs:
  ```bash
  ls runs/prototype_full_20260513_005357_p8765/metrics_learned/
  ls runs/prototype_full_20260513_005357_p8765/figures_learned/
  ```
  Expect: similar shape to `metrics/` and `figures/` but scoped to the 6 learned-detector strata.

- [ ] **D.4** Sanity check the DeLong contrasts:
  ```bash
  cat runs/prototype_full_20260513_005357_p8765/metrics_learned/rq1_real_vs_pooled_ml_contrasts.csv 2>/dev/null | head
  ```
  Look for: 6 strata (3 SRNet + 3 DCTR), Holm-corrected p-values, AUC gaps in [-0.2, +0.2] range.

- [ ] **D.5** Compare learned-detector RQ1 verdict with classical RQ1 verdict:
  ```bash
  # classical RQ1 (frozen): pooled Δ = -0.0129, mixed verdict
  # learned RQ1: read from metrics_learned/rq_verdicts.json
  diff <(jq .rq1 runs/.../metrics/rq_verdicts.json) <(jq .rq1 runs/.../metrics_learned/rq_verdicts.json) || true
  ```
  This diff will land directly in the paper's "Comparison with classical detectors" paragraph.

---

## Phase E — Fill the v2 paper placeholders

Wall-clock: ~30–45 minutes manual transcription.

- [ ] **E.1** Open the v2 paper and find all remaining placeholders:
  ```bash
  grep -nE '\\TBD\{' docs/report/final_report.tex | wc -l
  # Currently 34 placeholders. After filling each, re-run this to track progress.
  ```

- [ ] **E.2** Fill in the val-AUC table (Table `tab:learned-val-auc`) from `models/training_v1/*.summary.json` — use the script in A.4 to print all 6 lines.

- [ ] **E.3** Fill in the headline-AUC table (Table `tab:learned-headline-auc`) from `metrics_learned/auc_by_source_detector.csv` (or equivalent).

- [ ] **E.4** Fill in the RQ1 strata table (Table `tab:learned-rq1`) from `metrics_learned/rq1_real_vs_pooled_ml_contrasts.csv`.

- [ ] **E.5** Fill in the RQ2/RQ4/RQ5 prose paragraphs using the pooled-Δ numbers from `metrics_learned/`.

- [ ] **E.6** Fill in the learned-vs-classical comparison table (Table `tab:learned-vs-classical`) by pairing each learned cell against the strongest classical detector on that cell.

- [ ] **E.7** Update the abstract and conclusion's `\TBD{...}` slots with the pooled learned-detector RQ1 finding and the corroboration verdict.

- [ ] **E.8** Update the methodology training-run paragraph with actual hours + cost (e.g., "33 instance-hours, USD ~$25 on a Vast.ai RTX 4090").

- [ ] **E.9** Confirm zero remaining placeholders:
  ```bash
  grep -nE '\\TBD\{' docs/report/final_report.tex && echo "STILL HAS TBDS" || echo "ALL FILLED"
  ```

---

## Phase F — Rebuild the v2 PDF

Wall-clock: ~3 minutes.

- [ ] **F.1** Compile (twice for cross-refs):
  ```bash
  cd docs/report
  pdflatex -interaction=nonstopmode final_report.tex
  pdflatex -interaction=nonstopmode final_report.tex
  ```

- [ ] **F.2** Visual scan for any remaining red `[TBD: ...]` markers — there should be zero.

- [ ] **F.3** Verify page count looks reasonable (v1 was 14 pages, v2 should be 17–20).

- [ ] **F.4** Open and read the new V.J supplementary section end-to-end.

---

## Phase G — Reproducibility archival (HuggingFace + Zenodo)

Wall-clock: ~30 min active + overnight upload.

### G.1 HuggingFace Model Hub upload

- [ ] **G.1.1** Install + log in:
  ```bash
  pip install huggingface_hub
  huggingface-cli login   # paste a token with write access
  ```

- [ ] **G.1.2** Create model repo (browser): https://huggingface.co/new → name `m22-stego-srnet-dctr-v1`, license `MIT` (or whatever your project uses), README markdown to write below.

- [ ] **G.1.3** Upload artefacts:
  ```bash
  cd models/training_v1
  huggingface-cli upload davidwickerhf/m22-stego-srnet-dctr-v1 \
      srnet_lsb_low_v1.pt srnet_lsb_medium_v1.pt srnet_lsb_high_v1.pt \
      dctr_dct_low_v1.pkl dctr_dct_medium_v1.pkl dctr_dct_high_v1.pkl \
      srnet_lsb_low_v1.summary.json srnet_lsb_medium_v1.summary.json srnet_lsb_high_v1.summary.json \
      dctr_dct_low_v1.summary.json dctr_dct_medium_v1.summary.json dctr_dct_high_v1.summary.json
  huggingface-cli upload davidwickerhf/m22-stego-srnet-dctr-v1 \
      training_manifests/ training_manifests/
  ```

- [ ] **G.1.4** Write a model card at `README.md` in the HF repo:
  ```markdown
  # SRNet + DCTR for caption-matched diffusion-cover steganalysis

  Trained on a 3,000-group caption-matched corpus disjoint from the test
  set by caption ID. See [paper](URL) for full methodology.

  ## Provenance
  - Training-run SHA-256 hash: <hash from summary.json>
  - Caption-exclusion source: 3000-group prototype run, manifest in repo
  - Code: <link to GitLab tag v1.0-final>
  - Seed: 4242 throughout

  ## Per-cell val AUCs
  | model | cell | val AUC |
  |---|---|---|
  | srnet | LSB/low | 0.XX |
  ... (transcribe from summary.json) ...

  ## How to use
  ```python
  ... example inference code ...
  ```

  ## Citation
  If you use these models, please cite [paper].
  ```

### G.2 Zenodo DOI for the full project snapshot

- [ ] **G.2.1** Enable GitLab–Zenodo integration (one-time): browser → Zenodo → GitHub/GitLab tab → toggle on the repo. (Zenodo also supports GitLab via the Software Heritage backend if your institution doesn't have direct GitLab–Zenodo.)

- [ ] **G.2.2** Tag the final release in git:
  ```bash
  cd /Users/davidwickerhf/Projects/university/m2-2_steganography
  git tag -a v1.0-final -m "Final paper submission with SRNet+DCTR supplementary analysis"
  git push origin v1.0-final
  ```
  Zenodo auto-imports tagged releases and mints a DOI within ~1 hour.

- [ ] **G.2.3** Add the DOI to the paper's footer or acknowledgements:
  ```latex
  \footnote{Code, models, and data: \url{https://doi.org/10.5281/zenodo.XXXXXXX}}
  ```

---

## Phase H — Pre-submission QA

Wall-clock: ~1 hour, low-effort but high-value.

- [ ] **H.1** Re-read the supplementary section V.J end-to-end. Check that every claim is backed by a table or figure.

- [ ] **H.2** Confirm the leakage-guard claim is correct: re-run inference and verify the script refuses if you point it at a training run by accident:
  ```bash
  # this MUST raise the leakage error
  python scripts/inference/apply_srnet_to_run.py \
      --run models/training_v1/training_manifests/../  # fake-path the training run
      --models models/training_v1/srnet_lsb_low_v1.pt \
      --out /tmp/leakage_test.csv 2>&1 | grep -q "REFUSING TO RUN" && echo "leakage guard works"
  ```

- [ ] **H.3** Run a final `pdflatex` + visual scan for typos in the new V.J section.

- [ ] **H.4** Have at least one team member read the new V.J section cold.

- [ ] **H.5** Submit (or hand off to your supervisor for sign-off).

---

## What you DO NOT do

| Action | Why not |
|---|---|
| Re-run classical-detector inference | 648k rows already computed and frozen in `predictions/predictions.csv` |
| Re-run `metrics/` or `figures/` for classical detectors | Same — those numbers are pre-registered and unchanged in v2 |
| Merge learned + classical predictions into one analysis | Rejected (Option 2) — would silently rewrite the primary verdicts post-hoc |
| Upload the 30 GB training images to HuggingFace | Regeneratable from manifests + seeds + HF Inference API |
| Re-embed the test set stegos | Same 108,000 stegos used for both classical and learned inference |

---

## Decision log (for paper Methods section)

Final wording you can paste verbatim into v2:

> *"The learned-detector analysis (Section V.J) is reported as a supplementary
> robustness check on the pre-registered primary findings. It uses the same
> 3,000-group test set as the primary analysis; the only addition is two
> learned detectors (SRNet for the spatial branch, DCTR for the frequency
> branch). Per the original proposal (Section III.D), learned detectors were
> excluded from the primary analysis to avoid training-set bias confounding
> the carrier-source contrast. We address that concern in two ways: (i) by
> training on a 3,000-group caption-matched corpus disjoint from the test
> set by caption ID, which avoids the cover-source-mismatch problem that
> arises when learned detectors are trained on BOSSBase and applied to
> diffusion covers; and (ii) by reporting learned-detector results in a
> parallel stratum family rather than merging them into the pre-registered
> Bonferroni–Holm correction. The supplementary results corroborate / refine
> / contradict (delete as applicable) the primary classical-detector
> findings — see Section V.J for the per-RQ comparison."*

---

## Estimated total wall-clock

| Phase | Duration |
|---|---|
| A — retrieve | 5 min |
| B — destroy instance | 30 sec |
| C — apply trained detectors | 30–45 min |
| D — supplementary analysis | 15–30 min |
| E — fill placeholders | 30–45 min |
| F — rebuild PDF | 3 min |
| G — HF + Zenodo archival | 30 min active + overnight |
| H — pre-submission QA | 1 hour |
| **Total focused work** | **~2.5–3 hours** |
| **Cost** | **$0** (laptop only) |

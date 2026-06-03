# Poster figures

Seven purpose-built SVG figures, one per content point on the poster. All
authored in the same brand palette (umdark `#001C3D` / umlight `#4A90C4`
/ umorange `#E84E10` / umgray `#6B7280`) and typographic register
(Space Grotesk headings, Inter body, JetBrains Mono for numerical
values). All data points come straight from the paper; the source
sections / tables are cited inline at the top of each SVG.

## Figure manifest

| File | Supports | Paper source |
|---|---|---|
| `rq1.svg` | **RQ1**: 5 of 6 detectors find AI carriers easier (lollipop chart with the χ²-spatial outlier highlighted) | §IV.B, Fig. 5 strip-plot data, averaged across payload |
| `rq2.svg` | **RQ2**: SDXL and FLUX are interchangeable (forest plot: all detectors and the pooled estimate inside the ±0.025 equivalence band) | §IV.C, Table 5 |
| `rq3.svg` | **RQ3 (classical)**: real-vs-AI gap shrinks with payload — six classical detectors + pooled (−4.9 → −2.8 → −1.6 pp), χ²-spatial outlier called out | §IV.B per-stratum + §IV.D pooled |
| `rq3_learned.svg` | **RQ3 (learned)**: SRNet and DCTR under matched (V1, gray) vs real-only (V2a, red) training — direction flips, V2a SRNet peaks at +39 pp | §IV.D ablation, Table 11 per-stratum ΔAUC |
| `rq4.svg` | **RQ4**: which branch wins depends on payload (paired bars per payload, with per-payload winner labels) | §IV.E inline table |
| `deep_learning_cheat.svg` | **Deep-learning cheat (V2a)**: SRNet looks source-invariant under matched training, fails on AI under real-only training (two-panel paired bars with −44 pp gap callout) | §V.D, Table 11 (V1 vs V2a), SRNet @ medium payload |
| `tile_local.svg` | **Tile-local χ²-DCT**: +9 pp on BOSSBase JSteg, chance on histogram-preserving OutGuess (paired bars at Q=75 / Q=95 for both embedders) | §VII.A, Table 13 (BOSSBase tile-local results) |

## How to use them on the poster

Reference each SVG by relative path from `poster.html`:

```html
<img src="figures/rq1.svg" alt="5 of 6 detectors find AI carriers easier">
```

SVGs are vector, so they re-scale cleanly at A0 print without any
quality loss. The poster HTML / browser print pipeline handles them
identically to PNGs.

## Triptych hook visual

The "spot-the-secret" elephant (or Yoda) triptych at the top of the
poster lives under `../hook/` because the source images are pipeline
artefacts (cover → LSB-embedded stego variants), not paper figures.

## Legacy paper PNGs

Earlier versions of the poster referenced PNG exports from the paper
itself (`headline_rq1.png`, `v1_vs_v2a_heatmap.png`, etc.). Those have
been moved to `legacy_png/` for reference; the SVG redraws above are
the canonical assets for the poster going forward.

## Regenerating

Open any SVG in a text editor — they're hand-written and self-contained
with the data and rationale annotated at the top. If a paper number
changes, edit the SVG directly.

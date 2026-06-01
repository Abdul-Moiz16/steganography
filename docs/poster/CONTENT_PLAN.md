# Poster content plan

Working draft for the A0 portrait poster. The goal is **engagement first,
exhaustiveness second**: a passer-by should stop, ask one question, then
have the answer at eye level. The full paper does the comprehensive job;
the poster's job is to *pull people in*.

## What we got wrong in the previous drafts

| Pass | Issue |
|---|---|
| v1 (sparse hero) | Too much white space, no information density, no engagement |
| v2 (dense 9-figure grid) | Too many figures crowded together, reads as a research dashboard not a story, still has whitespace because so many charts have tall white plot areas |

Both failed because they tried to be the paper. A poster is **not** a paper.
It is a **hook + one or two memorable results + a way to learn more**.

## Proposed redesign principles

1. **One catchy visual hook above the fold.** Not a chart. Something a
   non-specialist understands in 2 seconds. (See "The hook" below.)
2. **Two or three findings, not five.** Each finding gets one chart and
   one sentence. Quality over quantity.
3. **An invitation to interact.** The repo has a working web demo at
   `/toolbox` where anyone can encode a message into an image and watch
   the chi-square detector light up. This is the killer feature for a
   poster session: "scan this and try it on your phone."
4. **No table of metadata for its own sake.** The factorial knobs, the
   pre-registration apparatus, etc.: necessary in the paper, but they
   are not what people stop walking to read. Reference the paper for
   them.

## Proposed structure

### Banner (top, 50 mm)
UM brand band, unchanged.

### Title block (~80 mm)
- Two-line headline title
- Authors right-aligned
- Affiliation line below

### Hook strip (~110 mm) — **THE CATCHY VISUAL**
The single most engaging element on the poster. Three options, in order
of how much we like them:

**Option A: "Spot the secret" image triptych** (recommended)
Three 200x200 thumbnails side by side:
1. A real photograph (e.g., COCO cat image, original)
2. The same image with a 50-character secret hidden via LSB
3. The same image with a 30 KB secret hidden via LSB
Caption underneath: "All three look identical to you. One is the
original; two carry hidden payloads at 0.05 and 0.30 bpp. Our
detectors tell them apart with AUC up to 0.99." Then the question:
**"Does it matter whether the cover is a real photo or AI-generated?"**

**Option B: Cover-stego visual + chi-square score swing**
Show one cover and one stego image plus an annotated chi-square score
distribution showing how the test "lights up" between them. More
mechanistic, slightly less catchy.

**Option C: Real photo vs SDXL vs FLUX side-by-side** of the same
caption ("a cat sitting on a windowsill"), demonstrating the carrier-
matched design visually. Educational, less "wow".

The visual sits at the top of the poster, full width, with the
question text overlaid or beside it.

### Findings strip (~280 mm) — THREE PANELS, NO MORE
Each panel: one hero number, one sentence, one supporting figure.

**Panel 1: "Diffusion carriers are slightly easier to attack"**
- Hero: **5/6** detectors agree (AI-easier)
- Number: pooled `|Delta_AUC| ~ 0.013`, amplified `3-7x` under pAUC
- Figure: `headline_rq1.png` (the per-detector bar chart)

**Panel 2: "But the deep learned detector is fooled by its training set"**
- Hero: **+0.44 AUC** gap on AI carriers when SRNet is trained on real
  photos only
- Figure: `v1_vs_v2a_heatmap.png` (the matched-vs-real-only heatmap)
- One-sentence mechanism: "It interprets diffusion-decoder noise as
  the LSB perturbation it was trained to detect."

**Panel 3: "A new detector wins on the field-reference dataset"**
- Hero: **+0.09 AUC** on BOSSBase 1.01 vs the textbook Westfeld test
- Figure: small 4-row BOSSBase table (Q75/Q95 x JSteg/OutGuess)
- One-sentence: "Localising the chi-square test to disjoint DCT tiles
  beats the global baseline on the canonical benchmark."

### Method panel (~120 mm) — COMPACT
One narrow side-strip OR one full-width band with a single visual
showing the pipeline:

`covers (real + SDXL + FLUX) -> embed -> 6 detectors -> paired DeLong`

Bullet underneath: "3,000 caption-matched groups; 6 classical + 2
learned detectors; pre-registered Bonferroni-Holm." That is enough.

### Try it yourself (~120 mm) — **THE SECOND ENGAGEMENT BEAT**

This is the killer panel. A QR code that opens the live toolbox demo:
"Encode a message into a real photograph or an AI image, watch which
detectors catch it, in your browser." Big call-to-action lettering,
prominent QR, screenshot of the toolbox UI alongside.

Two QRs total:
- **Try the demo** -> `/toolbox` route of the explorer (need to deploy
  somewhere accessible — see open questions below)
- **Code + paper** -> GitLab repo (already have)

### Limitations / next steps strip (~80 mm)
One thin strip near the bottom listing in one or two lines:
- Scope: non-adaptive LSB embeddings on JPEG Q=95; adaptive embeddings
  (J-UNIWARD etc.) deliberately out of scope
- Confound: frequency-branch real covers carry double-JPEG history
- What's next: extend to additional diffusion families (SD3,
  FLUX.1-dev, Midjourney); cross-payload T-sweep on caption-matched
  corpus

### Footer (~50 mm)
Authors + affiliation + paper version + repo URL. Compact.

## Concrete figure list (only the ones we actually feature)

| Figure | Used for | Source |
|---|---|---|
| Spot-the-secret triptych (NEW) | Hook | Need to generate from real cover + stego pair |
| Headline AUC bars | Panel 1 | `figures/v4_paper/headline_rq1.png` |
| Matched-vs-real-only heatmap | Panel 2 | `figures/v4_paper/v1_vs_v2a_heatmap.png` |
| BOSSBase table (text/HTML) | Panel 3 | Inline HTML |
| Pipeline diagram | Method | Maybe re-use Fig 3 from paper, or draw a 5-stage strip in HTML |
| Toolbox screenshot | Try it yourself | Screenshot of `/toolbox` |

That is **3 figures + 1 table + 1 hook visual + 1 demo screenshot = 6
visual elements** total. The dense v2 had 10. Less crowded, more
breathing room for the elements that matter.

## What we deliberately drop

- The RQ verdicts mini-row (RQ1...RQ5 boxes). The verdict labels read
  as jargon to passers-by. Keep "5 of 6 detectors agree" instead.
- The factorial knobs table. Reference it in one line.
- The chi-square spatial reversal mechanism box plot.
- The DCTR EOOB ladder. (DCTR shows the same V2a pattern at smaller
  magnitude; the heatmap already tells that story.)
- The four small RQ2/RQ4/RQ5 panels.
- The forest plots.

If anyone wants those, the QR code -> paper PDF.

## Open questions for you

1. **Hook visual**: A, B, or C? (I'd push for A.)
2. **Demo QR target**: Is the `/toolbox` route deployed somewhere
   public, or do we need to host it temporarily for the poster session?
   If it's not yet live, the QR could just go to the repo and we drop
   the "Try it yourself" framing.
3. **Pipeline diagram**: Re-use the v4 paper's Fig 3 (PNG), or want me
   to draw a fresh HTML/CSS one in the brand palette?
4. **Authors header**: keep current size/position, or move to the
   bottom footer to give the title and hook more room at the top?

Once you confirm, I'll do a v3 build matching this plan.

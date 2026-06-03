# Research Question Verdicts

Auto-generated from the per-experiment contrast CSVs. Drop this into the report's results overview or use the JSON sibling for downstream cross-referencing.

## RQ1 — Real vs pooled ML carrier sources

- **Verdict:** —  not supported
- **Test:** DeLong + Bonferroni–Holm (confirmatory)
- **Strata evaluated:** 3
- **Significant after Holm (α=0.05):** 0 / 3  (+ 0, − 0)
- **Pooled Δ-AUC (inverse-variance):** -0.0167  (95% CI [-0.0337, +0.0003])

## RQ2 — SDXL vs PixArt-α within ML

- **Verdict:** —  not supported
- **Test:** DeLong + Bonferroni–Holm (confirmatory)
- **Strata evaluated:** 3
- **Significant after Holm (α=0.05):** 0 / 3  (+ 0, − 0)
- **Pooled Δ-AUC (inverse-variance):** -0.0513  (95% CI [-0.2210, +0.1185])

## RQ3 — Payload-level interaction with carrier source

- **Verdict:** ·  no data
- **Test:** Real–ML AUC gap across payload levels (exploratory)
- **Strata evaluated:** 3

## RQ4 — Embedding branch × source interaction

- **Verdict:** ·  no data
- **Test:** Wald CI on (spatial gap − frequency gap) (exploratory)
- **Strata evaluated:** 0
- **Strata with 95% CI excluding 0:** 0 / 0  (+ 0, − 0)

## RQ5 — Encryption invariance (plain vs AES-256-CBC)

- **Verdict:** ✔  supported
- **Test:** Paired DeLong, equivalence check within ±2.5% AUC margin
- **Strata evaluated:** 9
- **Strata within ±0.025 AUC margin:** 9 / 9  (violating: 0)
- **Pooled Δ-AUC (inverse-variance):** +0.0021  (95% CI [-0.0046, +0.0087])

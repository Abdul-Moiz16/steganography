"""Apply trained SRNet checkpoints to an existing run, AS-IS.

This script loads pre-trained SRNet checkpoints (produced by
scripts/training/train_srnet.py) and runs inference on every (cover,
stego) pair in the given run. Output is appended to a
``predictions_srnet.csv`` matching the schema of the existing
``predictions.csv``, so the main analysis pipeline can incorporate the
SRNet rows by simple file concatenation.

The trained model is treated as a frozen, immutable artefact. This
script does NOT fine-tune, train, or modify the checkpoint in any way.

Usage
-----
    python scripts/inference/apply_srnet_to_run.py \
        --run runs/prototype_full_20260513_005357_p8765 \
        --models models/srnet_lsb_low_v1.pt \
                 models/srnet_lsb_medium_v1.pt \
                 models/srnet_lsb_high_v1.pt \
        --out runs/prototype_full_20260513_005357_p8765/predictions_srnet.csv

The script will:
  1. Refuse to run if any model's training_run_hash matches the test
     run (guards against train/test leakage).
  2. For each model, identify its (method, payload) cell from the
     checkpoint config and run inference on the matching subset of
     the test run.
  3. Stream predictions to the output CSV as it goes (resumable on
     interrupt).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Make runnable without PYTHONPATH=.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Lazy torch import.


PREDICTION_FIELDS = [
    "detector", "group_id", "source", "method",
    "payload_level", "encryption", "label", "score",
]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True,
                   help="Test run directory (e.g. runs/prototype_full_...).")
    p.add_argument("--models", type=Path, nargs="+", required=True,
                   help="One or more SRNet checkpoints (.pt files).")
    p.add_argument("--out", type=Path, required=True,
                   help="Output predictions CSV.")
    p.add_argument("--device", default="auto")
    p.add_argument("--batch-size", type=int, default=32)
    args = p.parse_args()

    import torch
    from src.detection_learned.srnet import SRNet
    from src.detection_learned.data import enumerate_cover_groups

    # ---------------- Setup ----------------
    device = _resolve_device(args.device)
    print(f"[apply-srnet] device={device}  run={args.run}")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # ---------------- Leakage guard ----------------
    run_hash = _hash_run(args.run)
    for ckpt_path in args.models:
        ckpt = torch.load(ckpt_path, map_location="cpu")
        if ckpt.get("training_run_hash") == run_hash:
            raise RuntimeError(
                f"REFUSING TO RUN: checkpoint {ckpt_path} was trained on the "
                f"same run we're now testing on ({args.run}). This would be "
                "data leakage. Train on a different run."
            )

    # ---------------- Open output CSV ----------------
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PREDICTION_FIELDS)
        writer.writeheader()

        # ---------------- Iterate over checkpoints ----------------
        for ckpt_path in args.models:
            ckpt = torch.load(ckpt_path, map_location=device)
            cfg = ckpt["config"]
            method, payload = cfg["method"], cfg["payload"]
            print(f"[apply-srnet] {ckpt_path.name}: {method}/{payload}  "
                  f"(val_auc={ckpt['val_auc']:.4f})")

            model = SRNet().to(device)
            model.load_state_dict(ckpt["model_state_dict"])
            model.eval()

            # Use the de-duplicated cover-group view: each physical cover
            # image is loaded and scored exactly ONCE, and the score is
            # written into the predictions CSV twice (once per encryption
            # value) since the existing pipeline's row schema indexes
            # cover predictions by encryption even though the cover bytes
            # are identical regardless of encryption. Stegos are scored
            # independently because they are physically different files.
            #
            # Gotcha #2: no duplicate cover loads => no wasted compute.
            # Gotcha #3: cover scores are guaranteed identical across
            # encryption rows because we score the cover image once.
            cover_groups = enumerate_cover_groups(args.run, method=method,
                                                   payload_level=payload, split=None)
            n_cov = len(cover_groups)
            n_ste = sum(len(cg.stego_paths) for cg in cover_groups)
            print(f"  {n_cov} covers + {n_ste} stegos to score "
                  f"(covers loaded once, written {n_ste} times with shared score)")
            _score_cover_groups(model, cover_groups, device, args.batch_size,
                                  detector_name="srnet", writer=writer, fh=fh)

    print(f"[apply-srnet] DONE -> {args.out}")


def _score_cover_groups(model, cover_groups, device, batch_size, *,
                          detector_name, writer, fh):
    """Score each cover once and each stego once; emit prediction rows.

    Cover scores are emitted ONE ROW PER ENCRYPTION variant (with the
    same numeric score), matching the existing predictions.csv schema
    in which cover rows are indexed by (group, source, method, payload,
    encryption, label=0). Stegos are emitted with the encryption value
    matching their physical file.
    """
    import torch
    from PIL import Image
    import numpy as np

    def _load(path):
        with Image.open(path) as im:
            arr = np.asarray(im.convert("L"), dtype="float32")
        return torch.from_numpy(arr)[None]   # (1, H, W)

    # Build the list of physical images to score: one per cover, plus
    # one per stego variant. We tag each entry with the metadata needed
    # to emit the correct prediction rows after scoring.
    @dataclass_lite()
    class _ScoreEntry:
        path: Path
        kind: str               # "cover" or "stego"
        group_id: int
        source: str
        method: str
        payload_level: str
        encryption: str | None  # set for stegos; None for covers (handled at write time)
        cover_group: "object"   # CoverGroup (typed loosely to avoid forward ref)

    entries: list = []
    for cg in cover_groups:
        entries.append(_ScoreEntry(
            path=cg.cover_path, kind="cover",
            group_id=cg.group_id, source=cg.source,
            method=cg.method, payload_level=cg.payload_level,
            encryption=None, cover_group=cg,
        ))
        for enc, ste_path in cg.stego_paths.items():
            entries.append(_ScoreEntry(
                path=ste_path, kind="stego",
                group_id=cg.group_id, source=cg.source,
                method=cg.method, payload_level=cg.payload_level,
                encryption=enc, cover_group=cg,
            ))

    # Score in batches
    n = len(entries)
    for i in range(0, n, batch_size):
        batch = entries[i:i+batch_size]
        x = torch.stack([_load(e.path) for e in batch]).to(device, non_blocking=True)
        with torch.no_grad():
            logits = model(x)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
        for entry, score in zip(batch, probs):
            score_str = f"{float(score):.6f}"
            if entry.kind == "cover":
                # Emit one cover row per known encryption variant. The
                # cover bytes are identical regardless of encryption, so
                # the score is shared across all variants. This matches
                # the existing predictions.csv schema where cover rows
                # are indexed by encryption alongside stego rows.
                for enc in entry.cover_group.stego_paths.keys():
                    writer.writerow({
                        "detector": detector_name,
                        "group_id": entry.group_id,
                        "source": entry.source,
                        "method": entry.method,
                        "payload_level": entry.payload_level,
                        "encryption": enc,
                        "label": 0,
                        "score": score_str,
                    })
            else:
                writer.writerow({
                    "detector": detector_name,
                    "group_id": entry.group_id,
                    "source": entry.source,
                    "method": entry.method,
                    "payload_level": entry.payload_level,
                    "encryption": entry.encryption,
                    "label": 1,
                    "score": score_str,
                })
        fh.flush()


def dataclass_lite():
    """Tiny local dataclass decorator -- avoids a module-level import."""
    from dataclasses import dataclass
    return dataclass


def _resolve_device(name: str):
    import torch
    if name == "auto":
        if torch.cuda.is_available(): return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(name)


def _hash_run(run_dir: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    manifest = run_dir / "manifests" / "raw_cover_index_real.csv"
    if manifest.exists():
        h.update(manifest.read_bytes())
    return h.hexdigest()[:16]


if __name__ == "__main__":
    main()

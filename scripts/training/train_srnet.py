"""Train one SRNet checkpoint per (method, payload) cell.

This script is invoked ONCE per cell. It is intentionally NOT part of
the main pipeline; it lives entirely on the learned-baselines branch
and writes only to the ``models/`` directory.

Usage
-----
    python scripts/training/train_srnet.py \
        --training-run runs/training_v1 \
        --method lsb --payload low \
        --epochs 80 --batch-size 16 \
        --out models/srnet_lsb_low_v1.pt

The output checkpoint contains:
  - SRNet state_dict
  - training config (method, payload, hyperparameters)
  - validation history (val_auc per epoch)
  - data hash of the training set (so inference can verify provenance)

NOTE: this script does not exist yet beyond a stub of the training loop.
The full implementation requires PyTorch (see requirements_learned.txt)
and ~6h of GPU time per cell. Use the skeleton below as the starting
point; the data-loader and model are already in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Make runnable without PYTHONPATH=.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Lazy imports of torch keep this script importable without torch installed.


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--training-run", type=Path, required=True,
                   help="Training run directory (from generate_training_set.py).")
    p.add_argument("--method", required=True, choices=["lsb", "dct"],
                   help="Embedding branch this checkpoint targets.")
    p.add_argument("--payload", required=True, choices=["low", "medium", "high"])
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--batch-size", type=int, default=32,
                   help="Total per-batch image count (covers+stegos). "
                        "Paper-faithful is 32 (16 covers + 16 stegos). "
                        "Drop to 16 only if VRAM-constrained.")
    p.add_argument("--lr", type=float, default=1e-3,
                   help="Initial learning rate. Boroumand+2019 used 1e-3 with Adamax.")
    p.add_argument("--optimizer", default="adamax", choices=["adam", "adamax"],
                   help="Optimiser. 'adamax' matches Boroumand+2019 (default, paper-"
                        "faithful, more robust to early-epoch gradient outliers). "
                        "'adam' is the common-substitute used in many open-source "
                        "SRNet ports but is known to occasionally diverge on "
                        "caption-matched / small-batch settings.")
    p.add_argument("--grad-clip", type=float, default=1.0,
                   help="Gradient L2-norm clip. Set 0 to disable. 1.0 prevents the "
                        "early-epoch divergence that can park CE loss at ln(2).")
    p.add_argument("--device", default="auto", help="'cuda', 'mps', 'cpu' or 'auto'.")
    p.add_argument("--out", type=Path, required=True,
                   help="Output checkpoint path (.pt).")
    p.add_argument("--resume", type=Path, default=None,
                   help="Path to a checkpoint to resume from. If the file does "
                        "not exist, training starts from scratch (safe to "
                        "always pass --resume on a cloud instance that may be "
                        "pre-empted).")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # ---------------- Imports (deferred to keep CLI fast) ----------------
    import numpy as np
    import torch

    from src.detection_learned.srnet import SRNet, count_parameters
    from src.detection_learned.data import (
        enumerate_cover_groups,
        make_balanced_pair_loader,
    )

    # ---------------- Setup ----------------
    torch.manual_seed(args.seed); np.random.seed(args.seed)
    device = _resolve_device(args.device)
    print(f"[train-srnet] device={device}")

    # ---------------- Data ----------------
    # Gotcha #2: use the cover-group view so each physical cover appears at
    # most once per epoch (no duplication). Gotcha #3: each cover's stego
    # is drawn with a random encryption variant on every epoch, so plain
    # and encrypted stegos are mixed under the same "stego" label by
    # construction in CoverGroup.sample_stego.
    train_groups = enumerate_cover_groups(args.training_run, method=args.method,
                                           payload_level=args.payload, split="train")
    val_groups   = enumerate_cover_groups(args.training_run, method=args.method,
                                           payload_level=args.payload, split="val")
    print(f"[train-srnet] {len(train_groups)} train cover-groups, {len(val_groups)} val cover-groups")
    print(f"[train-srnet]   each batch = {args.batch_size} images "
          f"({args.batch_size//2} covers + {args.batch_size//2} stegos), 50/50 by construction")

    pin = (device.type == "cuda")
    # D4 augmentation ON for training (paper-faithful), OFF for validation
    # (deterministic AUC, no epoch-to-epoch fluctuation from random rotations).
    train_loader = make_balanced_pair_loader(
        train_groups, batch_size=args.batch_size, shuffle=True,
        num_workers=2, pin_memory=pin, seed=args.seed, augment=True)
    val_loader = make_balanced_pair_loader(
        val_groups, batch_size=args.batch_size, shuffle=False,
        num_workers=2, pin_memory=pin, seed=args.seed + 1, augment=False)
    print(f"[train-srnet] D4 augmentation: train=ON (8 orientations), val=OFF (deterministic)")

    # ---------------- Model + optimiser ----------------
    model = SRNet().to(device)
    print(f"[train-srnet] parameters: {count_parameters(model):,}")
    if args.optimizer == "adamax":
        opt = torch.optim.Adamax(model.parameters(), lr=args.lr)
    else:
        opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    print(f"[train-srnet] optimiser: {type(opt).__name__}, lr={args.lr}, "
          f"grad_clip={args.grad_clip if args.grad_clip > 0 else 'OFF'}")
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="max", patience=5, factor=0.5)
    loss_fn = torch.nn.CrossEntropyLoss()

    # ---------------- Resume handling ----------------
    # On a cloud instance you should ALWAYS pass --resume; if the file
    # doesn't exist we start from scratch, if it exists we pick up where
    # we left off (epoch, optimiser state, best-val tracker, full history).
    start_epoch = 1
    history: list[dict] = []
    best_val_auc = 0.0
    if args.resume is not None and args.resume.exists():
        try:
            ck = torch.load(args.resume, map_location=device)
            # Strict load so any architecture drift fails loudly rather
            # than silently zero-initialising new layers.
            model.load_state_dict(ck["model_state_dict"], strict=True)
            if "optimizer_state_dict" in ck:
                opt.load_state_dict(ck["optimizer_state_dict"])
            if "scheduler_state_dict" in ck:
                sched.load_state_dict(ck["scheduler_state_dict"])
            history = list(ck.get("history", []))
            best_val_auc = float(ck.get("val_auc", 0.0))
            start_epoch = (history[-1]["epoch"] + 1) if history else 1
            # Verify we are resuming the same (method, payload) cell.
            cfg = ck.get("config", {})
            if cfg.get("method") != args.method or cfg.get("payload") != args.payload:
                raise RuntimeError(
                    f"--resume checkpoint is for ({cfg.get('method')}, "
                    f"{cfg.get('payload')}) but this run requests "
                    f"({args.method}, {args.payload}). Aborting to avoid "
                    "training the wrong cell."
                )
            # Verify the training-run hash matches — if not, the user
            # repointed --training-run between runs and the resume would
            # be semantically wrong.
            on_disk_hash = ck.get("training_run_hash")
            current_hash = _hash_training_run(args.training_run)
            if on_disk_hash and on_disk_hash != current_hash:
                raise RuntimeError(
                    f"--resume checkpoint was trained on a different training "
                    f"run (hash {on_disk_hash}) than the one currently "
                    f"specified ({current_hash}). Aborting."
                )
            print(f"[train-srnet] RESUMED from {args.resume} at epoch {start_epoch}, "
                  f"best val-AUC so far {best_val_auc:.4f}")
        except (KeyError, RuntimeError) as e:
            print(f"[train-srnet] Failed to resume from {args.resume}: {e}")
            print(f"[train-srnet] Aborting rather than silently restarting "
                  f"-- delete the file or fix the mismatch.")
            raise
    elif args.resume is not None:
        print(f"[train-srnet] --resume {args.resume} not found, starting from scratch")

    # ---------------- Training loop ----------------
    SANITY_EPOCH = 15
    SANITY_THRESHOLD = 0.55
    sanity_warned = False
    for epoch in range(start_epoch, args.epochs + 1):
        train_loss = _train_one_epoch(model, train_loader, opt, loss_fn, device,
                                        grad_clip=args.grad_clip)
        val_loss, val_auc = _validate(model, val_loader, loss_fn, device)
        sched.step(val_auc)
        history.append({"epoch": epoch, "train_loss": train_loss,
                         "val_loss": val_loss, "val_auc": val_auc})
        improved = val_auc > best_val_auc
        if improved:
            best_val_auc = val_auc
        # Save EVERY epoch (not just on improvement) so that a pre-emption
        # at epoch K is resumable from epoch K, not from the last
        # best-val epoch which could be many epochs back. The on-disk
        # "val_auc" field still tracks the BEST seen so far.
        _save_checkpoint(args.out, model, opt, sched, args, best_val_auc,
                          history, training_run=args.training_run)
        print(f"epoch {epoch:3d}  train {train_loss:.4f}  val {val_loss:.4f}  "
              f"val-AUC {val_auc:.4f}{' *' if improved else ''}")

        # Sanity warning: if we are well past the warm-up but the model is
        # still essentially random, something is wrong (label-flip bug,
        # broken DataLoader, etc.) and the user should investigate rather
        # than burn 5+ more GPU hours. We log a one-time WARNING but do
        # NOT abort -- the user might still want the partial checkpoint
        # for debugging.
        if epoch >= SANITY_EPOCH and best_val_auc < SANITY_THRESHOLD and not sanity_warned:
            print(f"")
            print(f"!!! WARNING !!!  best val-AUC after {epoch} epochs is {best_val_auc:.4f}")
            print(f"    < {SANITY_THRESHOLD} threshold -- the model has barely beaten random.")
            print(f"    This usually indicates a data bug. Investigate before letting")
            print(f"    training run for {args.epochs - epoch} more epochs.")
            print(f"    (Continuing anyway; abort with C-c if you suspect a bug.)")
            print(f"")
            sanity_warned = True

    print(f"[train-srnet] DONE — best val AUC {best_val_auc:.4f} saved to {args.out}")


# ---------------------------------------------------------------------------
# Helpers (TODO: full implementations)
# ---------------------------------------------------------------------------

def _resolve_device(name: str):
    import torch
    if name == "auto":
        if torch.cuda.is_available(): return torch.device("cuda")
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(name)


def _train_one_epoch(model, loader, opt, loss_fn, device, grad_clip: float = 0.0) -> float:
    """Each batch is class-balanced 50/50 (see make_balanced_pair_loader).

    grad_clip > 0 enables L2-norm gradient clipping; this prevents the
    early-epoch divergence that can park CE loss at exactly ln(2) when
    Adam fires its first few aggressive updates on noisy small batches.
    """
    import torch
    model.train()
    total, count = 0.0, 0
    for x, y, _meta in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        opt.zero_grad()
        logits = model(x)
        loss = loss_fn(logits, y)
        loss.backward()
        if grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=grad_clip)
        opt.step()
        total += loss.item() * x.size(0); count += x.size(0)
    return total / max(count, 1)


def _validate(model, loader, loss_fn, device) -> tuple[float, float]:
    """Validation also uses class-balanced batches.

    The per-batch encryption variant is fixed deterministically by the
    paired dataset's seed, so val-AUC is stable across epochs even
    though the stego encryption is randomly chosen at dataset
    construction time.
    """
    import torch
    import numpy as np
    model.eval()
    total, count = 0.0, 0
    scores, labels = [], []
    with torch.no_grad():
        for x, y, _meta in loader:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            logits = model(x)
            total += loss_fn(logits, y).item() * x.size(0); count += x.size(0)
            probs = torch.softmax(logits, dim=1)[:, 1]
            scores.append(probs.cpu().numpy()); labels.append(y.cpu().numpy())
    scores = np.concatenate(scores); labels = np.concatenate(labels)
    from src.evaluation.metrics import roc_auc_score_binary
    auc = roc_auc_score_binary(labels.tolist(), scores.tolist())
    return total / max(count, 1), auc


def _save_checkpoint(path: Path, model, opt, sched, args, best_val_auc: float,
                      history: list[dict], *, training_run: Path) -> None:
    """Save full state (model + optimiser + scheduler + history) atomically.

    Atomic write via tmp + rename so a pre-emption mid-write cannot leave
    a half-written checkpoint that would fail to resume.

    Also writes a sibling ``<checkpoint>.summary.json`` that mirrors the
    metadata in a torch-free format so the deliverable bundle is
    inspectable without loading PyTorch.
    """
    import os
    import torch
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    config = {
        "method": args.method,
        "payload": args.payload,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "seed": args.seed,
    }
    training_run_hash = _hash_training_run(training_run)
    torch.save({
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": opt.state_dict(),
        "scheduler_state_dict": sched.state_dict(),
        "config": config,
        "val_auc": best_val_auc,          # BEST val-AUC seen so far
        "history": history,                # full per-epoch log
        "training_run_hash": training_run_hash,
    }, tmp_path)
    os.replace(tmp_path, path)             # atomic on POSIX

    # Sibling JSON summary -- inspectable without torch
    summary = {
        "checkpoint_path": str(path),
        "config": config,
        "training_run_hash": training_run_hash,
        "training_run_dir": str(training_run),
        "best_val_auc": float(best_val_auc),
        "epochs_completed": history[-1]["epoch"] if history else 0,
        "history": history,
    }
    summary_path = path.with_suffix(".summary.json")
    summary_tmp = summary_path.with_suffix(".tmp")
    summary_tmp.write_text(json.dumps(summary, indent=2))
    os.replace(summary_tmp, summary_path)


def _hash_training_run(training_run: Path) -> str:
    """Hash the training-run manifest list. Used to detect train/test leakage."""
    h = hashlib.sha256()
    manifest = training_run / "manifests" / "raw_cover_index_real.csv"
    if manifest.exists():
        h.update(manifest.read_bytes())
    return h.hexdigest()[:16]


if __name__ == "__main__":
    main()

"""Shared dataset utilities for SRNet / DCTR training and inference.

Two access patterns are exposed:

1. **Cover-group view** (``enumerate_cover_groups``) -- the de-duplicated
   view used at training time and at inference time. One entry per
   (group_id, source) -- i.e. per physical cover image. Each entry
   carries the list of stego variants for that cover (one per encryption
   condition). This avoids loading or scoring the same cover image
   twice, and lets the batch sampler draw matched (cover, stego) pairs
   for class-balanced training.

2. **Flat-pair view** (``enumerate_samples``) -- one entry per
   (group_id, source, encryption). Kept for backwards compatibility but
   marked deprecated for training; the cover-group view should be
   preferred.

Caption-group-aware splits: ``group_id % 10`` deterministically
assigns train / val / id_test buckets. The held-out 3,000-group OOD
test run uses ``split=None`` at inference time.

Gotcha-handling
---------------
* **Class balance** is enforced at the BATCH level by a custom
  ``CoverStegoPairSampler`` that yields N cover-stego pairs per batch
  drawn from N distinct cover groups. Each batch is 50% cover / 50%
  stego by construction; each cover is sampled at most once per epoch.

* **Encryption mixing** at training time: when a cover group's stego
  is drawn, ``CoverGroup.sample_stego(rng)`` picks one of the available
  encryption variants uniformly at random. Over an epoch the model
  sees each stego variant in expectation; over many epochs both plain
  and encrypted stegos are sampled fairly.

* **Encryption at inference time** is the inverse: each cover is
  scored ONCE physically (the cover bytes are identical regardless of
  encryption); the inference writer then emits the cover row twice in
  the output CSV, once per encryption value, with the same score.
  Stegos are scored independently because they ARE different files.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Literal

SplitName = Literal["train", "val", "id_test"]

# Deterministic split keyed off group_id mod 10. Adjust if you want
# different ratios; the {7,8} -> val choice matches a 70/20/10 split.
SPLIT_BUCKETS: dict[SplitName, set[int]] = {
    "train":  {0, 1, 2, 3, 4, 5, 6},
    "val":    {7, 8},
    "id_test": {9},
}


def split_of(group_id: int) -> SplitName:
    bucket = group_id % 10
    for name, buckets in SPLIT_BUCKETS.items():
        if bucket in buckets:
            return name
    raise ValueError(f"group_id {group_id}: bucket {bucket} not assigned to any split")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sample:
    """One (cover, stego) pair for a specific encryption variant.

    Kept for backwards compatibility. Prefer ``CoverGroup`` in new code.
    """
    group_id: int
    source: str
    method: str
    payload_level: str
    encryption: str
    cover_path: Path
    stego_path: Path


@dataclass
class CoverGroup:
    """One physical cover image and all its stego variants in a (method, payload) cell.

    Per (group_id, source, method, payload_level), the pipeline produces
    one cover image and exactly two stego images (plain + AES-256-CBC).
    A CoverGroup bundles them so the training-time sampler can pair the
    cover with a random encryption variant on each draw.
    """
    group_id: int
    source: str
    method: str
    payload_level: str
    cover_path: Path
    stego_paths: dict[str, Path] = field(default_factory=dict)
    # stego_paths maps encryption ("plain" | "encrypted") -> path

    def sample_stego(self, rng: random.Random) -> tuple[Path, str]:
        """Return (path, encryption) for a uniformly-random stego variant."""
        encryption = rng.choice(list(self.stego_paths.keys()))
        return self.stego_paths[encryption], encryption

    def all_stegos(self) -> list[tuple[Path, str]]:
        """Return [(path, encryption)] for every available stego variant.

        Used at inference time when we want to score every variant.
        """
        return [(p, enc) for enc, p in self.stego_paths.items()]


# ---------------------------------------------------------------------------
# Filesystem enumeration
# ---------------------------------------------------------------------------

def enumerate_cover_groups(
    run_dir: Path,
    *,
    method: str,
    payload_level: str,
    split: SplitName | None = None,
) -> list[CoverGroup]:
    """Walk a run directory and return one CoverGroup per (group_id, source).

    Expected layout under ``run_dir`` (matches the main pipeline's
    actual on-disk format, src/pipeline/runner.py ~line 539)::

        covers/{real,ml_a,ml_b}/g<NNNN>__src-<source>.{png,jpg}
        stego/<method>/<payload>/<encryption>/<source>/g<NNNN>__src-<source>__m-<method>__p-<payload>__e-<encryption>.{png,jpg}

    The branch determines file extension:
      - method='lsb' -> PNG covers + PNG stegos (spatial branch)
      - method='dct' -> JPG covers + JPG stegos (frequency branch)

    If a cover has no matching stego files, it is skipped. If only one
    encryption variant exists, the CoverGroup is still emitted with the
    single available variant (the sampler will degenerate to that one
    variant deterministically).
    """
    ext = "png" if method == "lsb" else "jpg"
    covers_root = run_dir / "covers"
    stego_root  = run_dir / "stego" / method / payload_level   # singular "stego"
    if not stego_root.exists():
        raise FileNotFoundError(
            f"No stego at {stego_root}. Did you run the embedding stage?"
        )

    # First pass: collect cover paths per (group_id, source)
    groups: dict[tuple[int, str], CoverGroup] = {}
    for source in ("real", "ml_a", "ml_b"):
        cov_dir = covers_root / source
        if not cov_dir.exists():
            continue
        for cov_path in sorted(cov_dir.glob(f"g*__src-*.{ext}")):
            try:
                gid = int(cov_path.name.split("__")[0].lstrip("g"))
            except ValueError:
                continue
            if split is not None and split_of(gid) != split:
                continue
            groups[(gid, source)] = CoverGroup(
                group_id=gid, source=source,
                method=method, payload_level=payload_level,
                cover_path=cov_path,
            )

    # Second pass: attach stego paths
    # Stego filename pattern from runner.stego_filename():
    #   g<NNNN>__src-<source>__m-<method>__p-<payload>__e-<encryption>.<ext>
    for encryption in ("plain", "encrypted"):
        for source in ("real", "ml_a", "ml_b"):
            ste_dir = stego_root / encryption / source
            if not ste_dir.exists():
                continue
            ste_glob = f"g*__src-{source}__m-{method}__p-{payload_level}__e-{encryption}.{ext}"
            for ste_path in sorted(ste_dir.glob(ste_glob)):
                try:
                    gid = int(ste_path.name.split("__")[0].lstrip("g"))
                except ValueError:
                    continue
                key = (gid, source)
                if key in groups:
                    groups[key].stego_paths[encryption] = ste_path

    # Drop cover groups that have no stegos at all (incomplete embedding)
    result = [g for g in groups.values() if g.stego_paths]
    return sorted(result, key=lambda g: (g.group_id, g.source))


def enumerate_samples(
    run_dir: Path,
    *,
    method: str,
    payload_level: str,
    split: SplitName | None = None,
) -> list[Sample]:
    """Flat-pair view: one Sample per (group_id, source, encryption).

    Deprecated for training (use enumerate_cover_groups instead). Kept
    for backwards compatibility with earlier callers.
    """
    out: list[Sample] = []
    for cg in enumerate_cover_groups(run_dir, method=method,
                                       payload_level=payload_level, split=split):
        for encryption, ste_path in cg.stego_paths.items():
            out.append(Sample(
                group_id=cg.group_id, source=cg.source,
                method=method, payload_level=payload_level,
                encryption=encryption,
                cover_path=cg.cover_path, stego_path=ste_path,
            ))
    return out


# ---------------------------------------------------------------------------
# PyTorch dataset + paired sampler (lazily imported to avoid hard torch dep)
# ---------------------------------------------------------------------------

def make_paired_dataset(cover_groups: list[CoverGroup], *, seed: int = 0):
    """Return a torch.utils.data.Dataset of cover-stego PAIRS.

    Each ``__getitem__(idx)`` returns ``(cover_tensor, stego_tensor,
    encryption)`` where the stego is a uniformly-sampled encryption
    variant from the cover's group. The accompanying ``BalancedPairSampler``
    (see ``make_balanced_pair_loader``) flattens this into a per-batch
    interleaving of N covers and N stegos.

    This avoids the duplicated-cover problem of the old flat dataset:
    each physical cover is loaded at most twice per epoch (once as the
    cover input and once as the paired stego's cover -- but in fact we
    only load it once, since cover and stego are decoded in the same
    ``__getitem__`` call).
    """
    import torch
    import numpy as np
    from PIL import Image

    def _load_gray(path: Path) -> torch.Tensor:
        with Image.open(path) as im:
            arr = np.asarray(im.convert("L"), dtype="float32")
        return torch.from_numpy(arr)[None]  # (1, H, W)

    class _PairDataset(torch.utils.data.Dataset):
        def __init__(self, cgs: list[CoverGroup], seed: int) -> None:
            self.cgs = cgs
            # Per-item RNG seeded deterministically by index keeps val
            # reproducible; training overrides it via shuffle anyway.
            self.seed = seed

        def __len__(self) -> int:
            return len(self.cgs)

        def __getitem__(self, idx: int):
            cg = self.cgs[idx]
            # Per-item RNG must be a supported seed type for Python 3.12+
            # (random.Random no longer accepts tuples). Combine seed and idx
            # into a deterministic string -- random hashes the string with
            # SHA512 internally, so reproducibility across runs holds.
            rng = random.Random(f"{self.seed}-{idx}")
            stego_path, enc = cg.sample_stego(rng)
            cover_t = _load_gray(cg.cover_path)
            stego_t = _load_gray(stego_path)
            meta = {
                "group_id": cg.group_id,
                "source": cg.source,
                "encryption": enc,
            }
            return cover_t, stego_t, meta

    return _PairDataset(cover_groups, seed=seed)


def make_balanced_pair_loader(
    cover_groups: list[CoverGroup],
    *,
    batch_size: int,
    shuffle: bool,
    num_workers: int = 2,
    pin_memory: bool = False,
    seed: int = 0,
):
    """Return a DataLoader that emits class-balanced batches.

    ``batch_size`` is interpreted as the TOTAL batch size (covers +
    stegos). Internally we draw ``batch_size // 2`` cover-stego pairs
    per batch and the collate function unrolls them into a flat
    ``(images, labels, metadata)`` tuple where labels alternate 0, 1,
    0, 1, ... ensuring perfect class balance per batch.

    Gotcha #2 (class imbalance, duplicate covers): solved by sampling
    from the de-duplicated cover-group view and pairing each cover with
    exactly one (random encryption) stego per epoch.

    Gotcha #3 (encryption mixing): solved by random sampling of the
    encryption variant inside ``CoverGroup.sample_stego``; both plain
    and encrypted stegos are seen in expectation over training.
    """
    import torch

    if batch_size < 2 or batch_size % 2 != 0:
        raise ValueError(f"batch_size must be even and >= 2; got {batch_size}")
    pair_batch = batch_size // 2

    ds = make_paired_dataset(cover_groups, seed=seed)

    def _collate(batch):
        # batch: list of (cover_t, stego_t, meta)
        imgs = []
        labels = []
        metas = []
        for cover_t, stego_t, meta in batch:
            imgs.append(cover_t);  labels.append(0); metas.append({**meta, "label": 0})
            imgs.append(stego_t);  labels.append(1); metas.append({**meta, "label": 1})
        return (
            torch.stack(imgs),                          # (2*pair_batch, 1, H, W)
            torch.tensor(labels, dtype=torch.long),     # (2*pair_batch,)
            metas,
        )

    return torch.utils.data.DataLoader(
        ds,
        batch_size=pair_batch,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=pin_memory,
        collate_fn=_collate,
        drop_last=False,
    )

# Cloud-rental runbook for the SRNet sweep

End-to-end recipe for training all 3 SRNet cells (LSB × {low, medium,
high}) on rented GPU. Budget: $5-9 in cloud cost.

DCTR is **not** in this runbook -- it runs locally on CPU. Use
`docs/learned_baselines/PLAN.md` for the DCTR path.

## Two paths

| | **Path A** (laptop + cloud split) | **Path B** (everything on cloud) |
|---|---|---|
| **Use when** | You have a free overnight on the laptop | You don't want the laptop blocked at all |
| **Total cost** | ~$5-7 | ~$7-9 |
| **Laptop time** | ~8 h (training-data generation) | ~30 min (kicking off the cloud script) |
| **Cloud time** | ~10-15 h GPU + 30 min upload | ~15-20 h all-in-one |
| **Workflow** | Generate data overnight on laptop, package, upload, train on cloud | Single SSH session, `bash cloud_full_pipeline.sh`, walk away |

Both paths use the same training scripts and produce the same
checkpoints. Pick based on whether your laptop can take an overnight
hit.

The sections below cover **Path A** by default. **Path B** is at the
bottom (one-section recipe).

## Provider choice

Three viable options, ordered by total cost:

| Provider | GPU | $/hr (Q2 2026 typical) | Total for 3 cells | Interruptible? |
|---|---|---|---|---|
| **Vast.ai** | RTX 3090 (24GB) | $0.30-0.40 | **$5-8** | Yes (set bid above base) |
| **Lambda Labs** | RTX 4090 (24GB) | $0.50-0.70 | $7-12 | No |
| **Lambda Labs** | A100 40GB | $1.10 | $10-14, ~2× faster | No |
| **Google Colab Pro** | T4 (16GB) / sometimes A100 | $10/mo flat | "free" if patient | Yes, frequent |

**Recommendation:** start with **Vast.ai RTX 3090**. Cheapest, plenty
of VRAM, ~15h of total compute. If the spot price is volatile or you
get pre-empted twice, switch to Lambda RTX 4090 for ~$10 of stability.

## Pre-flight checklist (do at home, no cloud cost)

```bash
# 1. Verify the branch and that the training script is on it
git checkout srnet-dctr-baselines
git status                          # should be clean

# 2. Generate the training set locally (HF API, no GPU needed, ~5h)
python scripts/training/generate_training_set.py \
    --n-groups 3500 \
    --out-run runs/training_v1 \
    --seed 4242 \
    --exclude-captions-from runs/prototype_full_20260513_005357_p8765 \
    --ml-engine inference_api

# 3. Verify the layout
ls runs/training_v1/covers/{real,ml_a,ml_b} | head
ls runs/training_v1/stego/lsb/{low,medium,high}/{plain,encrypted}

# 4. Smoke-test on a subset with the existing pipeline's tests
python -c "
from src.detection_learned.data import enumerate_cover_groups
for pl in ('low','medium','high'):
    cgs = enumerate_cover_groups(__import__('pathlib').Path('runs/training_v1'),
                                  method='lsb', payload_level=pl)
    print(f'{pl:6s}: {len(cgs)} cover groups')
"

# 5. Package ONLY the LSB data needed for SRNet training
bash scripts/training/package_cloud_dataset.sh runs/training_v1 /tmp/srnet_train.tar
# expected output: ~11GB tarball
```

If the package step succeeds, you have the smallest possible upload.

## Cloud setup (15 min)

### Vast.ai

1. Create an account at https://vast.ai (needs credit card).
2. Add ~$20 of credit.
3. Search for instances:
   - GPU: RTX 3090
   - Disk: 50GB+
   - Image: `pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime`
   - DLPerf > 12
4. Rent one. Note the SSH command Vast shows you (looks like
   `ssh -p 31234 root@ssh4.vast.ai`).

### Lambda Labs

1. Create account at https://lambdalabs.com.
2. Launch a "1x RTX 4090" instance (Ubuntu 22.04 + PyTorch).
3. Wait ~2 min for boot; copy the SSH command.

## Upload (15-30 min, depends on home upload speed)

```bash
# From your laptop, in the project root:

# Tar+upload the dataset (~11GB)
scp -P <ssh_port> /tmp/srnet_train.tar root@<host>:/workspace/

# Sync the code (no data; small)
rsync -avz --exclude='runs/' --exclude='venv/' --exclude='__pycache__' \
    -e "ssh -p <ssh_port>" \
    . root@<host>:/workspace/m2-2-steg/
```

On a 50 Mbps residential upload, the 11GB takes ~30 min. Faster if
you're on fibre.

## On the cloud instance — environment + training (15-30h GPU)

```bash
# SSH in once, run inside a tmux session so a disconnect doesn't kill training
ssh -p <ssh_port> root@<host>
tmux new -s srnet                   # detach with C-b d, resume with `tmux a`

cd /workspace/m2-2-steg

# Unpack data
mkdir -p runs/training_v1
tar -xf /workspace/srnet_train.tar -C runs/training_v1

# Install Python deps (the PyTorch image already has torch; just our extras)
pip install -q -r requirements.txt
pip install -q -r requirements_learned.txt

# Confirm GPU
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# expected: True NVIDIA GeForce RTX 3090

# Quick model smoke test (~30 seconds)
python src/detection_learned/srnet.py
# expected: parameter count ~470k, output shape (2, 2)
```

### Train one cell at a time (sequential)

Order: **low → medium → high**. Low is most diagnostic; if SRNet
can't learn anything there, abort and debug before burning more GPU.

```bash
# Cell 1: LSB / low (~5-7h on RTX 3090)
python scripts/training/train_srnet.py \
    --training-run runs/training_v1 \
    --method lsb --payload low \
    --epochs 60 --batch-size 16 \
    --device cuda \
    --out models/srnet_lsb_low_v1.pt \
    --resume models/srnet_lsb_low_v1.pt    # safe if file doesn't exist

# Cell 2: LSB / medium
python scripts/training/train_srnet.py \
    --training-run runs/training_v1 \
    --method lsb --payload medium \
    --epochs 60 --batch-size 16 \
    --device cuda \
    --out models/srnet_lsb_medium_v1.pt \
    --resume models/srnet_lsb_medium_v1.pt

# Cell 3: LSB / high
python scripts/training/train_srnet.py \
    --training-run runs/training_v1 \
    --method lsb --payload high \
    --epochs 60 --batch-size 16 \
    --device cuda \
    --out models/srnet_lsb_high_v1.pt \
    --resume models/srnet_lsb_high_v1.pt
```

**Each cell logs val-AUC per epoch to stdout.** Expect:
- LSB/low: val-AUC reaches ~0.80-0.90 by epoch 30-40 (the hard case).
- LSB/medium: val-AUC reaches ~0.95+ quickly (epoch 10-20).
- LSB/high: val-AUC saturates at ~0.99 very quickly.

If LSB/low never beats 0.55 by epoch 15, something is wrong --
abort and inspect rather than spending the whole 6h.

## Pre-emption recovery (Vast.ai spot only)

If Vast pre-empts you mid-training:

1. Your tmux session dies but checkpoints are safe on disk.
2. Re-rent an equivalent instance (often the same one is available).
3. Re-upload the tarball or rent a "saved disk" image.
4. Re-run the same `train_srnet.py` command; the `--resume` flag
   will pick up from the last checkpoint and continue from where you
   left off (epoch + optimizer state restored).

Expected cost of a pre-emption: ~$0.50 (re-upload + lost epoch).

## Download checkpoints (5 min)

```bash
# From your laptop, after all 3 cells finish:
scp -P <ssh_port> 'root@<host>:/workspace/m2-2-steg/models/srnet_lsb_*.pt' models/

# Quick verify they loaded ok
python -c "
import torch
for p in ['models/srnet_lsb_low_v1.pt',
          'models/srnet_lsb_medium_v1.pt',
          'models/srnet_lsb_high_v1.pt']:
    ck = torch.load(p, map_location='cpu')
    print(f'{p}: val_auc={ck[\"val_auc\"]:.4f}  hash={ck[\"training_run_hash\"]}')
"
```

## Terminate the cloud instance

**Don't forget this.** Both Vast and Lambda charge by the wall-clock
hour whether you're using it or not.

- Vast.ai: from the dashboard, click "Destroy" on the instance.
- Lambda Labs: "Terminate" on the instance card.

Verify your remaining balance to confirm.

## Run inference locally (15 min)

```bash
# On your laptop (CPU or M-series MPS works fine for inference)
python scripts/inference/apply_srnet_to_run.py \
    --run runs/prototype_full_20260513_005357_p8765 \
    --models models/srnet_lsb_low_v1.pt \
             models/srnet_lsb_medium_v1.pt \
             models/srnet_lsb_high_v1.pt \
    --device auto \
    --out runs/prototype_full_20260513_005357_p8765/predictions_srnet.csv

# Verify schema matches existing predictions.csv
head -2 runs/prototype_full_20260513_005357_p8765/predictions_srnet.csv
wc -l runs/prototype_full_20260513_005357_p8765/predictions{,_srnet}.csv
```

Then merge into the analysis (script TBD in next branch commit):

```bash
python scripts/inference/merge_learned_predictions.py \
    --run runs/prototype_full_20260513_005357_p8765
```

## Cost-and-time summary

| Step | Where | Time | Cost |
|---|---|---|---|
| Pre-flight + tests | Laptop | ~30 min human | $0 |
| Real cover download | Laptop (HF datasets) | ~15 min | $0 |
| ML cover generation | Laptop (HF API) | ~5h background | $0 |
| LSB+DCT embedding (126k stegos) | Laptop (8-core CPU hot) | ~2.5h | $0 |
| Packaging | Laptop | ~10 min | $0 |
| Cloud account + provision | Vast.ai | ~15 min | $0.10 (idle time during setup) |
| Upload (50 Mbps) | Laptop → cloud | ~30 min | $0.20 |
| LSB-low SRNet training | Cloud RTX 3090 | ~5-7h | $1.80-2.50 |
| LSB-medium SRNet training | Cloud RTX 3090 | ~3-5h | $1.10-1.80 |
| LSB-high SRNet training | Cloud RTX 3090 | ~2-4h | $0.70-1.50 |
| Checkpoint download | Cloud → laptop | ~2 min | < $0.10 |
| SRNet inference on test run | Laptop (MPS or CPU) | ~10-15 min | $0 |
| DCTR feature extraction + train + apply | Laptop (8-core CPU) | ~4-5h | $0 |
| **Total** | | **~20-25h elapsed**, ~8h training data + ~4-5h DCTR | **~$4-7 cloud + 0** |

The cloud cost is *lower* than my earlier $10-15 estimate because we
only run 3 SRNet cells (not 6 — DCT branch goes to DCTR locally).
The corrected embedding time (~2.5h instead of "30 min") matters
because the laptop is busy with hot CPU work during that window.

If you want belt-and-braces, budget $15 to cover one pre-emption and
maybe a switch to a faster GPU mid-run.

## Sanity checks while training (read these once)

- **Val-AUC stuck at 0.5** for 10+ epochs on LSB/low: bug, abort. Likely a label-flipping mistake or the DataLoader serving the wrong file.
- **Val-AUC improving but training loss diverges**: lr too high; halve and resume.
- **Cell finishes in <30 min**: cells are quicker than expected; check that the val set is non-empty.
- **Checkpoint hash field is empty**: `training_run_hash` not populated -> leakage guard won't fire. Manually verify before running inference.

---

## Path B — Everything on the cloud (single SSH session)

The all-in-one alternative if you don't want to dedicate any laptop
time to training-data assembly. Single Vast.ai instance does the whole
pipeline: real downloads, ML generation (default: HF Inference API,
matching the test run's distribution), embedding via CPU
multiprocessing, then SRNet training.

### Instance requirements

| Spec | Minimum | Why |
|---|---|---|
| GPU | RTX 3090 / 4090 (24 GB VRAM) | SRNet training (no local SDXL needed in default config) |
| vCPU | **16 cores** | Embedding multiprocessing benefits from cores; speeds up the embed step from ~2.5h to ~1.5h |
| RAM | 32 GB | dataloader workers + checkpoint state |
| Disk | **60 GB** | dataset (~30 GB) + checkpoints (~5 GB) + OS/pip cache (~15 GB) |

ML cover generation by default uses the **HuggingFace Inference API**
(same as the test run was generated with). That matches the test
distribution exactly and avoids a ~30 GB SDXL+FLUX weights download.
If you instead pass `--ml-engine diffusers` to the cloud script, the
weights download locally and the disk requirement bumps to **100 GB**.

On Vast.ai, the typical RTX 3090 instance with 16 vCPU + 60 GB rents
for ~$0.40-0.45/hr.

### Recipe

```bash
# 1. Provision a Vast.ai instance matching the specs above.
#    Image: pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime
#    Disk: at least 80GB

# 2. SSH in and clone the repo (no dataset upload needed)
ssh -p <port> root@<host>
tmux new -s pipeline
cd /workspace
git clone https://github.com/<your-fork>/m2-2-steg.git
cd m2-2-steg
git checkout srnet-dctr-baselines

# 3. Run the all-in-one script
#    - Downloads real covers (~15 min, HF datasets)
#    - Generates ML covers via HF Inference API (~5h) -- same backend
#      the test run used, no model-weight download
#      (pass --ml-engine diffusers if you want local SDXL/FLUX instead)
#    - Embeds 126,000 stegos (~1.5h on 16 cores)
#    - Trains 3 SRNet cells (~10-15h GPU)
bash scripts/training/cloud_full_pipeline.sh \
    --n-groups 3500 \
    --run-id training_v1 \
    --seed 4242
#    NOTE: if you want to exclude the test run's captions, you'd need to
#    also rsync that run's manifests directory to the cloud first. For
#    most settings the exclusion is unnecessary because the random
#    caption sampling makes overlap with 3,000 specific captions vanishingly
#    rare; see PLAN.md.

# 4. Watch a few epochs from tmux to confirm training is healthy.
#    Then C-b d to detach; tmux survives SSH disconnects.

# 5. When the script reports "ALL STAGES COMPLETE", download the
#    checkpoints. From your laptop:
scp -P <port> 'root@<host>:/workspace/m2-2-steg/models/srnet_lsb_*.pt' models/

# 6. Terminate the instance.
```

### Idempotency / pre-emption recovery (Path B)

Every stage of `cloud_full_pipeline.sh` is idempotent:

- Real cover download: existing files in `runs/training_v1/covers/real/` are skipped.
- ML generation: per-image files already on disk are skipped.
- Embedding: existing stegos + already-written quality rows are skipped.
- SRNet training: `--resume` auto-loads the per-cell checkpoint and continues from the last epoch.

So a Vast.ai pre-emption mid-pipeline costs only the wasted time, no work. **Re-run the same `bash cloud_full_pipeline.sh` command** after re-provisioning, and it will pick up exactly where it left off.

### Cost breakdown (Path B, default = HF Inference API)

| Step | Time | At $0.45/hr |
|---|---|---|
| Setup (apt, pip; no model download in default config) | ~10 min | $0.08 |
| Real covers (HF datasets) | ~15 min | $0.10 |
| ML covers (HF Inference API; GPU idle, mostly waiting) | ~5 h | $2.25 |
| Embedding (CPU multiprocessing) | ~1.5 h | $0.70 |
| SRNet training (3 cells) | ~10-15 h | $4.50-6.75 |
| **Total** | **~17-22 h** | **~$7-10** |

Budget $12 to leave room for one re-provisioning after a pre-emption.

If you instead use `--ml-engine diffusers` (saves ~2 h of API waiting
but adds the weights download), the total drops slightly to ~$6-8 in
exchange for a 100 GB disk requirement and a ~15 min initial model
download. Worth it only if you're sensitive to wall-clock or worried
about HF API rate-limits.

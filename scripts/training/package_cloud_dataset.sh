#!/usr/bin/env bash
# Package the LSB-only subset of a training run for cloud upload.
#
# SRNet trains on the spatial branch only; the DCT-branch artefacts
# (~half of total disk usage) are not needed on the cloud instance.
# This script makes a tar of just the LSB stegos + all covers, which
# is what train_srnet.py reads.
#
# Usage: package_cloud_dataset.sh <training_run_dir> <output_tarball>

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <training_run_dir> <output_tarball>" >&2
    exit 2
fi

RUN_DIR="$1"
OUT_TAR="$2"

if [ ! -d "$RUN_DIR" ]; then
    echo "error: $RUN_DIR is not a directory" >&2
    exit 1
fi

# Sanity: required subdirs must exist
for sub in covers/real covers/ml_a covers/ml_b stego/lsb manifests; do
    if [ ! -d "$RUN_DIR/$sub" ]; then
        echo "error: missing $RUN_DIR/$sub -- did you run all pipeline stages?" >&2
        exit 1
    fi
done

# Estimate tarball size before bothering to build it (visible feedback)
COVERS_SZ=$(du -sh "$RUN_DIR/covers" | awk '{print $1}')
LSB_SZ=$(du -sh "$RUN_DIR/stego/lsb" | awk '{print $1}')
echo "[package] covers      : $COVERS_SZ"
echo "[package] LSB stegos  : $LSB_SZ"
echo "[package] (DCT stegos excluded; SRNet does not use them)"

# Build the tar. We tar relative to RUN_DIR's parent so the archive
# unpacks cleanly into a freshly-created runs/<name>/ on the remote.
# Note: covers/ contains BOTH PNG (spatial) and JPG (frequency) variants;
# we keep both because both formats sometimes share group_id space and
# the loader's split logic is fed by the PNG filenames; pruning JPG
# would save ~5GB but risks subtle mismatches.
PARENT=$(dirname "$RUN_DIR")
NAME=$(basename "$RUN_DIR")
echo "[package] writing $OUT_TAR ..."
tar -cf "$OUT_TAR" \
    -C "$PARENT" \
    "$NAME/covers" \
    "$NAME/stego/lsb" \
    "$NAME/manifests"

OUT_SZ=$(du -h "$OUT_TAR" | awk '{print $1}')
echo "[package] DONE -- $OUT_TAR ($OUT_SZ)"
echo
echo "To upload to a Vast.ai / Lambda Labs instance:"
echo "    scp -P <ssh_port> $OUT_TAR root@<host>:/workspace/"
echo "On the remote:"
echo "    mkdir -p runs && tar -xf /workspace/$(basename "$OUT_TAR") -C runs/"

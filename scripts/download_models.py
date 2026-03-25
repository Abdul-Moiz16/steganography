"""Pre-download HuggingFace model weights for SDXL and FLUX.1-schnell.

Run once after `pip install -r requirements.txt` to cache the weights
so that generation runs don't block on network I/O:

    python scripts/download_models.py
"""

from huggingface_hub import snapshot_download

# Only download safetensors weights (skip pytorch .bin duplicates and
# other large files we don't need).  The ignore patterns exclude the
# fp32 .bin weights, ONNX/flax variants, and training-only files.
MODELS = [
    {
        "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "allow_patterns": [
            "*.json",
            "*.txt",
            "*.safetensors",
            "tokenizer*/**",
            "scheduler/**",
        ],
        "ignore_patterns": [
            "*.bin",
            "*.onnx*",
            "*.msgpack",
            "onnx/**",
            "flax_model*",
        ],
    },
    {
        "repo_id": "black-forest-labs/FLUX.1-schnell",
        "allow_patterns": [
            "*.json",
            "*.txt",
            "*.safetensors",
            "tokenizer*/**",
            "scheduler/**",
        ],
        "ignore_patterns": [
            "*.bin",
            "*.onnx*",
            "*.msgpack",
        ],
    },
]


def main() -> None:
    for spec in MODELS:
        repo_id = spec["repo_id"]
        print(f"Downloading {repo_id} ...")
        path = snapshot_download(
            repo_id,
            allow_patterns=spec.get("allow_patterns"),
            ignore_patterns=spec.get("ignore_patterns"),
        )
        print(f"  cached at {path}")
    print("All model weights cached.")


if __name__ == "__main__":
    main()

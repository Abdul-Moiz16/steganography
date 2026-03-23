# Data Directory

This directory stores the proposal-aligned data layout.

## Structure

```text
data/
├── covers/
│   ├── spatial/{real|ml_a|ml_b}/
│   └── frequency/{real|ml_a|ml_b}/
├── payloads/{plain|encrypted}/{low|medium|high}/
├── stego/{lsb|dct}/{low|medium|high}/{plain|encrypted}/{real|ml_a|ml_b}/
└── manifests/
```

## Important Format Rules

- spatial covers and stegos are PNG
- frequency covers and stegos are JPEG
- standardized carriers are grayscale `512x512`

Git policy stays the same: only lightweight metadata files should be tracked here.

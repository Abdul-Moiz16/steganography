# Stego Images

Stego outputs are split by method because each branch now has its own codec.

## Methods

- `lsb`
  - grayscale PNG outputs
  - sequential row-major LSB replacement
- `dct`
  - JPEG outputs
  - JSteg-style DCT-LSB on non-zero quantized AC coefficients

## Payload Levels

- `low`: `25%` fill
- `medium`: `50%` fill
- `high`: `75%` fill

The auxiliary `BD-Sens` condition from the proposal is not part of the default automated output tree.

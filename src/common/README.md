# `src/common` Guide

`common/` owns the proposal-locked path and naming contracts.

## What It Defines

- allowed values for:
  - `source in {real, ml_a, ml_b}`
  - `method in {lsb, dct}`
  - `payload_level in {low, medium, high}`
  - `encryption in {plain, encrypted}`
- cover-branch mapping:
  - `lsb -> spatial`
  - `dct -> frequency`
- canonical filenames for:
  - spatial covers (`.png`)
  - frequency covers (`.jpg`)
  - payloads (`.bin`)
  - stegos (`.png` for `lsb`, `.jpg` for `dct`)

Do not rebuild path logic elsewhere in the repo.

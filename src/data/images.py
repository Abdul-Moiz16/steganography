from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return im.copy()


def load_bytes(path: Path) -> bytes:
    return path.read_bytes()


def center_crop_to_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    right = left + side
    bottom = top + side
    return image.crop((left, top, right, bottom))


def standardize_image(image: Image.Image, size: tuple[int, int] = (512, 512)) -> Image.Image:
    """Convert one raw image into the proposal-locked carrier format.

    The final proposal standardizes every carrier to grayscale before
    embedding. We therefore:
    1. convert to single-channel luminance,
    2. center-crop to a square,
    3. resize to 512x512 with Lanczos resampling.
    """
    grayscale = image.convert("L")
    square = center_crop_to_square(grayscale)
    return square.resize(size, Image.Resampling.LANCZOS)


def save_png(image: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=False)


def save_jpeg(image: Image.Image, out_path: Path, *, quality: int = 95) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="JPEG", quality=quality, subsampling=0, optimize=False)


def save_bytes(data: bytes, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)


def standardize_and_save_variants(
    input_path: Path,
    spatial_output_path: Path,
    frequency_output_path: Path,
    *,
    size: tuple[int, int] = (512, 512),
    jpeg_quality: int = 95,
) -> None:
    """Write both proposal-required carrier variants from one raw image.

    Spatial LSB uses an 8-bit grayscale PNG carrier.
    DCT-LSB uses a grayscale JPEG carrier encoded at Q=95.
    """
    image = load_image(input_path)
    standardized = standardize_image(image, size=size)
    save_png(standardized, spatial_output_path)
    save_jpeg(standardized, frequency_output_path, quality=jpeg_quality)


def list_pngs(path: Path) -> Iterable[Path]:
    return sorted(path.glob("*.png"))


def list_jpegs(path: Path) -> Iterable[Path]:
    return sorted([*path.glob("*.jpg"), *path.glob("*.jpeg")])

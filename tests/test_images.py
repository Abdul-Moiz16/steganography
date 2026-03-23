from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.data.images import (
    center_crop_to_square,
    list_jpegs,
    list_pngs,
    load_image,
    save_jpeg,
    save_png,
    standardize_and_save_variants,
    standardize_image,
)


def test_center_crop_to_square_uses_min_side() -> None:
    image = Image.new("RGB", (13, 9), color=(255, 0, 0))
    cropped = center_crop_to_square(image)
    assert cropped.size == (9, 9)


def test_standardize_image_converts_to_grayscale_and_target_size() -> None:
    image = Image.new("RGB", (100, 40), color=(10, 20, 30))
    standardized = standardize_image(image, size=(64, 64))
    assert standardized.mode == "L"
    assert standardized.size == (64, 64)


def test_standardize_and_save_variants_writes_png_and_jpeg(tmp_path: Path) -> None:
    input_path = tmp_path / "raw.jpg"
    spatial_path = tmp_path / "out" / "final.png"
    frequency_path = tmp_path / "out" / "final.jpg"

    Image.new("RGB", (32, 48), color=(10, 20, 30)).save(input_path)
    standardize_and_save_variants(
        input_path=input_path,
        spatial_output_path=spatial_path,
        frequency_output_path=frequency_path,
        size=(16, 16),
    )

    assert spatial_path.exists()
    assert frequency_path.exists()
    assert load_image(spatial_path).size == (16, 16)
    assert load_image(frequency_path).size == (16, 16)


def test_save_png_save_jpeg_and_listing(tmp_path: Path) -> None:
    out_dir = tmp_path / "images"
    a = out_dir / "a.png"
    b = out_dir / "b.png"
    c = out_dir / "c.jpg"

    save_png(Image.new("L", (4, 4), color=1), a)
    save_png(Image.new("L", (4, 4), color=2), b)
    save_jpeg(Image.new("L", (4, 4), color=3), c)

    assert list(list_pngs(out_dir)) == [a, b]
    assert list(list_jpegs(out_dir)) == [c]

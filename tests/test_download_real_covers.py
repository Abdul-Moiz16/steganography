from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from src.data.download_real_covers import (
    DownloadRecord,
    DatasetSpec,
    _build_rows,
    collect_candidates,
    download_real_covers,
    extract_coco_candidate,
    extract_flickr_candidate,
    is_detailed_caption,
    iter_hf_rows,
)
from src.data.images import load_image
from src.data.manifests import read_rows_csv


def _image_bytes(fmt: str = "JPEG") -> bytes:
    buff = io.BytesIO()
    Image.new("RGB", (32, 24), color=(123, 50, 200)).save(buff, format=fmt)
    return buff.getvalue()


def test_is_detailed_caption_threshold() -> None:
    assert is_detailed_caption("A person walking through a busy market street", min_words=8)
    assert not is_detailed_caption("A person walking", min_words=8)


def test_extract_coco_candidate_parses_fields() -> None:
    row = {
        "URL": "http://images.cocodataset.org/train2017/000000391895.jpg",
        "TEXT": "A man with a red helmet on a small moped on a dirt road.",
    }
    cand = extract_coco_candidate(row, min_words=8)

    assert cand is not None
    assert cand.dataset == "COCO"
    assert cand.orig_id == "000000391895"
    assert cand.caption_id == "coco-000000391895"


def test_extract_flickr_candidate_selects_most_detailed_caption() -> None:
    row = {
        "image": {"src": "https://datasets-server/path/image.jpg"},
        "caption": [
            "Two kids play.",
            "Two children wearing bright clothes are playing soccer near a metal fence.",
        ],
        "img_id": "12",
        "filename": "123456.jpg",
    }

    cand = extract_flickr_candidate(row, min_words=8)
    assert cand is not None
    assert cand.dataset == "Flickr30k"
    assert cand.orig_id == "123456"
    assert cand.caption_id == "flickr-12"
    assert "bright clothes" in cand.caption_text


def test_iter_hf_rows_paginates_until_exhausted() -> None:
    pages = {
        0: [{"id": 1}, {"id": 2}],
        2: [{"id": 3}],
        3: [],
    }

    def fake_fetch(**kwargs):
        return pages.get(kwargs["offset"], [])

    rows = list(
        iter_hf_rows(
            hf_dataset="x",
            config="y",
            split="z",
            page_size=2,
            max_rows=10,
            fetch_rows_fn=fake_fetch,
        )
    )
    assert [r["id"] for r in rows] == [1, 2, 3]


def test_collect_candidates_deduplicates_and_limits() -> None:
    spec = DatasetSpec(
        dataset="COCO",
        hf_dataset="coco",
        config="default",
        split="train",
        target_count=2,
    )

    rows = [
        {
            "URL": "http://images.cocodataset.org/train2017/000000000001.jpg",
            "TEXT": "A detailed caption with enough words to pass threshold now.",
        },
        {
            "URL": "http://images.cocodataset.org/train2017/000000000001.jpg",
            "TEXT": "A different caption but same image id should be ignored.",
        },
        {
            "URL": "http://images.cocodataset.org/train2017/000000000002.jpg",
            "TEXT": "Another detailed caption with enough words for filtering pass.",
        },
    ]

    def fake_fetch(**kwargs):
        offset = kwargs["offset"]
        length = kwargs["length"]
        return rows[offset : offset + length]

    selected = collect_candidates(
        spec=spec,
        extractor=extract_coco_candidate,
        seed=42,
        min_caption_words=8,
        max_scan_rows=10,
        page_size=2,
        fetch_rows_fn=fake_fetch,
    )

    assert len(selected) == 2
    assert len({c.orig_id for c in selected}) == 2


def test_collect_candidates_raises_on_insufficient_rows() -> None:
    spec = DatasetSpec(
        dataset="Flickr30k",
        hf_dataset="flickr",
        config="TEST",
        split="test",
        target_count=2,
    )

    def fake_fetch(**kwargs):
        return [
            {
                "image": {"src": "https://datasets-server/path/image.jpg"},
                "caption": ["Too short"],
                "img_id": "1",
                "filename": "x.jpg",
            }
        ] if kwargs["offset"] == 0 else []

    with pytest.raises(ValueError, match="Insufficient candidates"):
        collect_candidates(
            spec=spec,
            extractor=extract_flickr_candidate,
            seed=1,
            min_caption_words=8,
            max_scan_rows=10,
            page_size=100,
            fetch_rows_fn=fake_fetch,
        )


def test_build_rows_outputs_expected_schemas() -> None:
    records = [
        DownloadRecord(
            group_id=1,
            source="real",
            dataset="COCO",
            orig_id="0001",
            caption_id="coco-0001",
            caption_text="A detailed caption with enough words for this test case.",
            raw_image_path="/tmp/raw.jpg",
            spatial_path="/tmp/cover.png",
            frequency_path="/tmp/cover.jpg",
            qc_pass=True,
            qc_score=1.0,
            seed=42,
        )
    ]

    raw_rows, cover_rows, prompt_rows = _build_rows(records)
    assert set(raw_rows[0].keys()) == {
        "group_id",
        "source",
        "dataset",
        "orig_id",
        "caption_id",
        "caption_text",
        "raw_image_path",
        "qc_pass",
        "qc_score",
        "seed",
    }
    assert set(cover_rows[0].keys()) == {
        "group_id",
        "source",
        "dataset",
        "orig_id",
        "caption_id",
        "caption_text",
        "spatial_path",
        "frequency_path",
        "qc_pass",
        "qc_score",
        "seed",
    }
    assert set(prompt_rows[0].keys()) == {
        "group_id",
        "dataset",
        "orig_id",
        "caption_id",
        "caption_text",
        "real_spatial_path",
        "real_frequency_path",
    }


def test_download_real_covers_end_to_end_with_mocks(tmp_path: Path) -> None:
    coco_rows = [
        {
            "URL": f"http://images.cocodataset.org/train2017/{i:012d}.jpg",
            "TEXT": f"A detailed COCO caption for image number {i} with enough words.",
        }
        for i in range(1, 5)
    ]
    flickr_rows = [
        {
            "image": {"src": f"https://datasets-server/flickr/{i}.jpg"},
            "caption": [
                "Short one",
                f"A detailed Flickr30k caption example for image {i} with sufficient words.",
            ],
            "img_id": str(i),
            "filename": f"{1000+i}.jpg",
        }
        for i in range(1, 4)
    ]

    def fake_fetch_rows(**kwargs):
        source = coco_rows if kwargs["hf_dataset"] == "ChristophSchuhmann/MS_COCO_2017_URL_TEXT" else flickr_rows
        offset = kwargs["offset"]
        length = kwargs["length"]
        return source[offset : offset + length]

    bytes_by_ext = {".jpg": _image_bytes("JPEG"), ".png": _image_bytes("PNG")}

    def fake_fetch_bytes(url: str) -> bytes:
        return bytes_by_ext[".jpg"] if url.endswith(".jpg") else bytes_by_ext[".png"]

    outputs = download_real_covers(
        project_root=tmp_path,
        seed=7,
        coco_target=2,
        flickr_target=1,
        min_caption_words=8,
        max_scan_rows=50,
        page_size=2,
        fetch_rows_fn=fake_fetch_rows,
        fetch_bytes_fn=fake_fetch_bytes,
    )

    raw_index = read_rows_csv(outputs["raw_index"])
    covers = read_rows_csv(outputs["covers_master_real"])
    prompts = read_rows_csv(outputs["generation_prompts"])

    assert len(raw_index) == 3
    assert len(covers) == 3
    assert len(prompts) == 3

    datasets = {row["dataset"] for row in covers}
    assert datasets == {"COCO", "Flickr30k"}

    spatial_names = [Path(row["spatial_path"]).name for row in covers]
    frequency_names = [Path(row["frequency_path"]).name for row in covers]
    assert spatial_names == ["g0001__src-real.png", "g0002__src-real.png", "g0003__src-real.png"]
    assert frequency_names == ["g0001__src-real.jpg", "g0002__src-real.jpg", "g0003__src-real.jpg"]

    for row in covers:
        spatial_path = tmp_path / row["spatial_path"]
        frequency_path = tmp_path / row["frequency_path"]
        assert spatial_path.exists()
        assert frequency_path.exists()
        assert load_image(spatial_path).size == (512, 512)
        assert load_image(frequency_path).size == (512, 512)
        assert not Path(row["spatial_path"]).is_absolute()
        assert not Path(row["frequency_path"]).is_absolute()

    for row in raw_index:
        assert not Path(row["raw_image_path"]).is_absolute()

    for row in prompts:
        assert not Path(row["real_spatial_path"]).is_absolute()
        assert not Path(row["real_frequency_path"]).is_absolute()

    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    assert summary["total_groups"] == 3
    assert summary["dataset_counts"]["COCO"] == 2
    assert summary["dataset_counts"]["Flickr30k"] == 1
    assert not Path(summary["raw_index_path"]).is_absolute()
    assert not Path(summary["covers_master_real_path"]).is_absolute()
    assert not Path(summary["generation_prompts_path"]).is_absolute()

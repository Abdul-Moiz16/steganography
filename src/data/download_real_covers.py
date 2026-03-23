from __future__ import annotations

import argparse
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from src.common.contracts import PipelinePaths
from src.data.images import standardize_and_save_variants
from src.data.manifests import write_rows_csv


HF_DATASET_SERVER = "https://datasets-server.huggingface.co/rows"


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    hf_dataset: str
    config: str
    split: str
    target_count: int


@dataclass(frozen=True)
class Candidate:
    dataset: str
    orig_id: str
    caption_id: str
    caption_text: str
    image_url: str


@dataclass(frozen=True)
class DownloadRecord:
    group_id: int
    source: str
    dataset: str
    orig_id: str
    caption_id: str
    caption_text: str
    raw_image_path: str
    spatial_path: str
    frequency_path: str
    qc_pass: bool
    qc_score: float
    seed: int


def _request_json(
    url: str,
    *,
    timeout: int = 30,
    retries: int = 10,
    backoff_seconds: float = 1.0,
) -> dict:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "project-proposal-pipeline/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except HTTPError as exc:
            # Handle transient rate limits/server errors with backoff.
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after and retry_after.isdigit():
                    sleep_seconds = max(float(retry_after), backoff_seconds)
                else:
                    sleep_seconds = backoff_seconds * (2**attempt) + random.uniform(0.0, 0.5)
                time.sleep(sleep_seconds)
                continue
            raise
        except URLError:
            if attempt < retries - 1:
                time.sleep(backoff_seconds * (2**attempt) + random.uniform(0.0, 0.5))
                continue
            raise
    raise RuntimeError(f"Failed to fetch JSON from {url}")


def _request_bytes(
    url: str,
    *,
    timeout: int = 60,
    retries: int = 8,
    backoff_seconds: float = 1.0,
) -> bytes:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "project-proposal-pipeline/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after and retry_after.isdigit():
                    sleep_seconds = max(float(retry_after), backoff_seconds)
                else:
                    sleep_seconds = backoff_seconds * (2**attempt) + random.uniform(0.0, 0.5)
                time.sleep(sleep_seconds)
                continue
            raise
        except URLError:
            if attempt < retries - 1:
                time.sleep(backoff_seconds * (2**attempt) + random.uniform(0.0, 0.5))
                continue
            raise
    raise RuntimeError(f"Failed to download bytes from {url}")


def fetch_hf_rows(
    *,
    hf_dataset: str,
    config: str,
    split: str,
    offset: int,
    length: int,
    fetch_json: Callable[[str], dict] | None = None,
) -> list[dict]:
    fetch = fetch_json or _request_json
    query = urlencode(
        {
            "dataset": hf_dataset,
            "config": config,
            "split": split,
            "offset": offset,
            "length": length,
        }
    )
    payload = fetch(f"{HF_DATASET_SERVER}?{query}")
    rows = payload.get("rows", [])
    return [row["row"] for row in rows]


def iter_hf_rows(
    *,
    hf_dataset: str,
    config: str,
    split: str,
    page_size: int = 100,
    max_rows: int = 10000,
    page_pause_seconds: float = 0.2,
    fetch_rows_fn: Callable[..., list[dict]] | None = None,
) -> Iterable[dict]:
    fetch = fetch_rows_fn or fetch_hf_rows
    offset = 0
    yielded = 0
    while yielded < max_rows:
        page = fetch(
            hf_dataset=hf_dataset,
            config=config,
            split=split,
            offset=offset,
            length=min(page_size, max_rows - yielded),
        )
        if not page:
            break
        for row in page:
            yield row
            yielded += 1
            if yielded >= max_rows:
                break
        offset += len(page)
        if page_pause_seconds > 0:
            time.sleep(page_pause_seconds)


def _clean_caption(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_detailed_caption(text: str, min_words: int = 8) -> bool:
    caption = _clean_caption(text)
    return len(caption.split()) >= min_words


def extract_coco_candidate(row: dict, min_words: int = 8) -> Candidate | None:
    url = str(row.get("URL", "")).strip()
    caption = _clean_caption(str(row.get("TEXT", "")))
    if not url or not caption or not is_detailed_caption(caption, min_words=min_words):
        return None

    filename = Path(urlparse(url).path).name
    stem = Path(filename).stem or filename
    return Candidate(
        dataset="COCO",
        orig_id=stem,
        caption_id=f"coco-{stem}",
        caption_text=caption,
        image_url=url,
    )


def extract_flickr_candidate(row: dict, min_words: int = 8) -> Candidate | None:
    image = row.get("image") or {}
    url = str(image.get("src", "")).strip()
    captions = row.get("caption") or []
    filename = str(row.get("filename", "")).strip()
    img_id = str(row.get("img_id", "")).strip() or filename

    if not url or not filename or not captions:
        return None

    cleaned = [_clean_caption(str(c)) for c in captions if _clean_caption(str(c))]
    if not cleaned:
        return None

    # Keep the most detailed human caption for this image.
    cleaned.sort(key=lambda c: len(c.split()), reverse=True)
    caption = cleaned[0]
    if not is_detailed_caption(caption, min_words=min_words):
        return None

    stem = Path(filename).stem
    return Candidate(
        dataset="Flickr30k",
        orig_id=stem,
        caption_id=f"flickr-{img_id}",
        caption_text=caption,
        image_url=url,
    )


def collect_candidates(
    *,
    spec: DatasetSpec,
    extractor: Callable[[dict, int], Candidate | None],
    seed: int,
    min_caption_words: int,
    max_scan_rows: int,
    page_size: int = 100,
    pool_multiplier: int = 4,
    page_pause_seconds: float = 0.2,
    fetch_rows_fn: Callable[..., list[dict]] | None = None,
) -> list[Candidate]:
    seen_orig_ids: set[str] = set()
    selected: list[Candidate] = []
    pool_target = max(spec.target_count * pool_multiplier, spec.target_count)

    for row in iter_hf_rows(
        hf_dataset=spec.hf_dataset,
        config=spec.config,
        split=spec.split,
        page_size=page_size,
        max_rows=max_scan_rows,
        page_pause_seconds=page_pause_seconds,
        fetch_rows_fn=fetch_rows_fn,
    ):
        candidate = extractor(row, min_caption_words)
        if candidate is None:
            continue
        if candidate.orig_id in seen_orig_ids:
            continue
        seen_orig_ids.add(candidate.orig_id)
        selected.append(candidate)
        if len(selected) >= pool_target:
            break

    if len(selected) < spec.target_count:
        raise ValueError(
            f"Insufficient candidates for {spec.dataset}: "
            f"required {spec.target_count}, got {len(selected)}"
        )

    rng = random.Random(seed)
    rng.shuffle(selected)
    return selected[: spec.target_count]


def _url_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return suffix
    return ".jpg"


def _raw_image_path(paths: PipelinePaths, group_id: int, dataset: str, image_url: str) -> Path:
    dataset_slug = dataset.lower().replace(" ", "")
    ext = _url_extension(image_url)
    return paths.data_root / "raw" / "real" / dataset_slug / f"g{group_id:04d}__src-real{ext}"


def _to_project_relative(project_root: Path, path: Path | str) -> str:
    p = Path(path)
    resolved = p if p.is_absolute() else (project_root / p)
    try:
        return str(resolved.relative_to(project_root))
    except ValueError:
        return str(resolved)


def _build_rows(records: list[DownloadRecord]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    raw_index_rows = [
        {
            "group_id": r.group_id,
            "source": r.source,
            "dataset": r.dataset,
            "orig_id": r.orig_id,
            "caption_id": r.caption_id,
            "caption_text": r.caption_text,
            "raw_image_path": r.raw_image_path,
            "qc_pass": str(r.qc_pass).lower(),
            "qc_score": r.qc_score,
            "seed": r.seed,
        }
        for r in records
    ]

    covers_rows = [
        {
            "group_id": r.group_id,
            "source": r.source,
            "dataset": r.dataset,
            "orig_id": r.orig_id,
            "caption_id": r.caption_id,
            "caption_text": r.caption_text,
            "spatial_path": r.spatial_path,
            "frequency_path": r.frequency_path,
            "qc_pass": str(r.qc_pass).lower(),
            "qc_score": r.qc_score,
            "seed": r.seed,
        }
        for r in records
    ]

    prompt_rows = [
        {
            "group_id": r.group_id,
            "dataset": r.dataset,
            "orig_id": r.orig_id,
            "caption_id": r.caption_id,
            "caption_text": r.caption_text,
            "real_spatial_path": r.spatial_path,
            "real_frequency_path": r.frequency_path,
        }
        for r in records
    ]
    return raw_index_rows, covers_rows, prompt_rows


def download_real_covers(
    *,
    project_root: Path,
    seed: int = 42,
    coco_target: int = 300,
    flickr_target: int = 200,
    min_caption_words: int = 8,
    max_scan_rows: int = 20000,
    page_size: int = 100,
    pool_multiplier: int = 4,
    page_pause_seconds: float = 0.2,
    image_size: tuple[int, int] = (512, 512),
    fetch_rows_fn: Callable[..., list[dict]] | None = None,
    fetch_bytes_fn: Callable[[str], bytes] | None = None,
) -> dict[str, Path]:
    project_root = project_root.resolve()
    paths = PipelinePaths.from_project_root(project_root)
    paths.ensure_layout()
    fetch_bytes = fetch_bytes_fn or _request_bytes

    specs = [
        DatasetSpec(
            dataset="COCO",
            hf_dataset="ChristophSchuhmann/MS_COCO_2017_URL_TEXT",
            config="default",
            split="train",
            target_count=coco_target,
        ),
        DatasetSpec(
            dataset="Flickr30k",
            hf_dataset="nlphuji/flickr30k",
            config="TEST",
            split="test",
            target_count=flickr_target,
        ),
    ]

    collected: list[Candidate] = []
    for spec in specs:
        extractor = extract_coco_candidate if spec.dataset == "COCO" else extract_flickr_candidate
        collected.extend(
            collect_candidates(
                spec=spec,
                extractor=extractor,
                seed=seed,
                min_caption_words=min_caption_words,
                max_scan_rows=max_scan_rows,
                page_size=page_size,
                pool_multiplier=pool_multiplier,
                page_pause_seconds=page_pause_seconds,
                fetch_rows_fn=fetch_rows_fn,
            )
        )

    rng = random.Random(seed)
    rng.shuffle(collected)

    records: list[DownloadRecord] = []
    for idx, candidate in enumerate(collected, start=1):
        group_id = idx
        raw_path = _raw_image_path(paths, group_id, candidate.dataset, candidate.image_url)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(fetch_bytes(candidate.image_url))

        spatial_path = paths.cover_path(group_id, "real", "spatial")
        frequency_path = paths.cover_path(group_id, "real", "frequency")
        standardize_and_save_variants(
            raw_path,
            spatial_path,
            frequency_path,
            size=image_size,
            jpeg_quality=95,
        )

        records.append(
            DownloadRecord(
                group_id=group_id,
                source="real",
                dataset=candidate.dataset,
                orig_id=candidate.orig_id,
                caption_id=candidate.caption_id,
                caption_text=candidate.caption_text,
                raw_image_path=_to_project_relative(project_root, raw_path),
                spatial_path=_to_project_relative(project_root, spatial_path),
                frequency_path=_to_project_relative(project_root, frequency_path),
                qc_pass=True,
                qc_score=1.0,
                seed=seed,
            )
        )

    raw_rows, cover_rows, prompt_rows = _build_rows(records)

    raw_index_path = paths.manifests_dir / "raw_cover_index_real.csv"
    covers_real_path = paths.manifests_dir / "covers_master_real.csv"
    prompts_path = paths.manifests_dir / "generation_prompts.csv"
    summary_path = paths.manifests_dir / "real_download_summary.json"

    write_rows_csv(
        raw_index_path,
        raw_rows,
        fieldnames=[
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
        ],
    )

    write_rows_csv(
        covers_real_path,
        cover_rows,
        fieldnames=[
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
        ],
    )

    write_rows_csv(
        prompts_path,
        prompt_rows,
        fieldnames=[
            "group_id",
            "dataset",
            "orig_id",
            "caption_id",
            "caption_text",
            "real_spatial_path",
            "real_frequency_path",
        ],
    )

    summary = {
        "seed": seed,
        "total_groups": len(records),
        "dataset_counts": {
            "COCO": sum(1 for r in records if r.dataset == "COCO"),
            "Flickr30k": sum(1 for r in records if r.dataset == "Flickr30k"),
        },
        "raw_index_path": _to_project_relative(project_root, raw_index_path),
        "covers_master_real_path": _to_project_relative(project_root, covers_real_path),
        "generation_prompts_path": _to_project_relative(project_root, prompts_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "raw_index": raw_index_path,
        "covers_master_real": covers_real_path,
        "generation_prompts": prompts_path,
        "summary": summary_path,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download real-image covers from COCO/Flickr30k and build manifests."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--coco-target", type=int, default=300)
    parser.add_argument("--flickr-target", type=int, default=200)
    parser.add_argument("--min-caption-words", type=int, default=8)
    parser.add_argument("--max-scan-rows", type=int, default=20000)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--pool-multiplier", type=int, default=4)
    parser.add_argument("--page-pause-seconds", type=float, default=0.2)
    return parser


def main() -> None:
    args = _parser().parse_args()
    outputs = download_real_covers(
        project_root=args.project_root,
        seed=args.seed,
        coco_target=args.coco_target,
        flickr_target=args.flickr_target,
        min_caption_words=args.min_caption_words,
        max_scan_rows=args.max_scan_rows,
        page_size=args.page_size,
        pool_multiplier=args.pool_multiplier,
        page_pause_seconds=args.page_pause_seconds,
    )
    print(f"Raw index: {outputs['raw_index']}")
    print(f"Real covers manifest: {outputs['covers_master_real']}")
    print(f"Generation prompts: {outputs['generation_prompts']}")
    print(f"Summary: {outputs['summary']}")


if __name__ == "__main__":
    main()

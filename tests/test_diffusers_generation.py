"""Standalone tests for SDXL (ml_a) and FLUX.1-schnell (ml_b) image generation.

These tests directly instantiate the diffusers generators and call .generate()
with a variety of prompts. They do NOT touch any pipeline manifests or metadata.

Run a quick smoke test (1 prompt, few steps):
    pytest tests/test_diffusers_generation.py -k "smoke" -s

Run full prompt battery:
    pytest tests/test_diffusers_generation.py -k "not smoke" -s --timeout=0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image

TEST_OUTPUT_DIR = Path(__file__).parent / "output"


from src.data.generate_ml_covers import (
    FLUX_DEFAULT_MODEL_ID,
    SDXL_DEFAULT_MODEL_ID,
    DiffusersTextToImageGenerator,
    InferenceAPITextToImageGenerator,
)

# ---------------------------------------------------------------------------
# Prompts covering diverse scenes, complexities, and edge cases
# ---------------------------------------------------------------------------
PROMPTS = [
    # People & activities
    "A man sits in a chair while holding a large stuffed animal of a lion.",
    "Two chefs in a restaurant kitchen preparing food.",
    "Five ballet dancers caught mid jump in a dancing studio with sunlight coming through a window.",
    "A young woman with dark hair and wearing glasses is putting white powder on a cake using a sifter.",
    # Objects & still life
    "A wooden ball on top of a wooden stick.",
    "A professional kitchen filled with sinks and appliances.",
    "A bathroom with an enclosed shower next to a sink and a toilet.",
    # Outdoor & urban
    "People riding bicycles down the road approaching a bird.",
    "A red bus driving through downtown traffic.",
    "Two bikers, one in front of a building, the other in the city.",
    # Abstract / challenging
    "A large boat filled with men on wheels.",
    "A view of a very large bathroom with mirrored walls.",
]

SMOKE_PROMPT = "A cat sitting on a windowsill looking outside."

# Match pipeline defaults (generate_ml_covers_from_prompts)
DEFAULT_STEPS = 30
DEFAULT_GUIDANCE = 7.0
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_SEED = 42


# ---------------------------------------------------------------------------
# Timing tracker — collects per-image timings, prints summary at session end
# ---------------------------------------------------------------------------
@dataclass
class TimingRecord:
    model: str
    prompt: str
    seed: int
    steps: int
    width: int
    height: int
    elapsed_s: float


@dataclass
class TimingReport:
    records: list[TimingRecord] = field(default_factory=list)

    def add(self, record: TimingRecord) -> None:
        self.records.append(record)

    def summary(self) -> str:
        if not self.records:
            return "No generation timings recorded."
        lines = [
            "",
            "=" * 90,
            "IMAGE GENERATION TIMING REPORT",
            "=" * 90,
            f"{'Model':<12} {'Steps':>5} {'Size':>9} {'Time (s)':>9}  Prompt",
            "-" * 90,
        ]
        by_model: dict[str, list[float]] = {}
        for r in self.records:
            lines.append(
                f"{r.model:<12} {r.steps:>5} {r.width}x{r.height:>4} {r.elapsed_s:>9.2f}  "
                f"{r.prompt[:50]}{'...' if len(r.prompt) > 50 else ''}"
            )
            by_model.setdefault(r.model, []).append(r.elapsed_s)

        lines.append("-" * 90)
        for model, times in sorted(by_model.items()):
            avg = sum(times) / len(times)
            lines.append(
                f"{model:<12} — {len(times)} images, "
                f"total {sum(times):.1f}s, avg {avg:.2f}s/image"
            )
        lines.append("=" * 90)
        return "\n".join(lines)


# Session-scoped timing report shared across all tests
_timing_report = TimingReport()


@pytest.fixture(scope="session", autouse=True)
def print_timing_report():
    """Print the generation timing summary after all tests complete."""
    yield
    print(_timing_report.summary())


# ---------------------------------------------------------------------------
# Fixtures — each model loaded once per session
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def sdxl_generator():
    """Load SDXL once for the entire test session."""
    print(f"\n[fixture] Loading SDXL from {SDXL_DEFAULT_MODEL_ID} ...")
    t0 = time.time()
    gen = DiffusersTextToImageGenerator(SDXL_DEFAULT_MODEL_ID, flavor="sdxl")
    elapsed = time.time() - t0
    print(f"[fixture] SDXL loaded in {elapsed:.1f}s  (device={gen.device})")
    return gen


@pytest.fixture(scope="session")
def flux_generator():
    """Load FLUX.1-schnell once for the entire test session."""
    print(f"\n[fixture] Loading FLUX from {FLUX_DEFAULT_MODEL_ID} ...")
    t0 = time.time()
    gen = DiffusersTextToImageGenerator(FLUX_DEFAULT_MODEL_ID, flavor="flux")
    elapsed = time.time() - t0
    print(f"[fixture] FLUX loaded in {elapsed:.1f}s  (device={gen.device})")
    return gen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _generate_and_check(
    generator: DiffusersTextToImageGenerator,
    prompt: str,
    *,
    model_tag: str,
    seed: int = DEFAULT_SEED,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    num_inference_steps: int = DEFAULT_STEPS,
    guidance_scale: float = DEFAULT_GUIDANCE,
) -> Image.Image:
    """Call generate, record timing, assert basic output properties."""
    t0 = time.time()
    img = generator.generate(
        prompt=prompt,
        seed=seed,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        negative_prompt="",
    )
    elapsed = time.time() - t0

    _timing_report.add(TimingRecord(
        model=model_tag,
        prompt=prompt,
        seed=seed,
        steps=num_inference_steps,
        width=width,
        height=height,
        elapsed_s=elapsed,
    ))

    assert isinstance(img, Image.Image)
    assert img.size == (width, height)
    assert img.mode == "RGB"
    return img


def _save_output(img: Image.Image, out_dir: Path, name: str) -> Path:
    """Save image to output dir for visual inspection."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    img.save(path, "PNG")
    return path


# ---------------------------------------------------------------------------
# Smoke tests — single prompt, minimal steps
# ---------------------------------------------------------------------------
class TestSDXLSmoke:
    @pytest.mark.smoke
    def test_sdxl_single_generation(self, sdxl_generator):
        img = _generate_and_check(
            sdxl_generator,
            SMOKE_PROMPT,
            model_tag="sdxl",
            num_inference_steps=DEFAULT_STEPS,
        )
        path = _save_output(img, TEST_OUTPUT_DIR /"sdxl_smoke", "smoke")
        print(f"  saved: {path}")


class TestFluxSmoke:
    @pytest.mark.smoke
    def test_flux_single_generation(self, flux_generator):
        img = _generate_and_check(
            flux_generator,
            SMOKE_PROMPT,
            model_tag="flux",
            num_inference_steps=DEFAULT_STEPS,
        )
        path = _save_output(img, TEST_OUTPUT_DIR /"flux_smoke", "smoke")
        print(f"  saved: {path}")


# ---------------------------------------------------------------------------
# Full prompt battery — SDXL
# ---------------------------------------------------------------------------
class TestSDXLPrompts:
    @pytest.mark.parametrize(
        "prompt", PROMPTS, ids=[f"p{i}" for i in range(len(PROMPTS))]
    )
    def test_sdxl_prompt(self, sdxl_generator, prompt):
        img = _generate_and_check(sdxl_generator, prompt, model_tag="sdxl")
        idx = PROMPTS.index(prompt)
        _save_output(img, TEST_OUTPUT_DIR /"sdxl_prompts", f"prompt_{idx:02d}")

    def test_sdxl_deterministic(self, sdxl_generator):
        """Same seed + prompt should produce identical images."""
        img1 = _generate_and_check(
            sdxl_generator, SMOKE_PROMPT, model_tag="sdxl", seed=99
        )
        img2 = _generate_and_check(
            sdxl_generator, SMOKE_PROMPT, model_tag="sdxl", seed=99
        )
        assert list(img1.getdata()) == list(img2.getdata())

    def test_sdxl_different_seeds(self, sdxl_generator):
        """Different seeds should produce different images."""
        img1 = _generate_and_check(
            sdxl_generator, SMOKE_PROMPT, model_tag="sdxl", seed=1
        )
        img2 = _generate_and_check(
            sdxl_generator, SMOKE_PROMPT, model_tag="sdxl", seed=2
        )
        assert list(img1.getdata()) != list(img2.getdata())


# ---------------------------------------------------------------------------
# Full prompt battery — FLUX
# ---------------------------------------------------------------------------
class TestFluxPrompts:
    @pytest.mark.parametrize(
        "prompt", PROMPTS, ids=[f"p{i}" for i in range(len(PROMPTS))]
    )
    def test_flux_prompt(self, flux_generator, prompt):
        img = _generate_and_check(flux_generator, prompt, model_tag="flux")
        idx = PROMPTS.index(prompt)
        _save_output(img, TEST_OUTPUT_DIR /"flux_prompts", f"prompt_{idx:02d}")

    def test_flux_deterministic(self, flux_generator):
        """Same seed + prompt should produce identical images."""
        img1 = _generate_and_check(
            flux_generator, SMOKE_PROMPT, model_tag="flux", seed=99
        )
        img2 = _generate_and_check(
            flux_generator, SMOKE_PROMPT, model_tag="flux", seed=99
        )
        assert list(img1.getdata()) == list(img2.getdata())

    def test_flux_different_seeds(self, flux_generator):
        """Different seeds should produce different images."""
        img1 = _generate_and_check(
            flux_generator, SMOKE_PROMPT, model_tag="flux", seed=1
        )
        img2 = _generate_and_check(
            flux_generator, SMOKE_PROMPT, model_tag="flux", seed=2
        )
        assert list(img1.getdata()) != list(img2.getdata())


# ---------------------------------------------------------------------------
# Inference API tests — remote generation, no local model weights needed
# ---------------------------------------------------------------------------
def _generate_and_check_api(
    generator: InferenceAPITextToImageGenerator,
    prompt: str,
    *,
    model_tag: str,
    seed: int = DEFAULT_SEED,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    num_inference_steps: int = DEFAULT_STEPS,
    guidance_scale: float = DEFAULT_GUIDANCE,
) -> Image.Image:
    """Call generate on inference API generator, record timing, assert output."""
    t0 = time.time()
    img = generator.generate(
        prompt=prompt,
        seed=seed,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        negative_prompt="",
    )
    elapsed = time.time() - t0

    _timing_report.add(TimingRecord(
        model=f"{model_tag}_api",
        prompt=prompt,
        seed=seed,
        steps=num_inference_steps,
        width=width,
        height=height,
        elapsed_s=elapsed,
    ))

    assert isinstance(img, Image.Image)
    assert img.mode == "RGB"
    return img


@pytest.fixture(scope="session")
def sdxl_api_generator():
    """Create SDXL Inference API client."""
    return InferenceAPITextToImageGenerator(SDXL_DEFAULT_MODEL_ID)


@pytest.fixture(scope="session")
def flux_api_generator():
    """Create FLUX.1-schnell Inference API client."""
    return InferenceAPITextToImageGenerator(FLUX_DEFAULT_MODEL_ID)


class TestSDXLAPISmoke:
    @pytest.mark.smoke
    def test_sdxl_api_single(self, sdxl_api_generator):
        img = _generate_and_check_api(
            sdxl_api_generator,
            SMOKE_PROMPT,
            model_tag="sdxl",
            num_inference_steps=DEFAULT_STEPS,
        )
        path = _save_output(img, TEST_OUTPUT_DIR /"sdxl_api_smoke", "smoke")
        print(f"  saved: {path}")


class TestFluxAPISmoke:
    @pytest.mark.smoke
    def test_flux_api_single(self, flux_api_generator):
        img = _generate_and_check_api(
            flux_api_generator,
            SMOKE_PROMPT,
            model_tag="flux",
            num_inference_steps=DEFAULT_STEPS,
        )
        path = _save_output(img, TEST_OUTPUT_DIR /"flux_api_smoke", "smoke")
        print(f"  saved: {path}")


class TestSDXLAPIPrompts:
    @pytest.mark.parametrize(
        "prompt", PROMPTS, ids=[f"p{i}" for i in range(len(PROMPTS))]
    )
    def test_sdxl_api_prompt(self, sdxl_api_generator, prompt):
        img = _generate_and_check_api(sdxl_api_generator, prompt, model_tag="sdxl")
        idx = PROMPTS.index(prompt)
        _save_output(img, TEST_OUTPUT_DIR /"sdxl_api_prompts", f"prompt_{idx:02d}")


class TestFluxAPIPrompts:
    @pytest.mark.parametrize(
        "prompt", PROMPTS, ids=[f"p{i}" for i in range(len(PROMPTS))]
    )
    def test_flux_api_prompt(self, flux_api_generator, prompt):
        img = _generate_and_check_api(flux_api_generator, prompt, model_tag="flux")
        idx = PROMPTS.index(prompt)
        _save_output(img, TEST_OUTPUT_DIR /"flux_api_prompts", f"prompt_{idx:02d}")

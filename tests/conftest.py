from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.config import PipelineConfig
from src.pipeline.runner import PipelineRunner


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def runner(project_root: Path) -> PipelineRunner:
    cfg = PipelineConfig.from_project_root(project_root)
    return PipelineRunner(cfg)


@pytest.fixture
def small_runner(project_root: Path) -> PipelineRunner:
    cfg = PipelineConfig(project_root=project_root, n_groups=4)
    return PipelineRunner(cfg)

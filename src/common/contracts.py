from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Source = Literal["real", "ml_a", "ml_b"]
Method = Literal["lsb", "dct"]
PayloadLevel = Literal["low", "medium", "high"]
EncryptionState = Literal["plain", "encrypted"]
CoverBranch = Literal["spatial", "frequency"]

SOURCES: tuple[Source, ...] = ("real", "ml_a", "ml_b")
METHODS: tuple[Method, ...] = ("lsb", "dct")
PAYLOAD_LEVELS: tuple[PayloadLevel, ...] = ("low", "medium", "high")
ENCRYPTION_STATES: tuple[EncryptionState, ...] = ("plain", "encrypted")
COVER_BRANCHES: tuple[CoverBranch, ...] = ("spatial", "frequency")


def cover_branch_for_method(method: Method) -> CoverBranch:
    """Map one embedding method to the cover-storage branch it requires."""
    return "spatial" if method == "lsb" else "frequency"


def cover_extension(branch: CoverBranch) -> str:
    """Return the proposal-locked file extension for one cover branch."""
    return ".png" if branch == "spatial" else ".jpg"


@dataclass(frozen=True)
class PipelinePaths:
    project_root: Path
    data_root: Path
    results_root: Path
    manifests_dir: Path
    predictions_dir: Path
    metrics_dir: Path
    figures_dir: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "PipelinePaths":
        data_root = project_root / "data"
        results_root = project_root / "results"
        return cls(
            project_root=project_root,
            data_root=data_root,
            results_root=results_root,
            manifests_dir=data_root / "manifests",
            predictions_dir=results_root / "predictions",
            metrics_dir=results_root / "metrics",
            figures_dir=results_root / "figures",
        )

    def covers_dir(self, source: Source) -> Path:
        """All cover variants for one source live together; branch is implicit in extension."""
        return self.data_root / "covers" / source

    def cover_path(self, group_id: int, source: Source, branch: CoverBranch) -> Path:
        return self.covers_dir(source) / cover_filename(group_id, source, branch)

    def stego_path(
        self,
        group_id: int,
        source: Source,
        method: Method,
        payload: PayloadLevel,
        encryption: EncryptionState,
    ) -> Path:
        """Fallback stego path (used when no run_dir is set)."""
        return (
            self.data_root / "stego" / method / payload / encryption / source
            / stego_filename(
                group_id=group_id,
                source=source,
                method=method,
                payload=payload,
                encryption=encryption,
            )
        )

    def payload_path(
        self,
        group_id: int,
        payload: PayloadLevel,
        encryption: EncryptionState,
    ) -> Path:
        """Fallback payload path (used when no run_dir is set)."""
        return (
            self.data_root / "payloads" / encryption / payload
            / payload_filename(group_id, payload, encryption)
        )

    def ensure_layout(self) -> None:
        """Create only the directories that must exist before the pipeline starts.

        Stego and payload directories are created on-demand per run; only the
        cover image directories and manifests directory need to be pre-created.
        """
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        for source in SOURCES:
            self.covers_dir(source).mkdir(parents=True, exist_ok=True)


def cover_filename(group_id: int, source: Source, branch: CoverBranch) -> str:
    return f"g{group_id:04d}__src-{source}{cover_extension(branch)}"


def payload_filename(group_id: int, payload: PayloadLevel, encryption: EncryptionState) -> str:
    return f"g{group_id:04d}__p-{payload}__e-{encryption}.bin"


def stego_filename(
    group_id: int,
    source: Source,
    method: Method,
    payload: PayloadLevel,
    encryption: EncryptionState,
) -> str:
    ext = ".png" if method == "lsb" else ".jpg"
    return f"g{group_id:04d}__src-{source}__m-{method}__p-{payload}__e-{encryption}{ext}"

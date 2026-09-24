"""Pinned embedding model artifacts and a verified downloader.

The manifest is the single source of truth for which bytes the service runs.
The Docker build, local development, and ingestion all resolve the same
immutable Hugging Face revision and reject any file whose SHA-256 differs.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
EMBEDDING_DIMENSION = 384

EmbeddingVariant = Literal["onnx-qint8", "onnx-fp32"]
DEFAULT_VARIANT: EmbeddingVariant = "onnx-qint8"


@dataclass(frozen=True, slots=True)
class ModelFile:
    """One pinned repository file and the local name it is stored under."""

    repo_path: str
    local_name: str
    sha256: str


TOKENIZER_FILE = ModelFile(
    repo_path="onnx/tokenizer.json",
    local_name="tokenizer.json",
    sha256="0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
)

MODEL_FILES: dict[EmbeddingVariant, ModelFile] = {
    # Dynamic int8 export published in the pinned revision: ~118 MB instead of
    # ~470 MB, with retrieval quality verified by scripts/evaluate_retrieval.py.
    "onnx-qint8": ModelFile(
        repo_path="onnx/model_qint8_avx512_vnni.onnx",
        local_name="model_qint8.onnx",
        sha256="dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88",
    ),
    "onnx-fp32": ModelFile(
        repo_path="onnx/model.onnx",
        local_name="model_fp32.onnx",
        sha256="ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
    ),
}

_DOWNLOAD_TIMEOUT_SECONDS = 120
_CHUNK_BYTES = 1024 * 1024


def default_model_dir() -> Path:
    """Per-revision cache directory used when EMBEDDING_MODEL_PATH is unset."""

    cache_root = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_root / "serverless-rag" / f"multilingual-e5-small-{MODEL_REVISION[:12]}"


def required_files(variant: EmbeddingVariant) -> tuple[ModelFile, ...]:
    return (TOKENIZER_FILE, MODEL_FILES[variant])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            # URL is built from constants in this module, never from user input.
            with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
                for block in iter(lambda: response.read(_CHUNK_BYTES), b""):
                    digest.update(block)
                    handle.write(block)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    if digest.hexdigest() != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {url}")
    # NamedTemporaryFile is 0600; model files are read-only data for any user.
    temporary.chmod(0o644)
    temporary.replace(destination)


def ensure_model_files(
    model_dir: Path,
    variant: EmbeddingVariant,
    *,
    allow_download: bool,
    verify: bool = False,
) -> Path:
    """Return ``model_dir`` once every pinned file is present.

    Missing files are downloaded from the pinned revision when allowed.
    ``verify`` re-hashes files that already exist; the image build uses it,
    while the hot startup path skips re-hashing ~130 MB on every cold start.
    """

    for model_file in required_files(variant):
        target = model_dir / model_file.local_name
        if target.is_file():
            if verify and _sha256(target) != model_file.sha256:
                raise RuntimeError(f"Checksum mismatch for {target}")
            continue
        if not allow_download:
            raise RuntimeError(f"Embedding model file is missing and downloads are disabled: {target}")
        url = f"https://huggingface.co/{MODEL_NAME}/resolve/{MODEL_REVISION}/{model_file.repo_path}"
        _download(url, target, model_file.sha256)
    return model_dir


def main() -> int:
    """Download and verify the pinned model files (used by the image build)."""

    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--download", type=Path, required=True, help="Target model directory")
    parser.add_argument("--variant", choices=sorted(MODEL_FILES), default=DEFAULT_VARIANT)
    args = parser.parse_args()
    ensure_model_files(args.download, args.variant, allow_download=True, verify=True)
    print(f"Verified {args.variant} files for {MODEL_NAME}@{MODEL_REVISION[:12]} in {args.download}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

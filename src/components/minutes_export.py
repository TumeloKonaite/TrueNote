from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.contracts.artifacts import DocxArtifact
from src.contracts.errors import InputValidationError
from src.utils.hashing import sha256_file


class MarkdownDocxExporter(Protocol):
    def markdown_to_docx(
        self,
        input_markdown_path: Path,
        output_docx_path: Path,
        *,
        reference_docx_path: Path | None = None,
        toc: bool = False,
        toc_depth: int = 2,
    ) -> Path:
        """Convert markdown to a .docx file and return the produced output path."""


def export_minutes_docx(
    minutes_markdown_path: Path,
    output_docx_path: Path,
    *,
    exporter: MarkdownDocxExporter,
    reference_docx_path: Path | None = None,
    toc: bool = False,
    toc_depth: int = 2,
) -> DocxArtifact:
    md_path = Path(minutes_markdown_path)
    out_path = Path(output_docx_path)
    reference_path = Path(reference_docx_path) if reference_docx_path is not None else None

    if not md_path.exists() or not md_path.is_file():
        raise InputValidationError(f"minutes markdown not found: {md_path}")
    if md_path.suffix.lower() != ".md":
        raise InputValidationError(f"minutes markdown must be a .md file: {md_path}")
    if out_path.suffix.lower() != ".docx":
        raise InputValidationError(f"minutes docx output must end with .docx: {out_path}")
    if reference_path is not None and (not reference_path.exists() or not reference_path.is_file()):
        raise InputValidationError(f"reference docx not found: {reference_path}")

    produced_path = exporter.markdown_to_docx(
        md_path,
        out_path,
        reference_docx_path=reference_path,
        toc=toc,
        toc_depth=toc_depth,
    )
    final_path = Path(produced_path)
    if not final_path.exists() or not final_path.is_file():
        raise InputValidationError(f"docx export did not produce output: {final_path}")

    return DocxArtifact(
        path=final_path,
        sha256=sha256_file(final_path),
        meta={
            "source_markdown_path": str(md_path),
            "reference_docx_path": str(reference_path) if reference_path is not None else None,
            "toc": toc,
            "toc_depth": toc_depth if toc else None,
        },
    )


__all__ = [
    "MarkdownDocxExporter",
    "export_minutes_docx",
]

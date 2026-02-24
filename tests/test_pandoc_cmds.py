from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.pandoc import (
    PANDOC_PATH_ENV_VAR,
    build_pandoc_markdown_to_docx_cmd,
    resolve_pandoc_executable,
)
from src.contracts.errors import PandocError


def test_build_pandoc_markdown_to_docx_cmd_minimal() -> None:
    cmd = build_pandoc_markdown_to_docx_cmd("pandoc", Path("minutes.md"), Path("minutes.docx"))

    assert cmd == [
        "pandoc",
        "--from",
        "markdown",
        "--to",
        "docx",
        str(Path("minutes.md")),
        "--output",
        str(Path("minutes.docx")),
    ]


def test_build_pandoc_markdown_to_docx_cmd_with_reference_doc_and_toc() -> None:
    cmd = build_pandoc_markdown_to_docx_cmd(
        "pandoc.exe",
        "minutes.md",
        "minutes.docx",
        reference_docx_path="templates/reference.docx",
        toc=True,
        toc_depth=3,
    )

    assert cmd == [
        "pandoc.exe",
        "--from",
        "markdown",
        "--to",
        "docx",
        str(Path("minutes.md")),
        "--output",
        str(Path("minutes.docx")),
        "--reference-doc",
        str(Path("templates/reference.docx")),
        "--toc",
        "--toc-depth",
        "3",
    ]


def test_resolve_pandoc_prefers_path_before_env_override() -> None:
    resolved = resolve_pandoc_executable(
        env={PANDOC_PATH_ENV_VAR: str(Path("C:/custom/pandoc.exe"))},
        which=lambda name: str(Path("C:/path/pandoc.exe")),
        platform_name="Windows",
    )

    assert resolved == Path("C:/path/pandoc.exe")


def test_resolve_pandoc_uses_env_override_when_valid(tmp_path: Path) -> None:
    pandoc_path = tmp_path / "pandoc.exe"
    pandoc_path.write_text("", encoding="utf-8")

    resolved = resolve_pandoc_executable(
        env={PANDOC_PATH_ENV_VAR: str(pandoc_path)},
        which=lambda name: None,
        platform_name="Windows",
    )

    assert resolved == pandoc_path


def test_resolve_pandoc_invalid_env_override_raises_clear_error() -> None:
    with pytest.raises(PandocError, match=PANDOC_PATH_ENV_VAR):
        resolve_pandoc_executable(
            env={PANDOC_PATH_ENV_VAR: r"C:\missing\pandoc.exe"},
            which=lambda name: None,
            platform_name="Windows",
        )


def test_resolve_pandoc_uses_windows_fallback_locations(tmp_path: Path) -> None:
    program_files = tmp_path / "ProgramFiles"
    fallback = program_files / "Pandoc" / "pandoc.exe"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.write_text("", encoding="utf-8")

    resolved = resolve_pandoc_executable(
        env={"ProgramFiles": str(program_files)},
        which=lambda name: None,
        platform_name="Windows",
    )

    assert resolved == fallback


def test_resolve_pandoc_missing_raises_clear_error() -> None:
    with pytest.raises(PandocError, match="pandoc not found"):
        resolve_pandoc_executable(env={}, which=lambda name: None, platform_name="Windows")


def test_build_pandoc_rejects_invalid_toc_depth() -> None:
    with pytest.raises(ValueError):
        build_pandoc_markdown_to_docx_cmd("pandoc", "minutes.md", "minutes.docx", toc=True, toc_depth=0)

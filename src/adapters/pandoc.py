from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Callable, Mapping

from src.contracts.errors import PandocError


type StrPath = str | PathLike[str]

PANDOC_PATH_ENV_VAR = "PANDOC_PATH"


def _path_str(value: StrPath) -> str:
    return str(Path(value))


def _windows_pandoc_candidates(env: Mapping[str, str]) -> list[Path]:
    candidates: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "ChocolateyInstall"):
        base = env.get(key)
        if not base:
            continue
        base_path = Path(base)
        if key == "ChocolateyInstall":
            candidates.append(base_path / "bin" / "pandoc.exe")
            continue
        candidates.append(base_path / "Pandoc" / "pandoc.exe")
    candidates.extend(
        [
            Path(r"C:\Program Files\Pandoc\pandoc.exe"),
            Path(r"C:\Program Files (x86)\Pandoc\pandoc.exe"),
            Path(r"C:\Users\Public\Pandoc\pandoc.exe"),
        ]
    )
    # Preserve order while removing duplicates.
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def resolve_pandoc_executable(
    *,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    platform_name: str | None = None,
) -> Path:
    effective_env: Mapping[str, str] = dict(os.environ) if env is None else env

    from_path = which("pandoc")
    if from_path:
        return Path(from_path)

    env_override = effective_env.get(PANDOC_PATH_ENV_VAR)
    if env_override:
        override_path = Path(env_override)
        if override_path.is_file():
            return override_path
        raise PandocError(
            f"{PANDOC_PATH_ENV_VAR} is set but pandoc was not found at: {override_path}"
        )

    if (platform_name or os.name).lower() in {"nt", "windows"}:
        for candidate in _windows_pandoc_candidates(effective_env):
            if candidate.is_file():
                return candidate

    raise PandocError(
        "pandoc not found. Install Pandoc and add it to PATH, or set PANDOC_PATH to the executable path."
    )


def build_pandoc_markdown_to_docx_cmd(
    pandoc_executable: StrPath,
    input_markdown_path: StrPath,
    output_docx_path: StrPath,
    *,
    reference_docx_path: StrPath | None = None,
    toc: bool = False,
    toc_depth: int = 2,
) -> list[str]:
    if toc_depth <= 0:
        raise ValueError("toc_depth must be > 0")

    cmd = [
        _path_str(pandoc_executable),
        "--from",
        "markdown",
        "--to",
        "docx",
        _path_str(input_markdown_path),
        "--output",
        _path_str(output_docx_path),
    ]
    if reference_docx_path is not None:
        cmd.extend(["--reference-doc", _path_str(reference_docx_path)])
    if toc:
        cmd.append("--toc")
        cmd.extend(["--toc-depth", str(toc_depth)])
    return cmd


@dataclass(frozen=True, slots=True)
class PandocAdapter:
    pandoc_executable: Path | None = None
    env: Mapping[str, str] | None = None

    def markdown_to_docx(
        self,
        input_markdown_path: StrPath,
        output_docx_path: StrPath,
        *,
        reference_docx_path: StrPath | None = None,
        toc: bool = False,
        toc_depth: int = 2,
    ) -> Path:
        input_path = Path(input_markdown_path)
        output_path = Path(output_docx_path)
        reference_path = Path(reference_docx_path) if reference_docx_path is not None else None

        if not input_path.exists() or not input_path.is_file():
            raise PandocError(f"markdown input not found: {input_path}")
        if reference_path is not None and (not reference_path.exists() or not reference_path.is_file()):
            raise PandocError(f"reference docx not found: {reference_path}")

        pandoc_path = self.pandoc_executable or resolve_pandoc_executable(env=self.env)
        cmd = build_pandoc_markdown_to_docx_cmd(
            pandoc_path,
            input_path,
            output_path,
            reference_docx_path=reference_path,
            toc=toc,
            toc_depth=toc_depth,
        )
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "pandoc conversion failed"
            raise PandocError(message)
        if not output_path.exists() or not output_path.is_file():
            raise PandocError(f"pandoc did not produce docx output: {output_path}")
        return output_path


__all__ = [
    "PANDOC_PATH_ENV_VAR",
    "PandocAdapter",
    "build_pandoc_markdown_to_docx_cmd",
    "resolve_pandoc_executable",
]

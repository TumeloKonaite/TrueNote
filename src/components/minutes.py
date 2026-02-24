from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.contracts.artifacts import MinutesArtifact, TranscriptArtifact
from src.contracts.errors import InputValidationError, MinutesGenerationError
from src.utils.hashing import sha256_file


DEFAULT_MINUTES_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "minutes_prompt.md"


@dataclass(frozen=True, slots=True)
class LoadedMinutesPrompt:
    path: Path
    text: str
    prompt_hash: str


class MinutesLLM(Protocol):
    """Provider adapter boundary for minutes generation."""

    def generate_minutes(
        self,
        transcript: TranscriptArtifact,
        *,
        prompt: str,
        extra_context: dict[str, str] | None = None,
    ) -> MinutesArtifact:
        """Return a normalized minutes artifact for the given transcript and prompt."""


def load_minutes_prompt(prompt_path: Path = DEFAULT_MINUTES_PROMPT_PATH) -> LoadedMinutesPrompt:
    path = Path(prompt_path)
    if not path.exists():
        raise InputValidationError(f"minutes prompt not found: {path}")
    if not path.is_file():
        raise InputValidationError(f"minutes prompt is not a file: {path}")

    prompt_text = path.read_text(encoding="utf-8")
    if not prompt_text.strip():
        raise InputValidationError(f"minutes prompt is empty: {path}")

    return LoadedMinutesPrompt(
        path=path,
        text=prompt_text,
        prompt_hash=sha256_file(path),
    )


def generate_minutes(
    transcript: TranscriptArtifact,
    *,
    llm: MinutesLLM,
    prompt_path: Path = DEFAULT_MINUTES_PROMPT_PATH,
    prompt_version: str | None = None,
    extra_context: dict[str, str] | None = None,
) -> MinutesArtifact:
    if not transcript.text.strip():
        raise InputValidationError("transcript.text must not be empty")

    loaded_prompt = load_minutes_prompt(prompt_path)

    try:
        llm_result = llm.generate_minutes(
            transcript,
            prompt=loaded_prompt.text,
            extra_context=extra_context,
        )
    except MinutesGenerationError:
        raise
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        raise MinutesGenerationError(f"minutes generation failed: {exc}") from exc

    if not isinstance(llm_result, MinutesArtifact):
        raise MinutesGenerationError("minutes llm must return MinutesArtifact")
    if not llm_result.markdown.strip():
        raise MinutesGenerationError("minutes llm returned empty markdown")
    if not llm_result.model.strip():
        raise MinutesGenerationError("minutes llm returned empty model")

    meta = dict(llm_result.meta or {})
    meta["prompt_path"] = str(loaded_prompt.path)
    meta["prompt_hash"] = loaded_prompt.prompt_hash
    effective_prompt_version = prompt_version if prompt_version is not None else llm_result.prompt_version
    if effective_prompt_version is not None:
        meta["prompt_version"] = effective_prompt_version

    return MinutesArtifact(
        markdown=llm_result.markdown,
        model=llm_result.model,
        prompt_version=effective_prompt_version,
        tokens=llm_result.tokens,
        meta=meta,
    )


__all__ = [
    "DEFAULT_MINUTES_PROMPT_PATH",
    "LoadedMinutesPrompt",
    "MinutesLLM",
    "generate_minutes",
    "load_minutes_prompt",
]

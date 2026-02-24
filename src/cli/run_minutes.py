from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from src.adapters.ffmpeg import build_ffmpeg_chunk_cmd, build_ffmpeg_normalize_cmd
from src.adapters.openai_transcription import OpenAITranscriptionAdapter
from src.components.minutes import MinutesLLM
from src.contracts.artifacts import AudioArtifact, MinutesArtifact, TranscriptArtifact
from src.contracts.errors import FfmpegError
from src.pipeline.io import build_pipeline_paths
from src.pipeline.prediction_pipeline import PipelineConfig, run as run_pipeline
from src.utils.hashing import sha256_file


type Argv = Sequence[str]


@dataclass(frozen=True, slots=True)
class CliRunResult:
    manifest_path: Path
    output_dir: Path


class _FfmpegChunkAdapter:
    def chunk_audio(self, input_audio: str | Path, chunks_dir: str | Path, chunk_seconds: int) -> None:
        cmd = build_ffmpeg_chunk_cmd(input_audio, chunks_dir, chunk_seconds)
        _run_ffmpeg_or_raise(cmd, "ffmpeg chunking failed")


class _FfmpegAudioNormalizer:
    def __init__(self, *, sample_rate: int, channels: int = 1) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    def normalize_audio(self, input_path: Path, output_path: Path) -> AudioArtifact:
        cmd = build_ffmpeg_normalize_cmd(
            input_path=input_path,
            output_path=output_path,
            sample_rate=self._sample_rate,
            channels=self._channels,
        )
        _run_ffmpeg_or_raise(cmd, "ffmpeg normalization failed")
        if not output_path.exists() or not output_path.is_file():
            raise FfmpegError(f"ffmpeg did not produce normalized audio: {output_path}")
        return AudioArtifact(
            path=output_path,
            sha256=sha256_file(output_path),
            sample_rate=self._sample_rate,
            channels=self._channels,
        )


class _OpenAIMinutesLLM(MinutesLLM):
    def __init__(self, client: Any, *, model: str) -> None:
        if not model:
            raise ValueError("minutes model is required")
        self._client = client
        self._model = model

    def generate_minutes(
        self,
        transcript: TranscriptArtifact,
        *,
        prompt: str,
        extra_context: dict[str, str] | None = None,
    ) -> MinutesArtifact:
        message = _build_minutes_message(prompt=prompt, transcript=transcript.text, extra_context=extra_context)
        text = _call_openai_text(client=self._client, model=self._model, message=message)
        return MinutesArtifact(markdown=text, model=self._model)


def _build_minutes_message(*, prompt: str, transcript: str, extra_context: dict[str, str] | None) -> str:
    parts = [prompt.strip(), "", "Transcript:", transcript.strip()]
    if extra_context:
        parts.extend(["", "Extra context:"])
        for key, value in sorted(extra_context.items()):
            parts.append(f"- {key}: {value}")
    return "\n".join(parts).strip()


def _call_openai_text(*, client: Any, model: str, message: str) -> str:
    responses_api = getattr(client, "responses", None)
    if responses_api is not None and hasattr(responses_api, "create"):
        response = responses_api.create(model=model, input=message)
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

    chat_api = getattr(client, "chat", None)
    completions_api = getattr(chat_api, "completions", None) if chat_api is not None else None
    if completions_api is not None and hasattr(completions_api, "create"):
        response = completions_api.create(
            model=model,
            messages=[{"role": "user", "content": message}],
        )
        text = _extract_chat_completion_text(response)
        if text:
            return text

    raise RuntimeError("unable to extract text from OpenAI response")


def _extract_chat_completion_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = _field(item, "text")
            if text:
                chunks.append(str(text))
        return "\n".join(chunks).strip()
    return ""


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _run_ffmpeg_or_raise(cmd: Sequence[str], fallback_message: str) -> None:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode == 0:
        return
    message = completed.stderr.strip() or completed.stdout.strip() or fallback_message
    raise FfmpegError(message)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid int value: {value}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid int value: {value}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def _kv_pair(value: str) -> str:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected KEY=VALUE")
    key, _, raw_value = value.partition("=")
    if not key.strip():
        raise argparse.ArgumentTypeError("context key must not be empty")
    return f"{key}={raw_value}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Minutes pipeline.")
    parser.add_argument("--input", dest="input_path", type=Path, required=True, help="Input audio file path.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output artifacts directory.")
    parser.add_argument("--provider", choices=["openai"], required=True, help="Transcription provider.")
    parser.add_argument("--model", required=True, help="Transcription model (for the selected provider).")
    parser.add_argument("--chunk-seconds", type=_positive_int, required=True, help="Chunk size in seconds.")
    parser.add_argument("--sample-rate", type=_positive_int, default=16000, help="Normalized WAV sample rate.")
    parser.add_argument("--channels", type=_positive_int, default=1, help="Normalized WAV channel count.")
    parser.add_argument("--language", default=None, help="Transcription language code (e.g. en).")
    parser.add_argument("--transcription-prompt", default=None, help="Optional provider prompt for transcription.")
    parser.add_argument(
        "--transcription-max-retries",
        type=_nonnegative_int,
        default=2,
        help="Provider retries per chunk (>= 0).",
    )
    parser.add_argument("--minutes-model", default="gpt-4o-mini", help="Minutes generation model.")
    parser.add_argument("--prompt-path", type=Path, default=None, help="Minutes prompt file path.")
    parser.add_argument("--prompt-version", default=None, help="Prompt version recorded in the manifest.")
    parser.add_argument(
        "--minutes-extra-context",
        action="append",
        type=_kv_pair,
        default=[],
        help="Additional minutes context as KEY=VALUE (repeatable).",
    )
    parser.add_argument("--run-id", default=None, help="Optional deterministic run identifier.")
    parser.add_argument(
        "--include-error-traceback",
        action="store_true",
        help="Persist traceback details in manifest step errors.",
    )
    return parser


def parse_args(argv: Argv | None = None) -> argparse.Namespace:
    return build_parser().parse_args(list(argv) if argv is not None else None)


def build_pipeline_config(
    args: argparse.Namespace,
    *,
    normalizer: Any,
    ffmpeg: Any,
    transcription_provider: Any,
    minutes_llm: Any,
) -> PipelineConfig:
    return PipelineConfig(
        output_dir=Path(args.output_dir),
        normalizer=normalizer,
        ffmpeg=ffmpeg,
        transcription_provider=transcription_provider,
        minutes_llm=minutes_llm,
        chunk_seconds=int(args.chunk_seconds),
        prompt_path=Path(args.prompt_path) if args.prompt_path is not None else None,
        prompt_version=args.prompt_version,
        minutes_extra_context=_minutes_extra_context_dict(args.minutes_extra_context),
        include_error_traceback=bool(args.include_error_traceback),
        run_id=args.run_id,
    )


def _minutes_extra_context_dict(entries: list[str]) -> dict[str, str] | None:
    if not entries:
        return None
    parsed: dict[str, str] = {}
    for entry in entries:
        key, _, value = entry.partition("=")
        parsed[key] = value
    return parsed or None


def _load_openai_client() -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on local runtime
        raise RuntimeError("The 'openai' package is required to use the CLI (pip install openai).") from exc
    return OpenAI()


def _build_runtime_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    if args.provider != "openai":
        raise ValueError(f"unsupported provider: {args.provider}")

    client = _load_openai_client()
    return {
        "normalizer": _FfmpegAudioNormalizer(sample_rate=int(args.sample_rate), channels=int(args.channels)),
        "ffmpeg": _FfmpegChunkAdapter(),
        "transcription_provider": OpenAITranscriptionAdapter(
            client,
            model=args.model,
            language=args.language,
            prompt=args.transcription_prompt,
            max_retries_per_chunk=int(args.transcription_max_retries),
        ),
        "minutes_llm": _OpenAIMinutesLLM(client, model=args.minutes_model),
    }


def run_from_args(args: argparse.Namespace) -> CliRunResult:
    deps = _build_runtime_dependencies(args)
    config = build_pipeline_config(args, **deps)
    run_pipeline(Path(args.input_path), config)
    paths = build_pipeline_paths(Path(args.output_dir))
    return CliRunResult(manifest_path=paths.manifest_path, output_dir=paths.run_dir)


def main(argv: Argv | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_from_args(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"manifest_path={result.manifest_path}")
    print(f"output_dir={result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

import pytest

from src.cli import run_minutes as cli
from src.pipeline.prediction_pipeline import PipelineConfig


def test_parse_args_maps_cli_flags() -> None:
    args = cli.parse_args(
        [
            "--input",
            "audio.wav",
            "--output-dir",
            "outputs",
            "--provider",
            "openai",
            "--model",
            "whisper-1",
            "--chunk-seconds",
            "30",
            "--sample-rate",
            "16000",
            "--language",
            "en",
            "--minutes-extra-context",
            "team=platform",
            "--minutes-extra-context",
            "timezone=UTC",
            "--prompt-version",
            "v1",
            "--include-error-traceback",
        ]
    )

    assert args.input_path == Path("audio.wav")
    assert args.output_dir == Path("outputs")
    assert args.provider == "openai"
    assert args.model == "whisper-1"
    assert args.chunk_seconds == 30
    assert args.sample_rate == 16000
    assert args.language == "en"
    assert args.prompt_version == "v1"
    assert args.minutes_extra_context == ["team=platform", "timezone=UTC"]
    assert args.include_error_traceback is True


def test_build_pipeline_config_maps_pipeline_fields() -> None:
    args = cli.parse_args(
        [
            "--input",
            "audio.wav",
            "--output-dir",
            "outputs",
            "--provider",
            "openai",
            "--model",
            "whisper-1",
            "--chunk-seconds",
            "45",
            "--prompt-path",
            "prompt.md",
            "--prompt-version",
            "v2",
            "--run-id",
            "run_123",
            "--minutes-extra-context",
            "project=minutes",
        ]
    )

    normalizer = object()
    ffmpeg = object()
    provider = object()
    minutes_llm = object()
    pandoc = object()
    config = cli.build_pipeline_config(
        args,
        normalizer=normalizer,
        ffmpeg=ffmpeg,
        transcription_provider=provider,
        minutes_llm=minutes_llm,
        pandoc=pandoc,
    )

    assert isinstance(config, PipelineConfig)
    assert config.output_dir == Path("outputs")
    assert config.normalizer is normalizer
    assert config.ffmpeg is ffmpeg
    assert config.transcription_provider is provider
    assert config.minutes_llm is minutes_llm
    assert config.docx_exporter is pandoc
    assert config.chunk_seconds == 45
    assert config.prompt_path == Path("prompt.md")
    assert config.prompt_version == "v2"
    assert config.run_id == "run_123"
    assert config.minutes_extra_context == {"project": "minutes"}
    assert config.include_error_traceback is False


def test_run_from_args_delegates_to_orchestrator_and_returns_deterministic_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_build_runtime_dependencies(args):  # type: ignore[no-untyped-def]
        captured["provider"] = args.provider
        captured["model"] = args.model
        captured["language"] = args.language
        captured["sample_rate"] = args.sample_rate
        return {
            "normalizer": object(),
            "ffmpeg": object(),
            "transcription_provider": object(),
            "minutes_llm": object(),
            "pandoc": object(),
        }

    def fake_run_pipeline(input_path, config):  # type: ignore[no-untyped-def]
        captured["input_path"] = input_path
        captured["config"] = config
        return object()

    monkeypatch.setattr(cli, "_build_runtime_dependencies", fake_build_runtime_dependencies)
    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    args = cli.parse_args(
        [
            "--input",
            "audio.wav",
            "--output-dir",
            "outputs",
            "--provider",
            "openai",
            "--model",
            "whisper-1",
            "--chunk-seconds",
            "30",
            "--sample-rate",
            "16000",
            "--language",
            "en",
            "--export-docx",
            "--reference-docx",
            "templates/reference.docx",
            "--docx-toc",
            "--docx-toc-depth",
            "3",
        ]
    )
    result = cli.run_from_args(args)

    assert captured["provider"] == "openai"
    assert captured["model"] == "whisper-1"
    assert captured["language"] == "en"
    assert captured["sample_rate"] == 16000
    assert captured["input_path"] == Path("audio.wav")
    assert isinstance(captured["config"], PipelineConfig)
    assert captured["config"].export_minutes_docx is True
    assert captured["config"].reference_docx_path == Path("templates/reference.docx")
    assert captured["config"].docx_toc is True
    assert captured["config"].docx_toc_depth == 3
    assert result.manifest_path == Path("outputs") / "manifest.json"
    assert result.output_dir == Path("outputs")


def test_main_success_prints_paths_and_returns_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        cli,
        "run_from_args",
        lambda args: cli.CliRunResult(manifest_path=Path("outputs/manifest.json"), output_dir=Path("outputs")),
    )

    exit_code = cli.main(
        [
            "--input",
            "audio.wav",
            "--output-dir",
            "outputs",
            "--provider",
            "openai",
            "--model",
            "whisper-1",
            "--chunk-seconds",
            "30",
        ]
    )
    out = capsys.readouterr()

    assert exit_code == 0
    assert out.err == ""
    assert out.out.splitlines() == [
        f"manifest_path={Path('outputs') / 'manifest.json'}",
        "output_dir=outputs",
    ]


def test_main_failure_returns_nonzero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def raise_error(args):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run_from_args", raise_error)

    exit_code = cli.main(
        [
            "--input",
            "audio.wav",
            "--output-dir",
            "outputs",
            "--provider",
            "openai",
            "--model",
            "whisper-1",
            "--chunk-seconds",
            "30",
        ]
    )
    out = capsys.readouterr()

    assert exit_code == 1
    assert "error: boom" in out.err

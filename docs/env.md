# Environment and Runtime Configuration

This project's CLI uses the OpenAI Python SDK for transcription and minutes generation. The SDK reads `OPENAI_API_KEY` from the process environment.

## Required Environment Variable

- `OPENAI_API_KEY`: Required for OpenAI API calls (transcription + minutes generation).

## Model Selection (CLI vs `.env`)

Current behavior:
- The CLI reads model names from explicit CLI flags, not from `.env`.
- Transcription model: `--model`
- Minutes model: `--minutes-model`

You can still keep preferred values in a local `.env` for convenience, but you must pass them into the CLI yourself (or via a shell wrapper/script).

Suggested local aliases (optional, not read by the CLI directly):
- `MINUTES_TRANSCRIPTION_MODEL`
- `MINUTES_MINUTES_MODEL`
- `MINUTES_LANGUAGE`
- `MINUTES_CHUNK_SECONDS`
- `MINUTES_PROMPT_PATH`
- `MINUTES_PROMPT_VERSION`
- `MINUTES_TRANSCRIPTION_MAX_RETRIES`

## Runtime Knobs Used by the CLI

Common CLI flags you may want to standardize in local workflows:
- `--input` (source audio path)
- `--output-dir` (run directory for artifacts)
- `--provider` (currently only `openai`)
- `--model` (OpenAI transcription model)
- `--minutes-model` (OpenAI text model for minutes)
- `--chunk-seconds` (required; ffmpeg chunk size)
- `--sample-rate` (default `16000`)
- `--channels` (default `1`)
- `--language` (optional transcription language code, e.g. `en`)
- `--transcription-prompt` (optional provider prompt)
- `--transcription-max-retries` (default `2`)
- `--prompt-path` (minutes prompt file path; defaults to `src/prompts/minutes_prompt.md`)
- `--prompt-version` (recorded in manifest)
- `--minutes-extra-context KEY=VALUE` (repeatable)
- `--run-id` (optional deterministic run id)
- `--include-error-traceback` (include traceback in manifest step errors)

## `.env` Example (Copy/Paste)

The CLI does not parse `.env` files automatically. Load this into your shell using your preferred tool (`dotenv`, PowerShell profile, `direnv`, etc.), then pass values to the CLI.

```dotenv
# Required by OpenAI SDK
OPENAI_API_KEY=sk-...

# Optional local aliases (not read directly by the CLI)
MINUTES_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
MINUTES_MINUTES_MODEL=gpt-4o-mini
MINUTES_LANGUAGE=en
MINUTES_CHUNK_SECONDS=30
MINUTES_TRANSCRIPTION_MAX_RETRIES=2
MINUTES_PROMPT_PATH=src/prompts/minutes_prompt.md
MINUTES_PROMPT_VERSION=v1

# Example local paths for your shell wrapper
MINUTES_INPUT=path/to/meeting_audio.mp3
MINUTES_OUTPUT_DIR=artifacts/run-001
```

Example PowerShell invocation using env aliases:

```powershell
python run_minutes.py `
  --input $env:MINUTES_INPUT `
  --output-dir $env:MINUTES_OUTPUT_DIR `
  --provider openai `
  --model $env:MINUTES_TRANSCRIPTION_MODEL `
  --chunk-seconds ([int]$env:MINUTES_CHUNK_SECONDS) `
  --minutes-model $env:MINUTES_MINUTES_MODEL `
  --language $env:MINUTES_LANGUAGE `
  --transcription-max-retries ([int]$env:MINUTES_TRANSCRIPTION_MAX_RETRIES) `
  --prompt-path $env:MINUTES_PROMPT_PATH `
  --prompt-version $env:MINUTES_PROMPT_VERSION
```

## Local Dependencies (Non-env)

- `ffmpeg` must be installed and available on `PATH` (used for normalization and chunking).
- `openai` Python package must be installed in the active environment.

## Cleanup / Retention (Current Status)

Current default behavior:
- Keeps `normalized.wav` and `chunks/` after success.
- Does not automatically clean up partial artifacts on failure.

Configuration status:
- Cleanup/retention is not currently configurable via env vars or CLI flags.
- Future work: add explicit retention/cleanup controls.

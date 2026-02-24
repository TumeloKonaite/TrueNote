# Notebook Parity Smoke Check (OpenAI-only)

## Purpose

Single-input smoke procedure to verify the current CLI pipeline produces the expected artifact set and artifact shape when compared to the notebook flow.

Parity target:
- Artifact presence and basic shape/metadata
- Not exact transcript/minutes text equality

## Requirements

- Valid `OPENAI_API_KEY` in the environment
- Network access to OpenAI API
- `ffmpeg` installed and on `PATH`
- Python environment with project dependencies installed
- One test audio file used for both runs

This is a live/API smoke check. It is not suitable for offline CI unless OpenAI access is available.

## Inputs to Keep Aligned (Notebook vs CLI)

Use the same values where possible:
- Same input audio file
- Same transcription model (or closest equivalent used in notebook)
- Same minutes model
- Same language (if set)
- Same chunk duration

Differences that are acceptable:
- Exact wording of transcript and minutes
- Notebook chunk codec/extension vs CLI chunk codec/extension (notebook may use `.mp3`; CLI uses `chunk_####.wav`)
- Presence of CLI-only manifest (`manifest.json`)

## Procedure

1. Run the notebook `notebooks/3_Day_5_Meeting_Minutes_openai_only.ipynb` on the test input.
2. Confirm the notebook produces at least:
   - A transcript text file (for example `meeting_transcript.txt`)
   - A minutes markdown file (for example `meeting_minutes.md`)
   - Chunk artifacts if the chunking cell is part of the executed path
3. Run the CLI on the same input using a fresh output directory:

```powershell
python run_minutes.py `
  --input .\path\to\meeting_audio.mp3 `
  --output-dir .\artifacts\parity-smoke `
  --provider openai `
  --model gpt-4o-mini-transcribe `
  --chunk-seconds 30 `
  --minutes-model gpt-4o-mini `
  --language en `
  --transcription-max-retries 2
```

4. Verify the CLI exits successfully and prints `manifest_path=` and `output_dir=`.
5. Validate the CLI artifact set and manifest shape using the checks below.

## CLI Artifact Presence Checks

Expected in `--output-dir` (current pipeline contract):
- `manifest.json`
- `transcript.txt`
- `minutes.md`
- `normalized.wav`
- `chunks\chunk_####.wav` (one or more files)
- `transcript_segments.json` (optional; expected when provider returns segments)

PowerShell quick checks:

```powershell
$out = ".\artifacts\parity-smoke"
Test-Path "$out\manifest.json"
Test-Path "$out\transcript.txt"
Test-Path "$out\minutes.md"
Test-Path "$out\normalized.wav"
(Get-ChildItem "$out\chunks\chunk_*.wav" -ErrorAction Stop).Count -ge 1
```

## Manifest Shape Checks (CLI)

Verify `manifest.json` contains:
- Step records for `validate`, `normalize`, `chunk`, `transcribe`, `generate`, `write_outputs`
- `status = success` for each step
- Artifact refs/metadata for:
  - `transcript_path`
  - `minutes_md_path`
  - `chunks_dir`
  - `chunk_paths`
  - `normalized_audio_path`
- `transcript_segments_path` may be missing/null if provider returns no segments

PowerShell example:

```powershell
$m = Get-Content ".\artifacts\parity-smoke\manifest.json" -Raw | ConvertFrom-Json
$m.steps.validate.status
$m.steps.normalize.status
$m.steps.chunk.status
$m.steps.transcribe.status
$m.steps.generate.status
$m.steps.write_outputs.status
$m.artifacts.transcript_path
$m.artifacts.minutes_md_path
$m.artifacts.chunks_dir
$m.artifacts.normalized_audio_path
$m.artifacts.chunk_paths.Count
```

## Notebook vs CLI Parity Expectations

Pass if:
- Both flows produce transcript and minutes artifacts for the same input
- CLI produces the full pipeline artifact set listed above
- CLI manifest step statuses are all successful
- Artifact shapes are consistent with each flow (for example, chunk list exists, transcript/minutes files are non-empty)

Do not fail parity on:
- Transcript text differences
- Minutes wording/format differences
- Minor segment timing/count differences
- Different chunk file extensions/codecs between notebook and CLI

## Cleanup / Retention Note (Current Behavior)

Current CLI behavior keeps `normalized.wav` and `chunks/` after success and does not auto-clean partial artifacts on failure. Cleanup is not configurable yet.

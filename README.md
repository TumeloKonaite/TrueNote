## Minutes (OpenAI-only pipeline)

This repo includes a CLI pipeline that normalizes audio, chunks it, transcribes with OpenAI, and generates meeting minutes.

## Project Status

Status:
- Active development
- OpenAI-only CLI pipeline is implemented and usable for local runs
- Unit tests are automated in GitHub Actions (`.github/workflows/ci.yml`)
- Notebook parity smoke check is documented (`tests/smoke/test_notebook_parity.md`) and currently manual (live API required)

Current limitations:
- Exact notebook parity is artifact/shape parity, not text equality
- `gpt-4o*-transcribe` response-format compatibility in the adapter is not yet fully aligned with the notebook flow (`response_format="text"` in notebook)

## CI

GitHub Actions workflow:
- `.github/workflows/ci.yml` (runs unit tests on push / pull request / manual dispatch)

CI scope:
- Runs `pytest` unit tests with `PYTHONPATH=.` on Python 3.12 and 3.13
- Does not run the live OpenAI parity smoke check

Local equivalent:

```powershell
$env:PYTHONPATH='.'
pytest -q
```

## Artifact Contract

Parity target for the notebook and CLI is artifact production and shape, not exact transcript/minutes text.

`Same input -> produces artifacts` means:
- Given the same source audio and comparable model/settings, the pipeline should produce the expected output files and a valid manifest.
- Model output text may differ across runs/providers/models.

The current CLI writes artifacts directly into the run directory provided by `--output-dir` (there is no extra nested run folder).

Expected artifacts in `--output-dir`:
- `manifest.json` (step status + artifact references/metadata)
- `transcript.txt`
- `minutes.md`
- `normalized.wav`
- `chunks/` containing `chunk_####.wav`
- `transcript_segments.json` (only when the transcription provider returns segments; OpenAI adapter usually does)

Notes:
- `manifest.json` also stores transcript/minutes content in manifest artifact fields (`transcript_text`, `minutes_markdown`) in addition to file paths.
- Use a fresh `--output-dir` for each run. Reusing an output directory with a non-empty `chunks/` folder will fail the chunking step.

## Run (CLI)

Prereqs:
- Python 3.12+
- `ffmpeg` available on `PATH`
- `OPENAI_API_KEY` in the environment

Example:

```powershell
python run_minutes.py `
  --input .\path\to\meeting_audio.mp3 `
  --output-dir .\artifacts\run-001 `
  --provider openai `
  --model gpt-4o-mini-transcribe `
  --chunk-seconds 30 `
  --minutes-model gpt-4o-mini `
  --language en `
  --transcription-max-retries 2
```

On success the CLI prints:
- `manifest_path=<output-dir>\manifest.json`
- `output_dir=<output-dir>`

## Cleanup / Retention (Current Behavior)

Current default behavior:
- `normalized.wav` is kept after success.
- `chunks/` and chunk files are kept after success.
- Partial artifacts are not automatically cleaned up on failure.

Cleanup configurability:
- Not currently configurable in the CLI/pipeline.
- Future work: add explicit cleanup/retention flags (for example, keep/delete normalized audio and chunks on success/failure).

## Parity Smoke Check

See `tests/smoke/test_notebook_parity.md` for a single-input notebook-vs-CLI parity smoke procedure (artifact presence/shape checks, not text equality).

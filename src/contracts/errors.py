from __future__ import annotations


class PipelineError(Exception):
    """Raised by the pipeline entrypoint for user-facing failures."""


class ContractError(PipelineError):
    """Raised when manifest/contracts are invalid."""


class ComponentError(Exception):
    """Base exception for component-level failures."""


class InputValidationError(ComponentError):
    """Raised when an input path or config is invalid."""


class FfmpegError(ComponentError):
    """Raised when ffmpeg/ffprobe operations fail."""


class ChunkingError(ComponentError):
    """Raised when chunking fails or produces invalid outputs."""


class TranscriptionError(ComponentError):
    """Raised when transcription provider calls fail."""


class MinutesGenerationError(ComponentError):
    """Raised when minutes generation fails."""


class ExternalToolError(FfmpegError):
    """Compatibility alias for external tool failures."""


class ProviderError(TranscriptionError):
    """Compatibility alias for provider/API failures."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an unexpected response shape."""


class ProviderRetryExhaustedError(ProviderError):
    """Raised when adapter-managed provider retries are exhausted."""

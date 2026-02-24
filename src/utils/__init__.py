"""Utility package for workflow helpers and legacy ML utilities."""

from __future__ import annotations

from .hashing import sha256_file, sha256_text
from .time import Timer, now_unix_s

__all__ = [
    "sha256_file",
    "sha256_text",
    "now_unix_s",
    "Timer",
    "save_object",
    "evaluate_models",
    "load_object",
]


def save_object(*args, **kwargs):
    from .legacy import save_object as _save_object

    return _save_object(*args, **kwargs)


def evaluate_models(*args, **kwargs):
    from .legacy import evaluate_models as _evaluate_models

    return _evaluate_models(*args, **kwargs)


def load_object(*args, **kwargs):
    from .legacy import load_object as _load_object

    return _load_object(*args, **kwargs)

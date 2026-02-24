from __future__ import annotations

from src.components.minutes import DEFAULT_MINUTES_PROMPT_PATH, DEFAULT_MINUTES_PROMPT_VERSION, load_minutes_prompt


def test_default_minutes_prompt_is_versioned_and_loadable() -> None:
    loaded = load_minutes_prompt(DEFAULT_MINUTES_PROMPT_PATH)

    assert DEFAULT_MINUTES_PROMPT_VERSION == "minutes_v1"
    assert loaded.path == DEFAULT_MINUTES_PROMPT_PATH
    assert "Return Markdown only" in loaded.text
    assert "Prefer action items as a Markdown table" in loaded.text
    assert "Do not use code fences" in loaded.text

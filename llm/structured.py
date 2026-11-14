"""Ask a model for JSON that matches a Pydantic model, with one repair attempt.

The same pattern as Week 1's extractor, shared so every app gets it for free.
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .client import LLMError, complete, parse_json

T = TypeVar("T", bound=BaseModel)


class StructuredError(LLMError):
    """The model was unavailable, or its answer still didn't fit after a repair attempt."""


def ask_json(system: str, user: str, model: type[T], max_repairs: int = 1, temperature: float = 0.0) -> tuple[T, str]:
    """Returns (parsed answer, provider name)."""
    messages = [
        {"role": "system", "content": system + "\n\nReturn ONLY a JSON object matching this JSON Schema:\n"
         + json.dumps(model.model_json_schema())},
        {"role": "user", "content": user},
    ]
    for attempt in range(max_repairs + 1):
        try:
            result = complete(messages, json_mode=True, temperature=temperature)
        except LLMError as e:
            raise StructuredError(f"model unavailable: {e}") from e
        try:
            return model.model_validate(parse_json(result.text)), result.provider
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt == max_repairs:
                raise StructuredError(f"model output failed validation: {e}") from e
            messages += [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content": f"That JSON was invalid:\n{e}\nReturn corrected JSON only."},
            ]
    raise AssertionError("unreachable")

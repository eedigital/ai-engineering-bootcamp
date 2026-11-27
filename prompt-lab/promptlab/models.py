"""What a task, a test case and its expected result look like. The page sends these back with every run."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Value = bool | int | float | str  # bool first, so true stays true and doesn't become 1


class Expect(BaseModel):
    """Everything listed must hold for the case to pass. Checked in code, never by the AI."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, Value] | None = Field(
        default=None, description="The answer must be a JSON object with exactly these keys and values (strings ignore case)")
    equals: str | None = Field(default=None, max_length=2000, description="The whole answer, ignoring case and spaces")
    max_chars: int | None = Field(default=None, ge=1, le=20000)
    contains: list[str] = Field(default_factory=list, max_length=10, description="Each must appear (ignoring case)")
    not_contains: list[str] = Field(default_factory=list, max_length=10, description="None may appear (ignoring case)")


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    input: str = Field(min_length=1, max_length=4000)
    expect: Expect
    heldout: bool = Field(default=False, description="Kept out of the AI improver, to catch prompts that only fit the cases they were tuned on")
    note: str = Field(default="", max_length=200)


class Task(BaseModel):
    id: str
    name: str
    description: str
    output: Literal["json", "text"]
    cases: list[Case] = Field(min_length=1, max_length=20)
    versions: list[str] = Field(min_length=1, max_length=4, description="Starter prompts")

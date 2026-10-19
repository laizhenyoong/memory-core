"""Request models. Field names are camelCase on the wire, snake_case in Python."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from memory_agent import policy


class Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# --- principals -------------------------------------------------------------


def _check_policies(policies: list[dict] | None) -> list[dict] | None:
    for document in policies or []:
        policy.validate(document)
    return policies


class CreatePrincipalInput(Base):
    name: Annotated[str, Field(min_length=1, max_length=128)]
    policies: list[dict[str, Any]] = []
    tags: dict[str, str] = {}

    @field_validator("policies")
    @classmethod
    def check_policies(cls, value):
        return _check_policies(value)


class UpdatePrincipalInput(Base):
    name: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    policies: list[dict[str, Any]] | None = None
    tags: dict[str, str] | None = None
    disabled: bool | None = None

    @field_validator("policies")
    @classmethod
    def check_policies(cls, value):
        return _check_policies(value)

"""Request models. Field names are camelCase on the wire, snake_case in Python."""

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from memory_agent import policy

NAME_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]{0,47}$"
NAMESPACE_VARIABLES = ("{actorId}", "{sessionId}", "{memoryStrategyId}")


def _check_namespace(value: str) -> str:
    if not value.startswith("/"):
        raise ValueError("namespace must start with '/'")
    stripped = value
    for variable in NAMESPACE_VARIABLES:
        stripped = stripped.replace(variable, "")
    if "{" in stripped or "}" in stripped:
        raise ValueError(f"namespace may only use {', '.join(NAMESPACE_VARIABLES)}")
    return value if value.endswith("/") else value + "/"


Name = Annotated[str, Field(pattern=NAME_PATTERN)]
Namespace = Annotated[str, Field(max_length=1024), AfterValidator(_check_namespace)]
Namespaces = Annotated[list[Namespace], Field(min_length=1)]
Description = Annotated[str, Field(max_length=4096)]
ExpiryDays = Annotated[int, Field(ge=7, le=365)]


class Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


def _exactly_one(model: BaseModel) -> BaseModel:
    set_fields = [name for name in type(model).model_fields if getattr(model, name) is not None]
    if len(set_fields) != 1:
        options = ", ".join(to_camel(n) for n in type(model).model_fields)
        raise ValueError(f"exactly one of {options} is required")
    return model


# --- strategies -------------------------------------------------------------


class StepOverride(Base):
    append_to_prompt: Annotated[str, Field(min_length=1, max_length=30000)] | None = None
    model_id: str | None = None


class ExtractConsolidateOverride(Base):
    extraction: StepOverride | None = None
    consolidation: StepOverride | None = None


class SummaryOverride(Base):
    consolidation: StepOverride | None = None


class EpisodicOverride(ExtractConsolidateOverride):
    reflection: StepOverride | None = None


class CustomConfiguration(Base):
    semantic_override: ExtractConsolidateOverride | None = None
    user_preference_override: ExtractConsolidateOverride | None = None
    summary_override: SummaryOverride | None = None
    episodic_override: EpisodicOverride | None = None
    self_managed_configuration: dict[str, Any] | None = None

    @model_validator(mode="after")
    def check_exactly_one(self):
        return _exactly_one(self)


class StrategySpec(Base):
    name: Name
    description: Description | None = None
    namespaces: Namespaces | None = None


class ReflectionConfiguration(Base):
    namespaces: Namespaces


class EpisodicStrategySpec(StrategySpec):
    reflection_configuration: ReflectionConfiguration | None = None


class CustomStrategySpec(StrategySpec):
    configuration: CustomConfiguration


class StrategyInput(Base):
    semantic_memory_strategy: StrategySpec | None = None
    user_preference_memory_strategy: StrategySpec | None = None
    summary_memory_strategy: StrategySpec | None = None
    episodic_memory_strategy: EpisodicStrategySpec | None = None
    custom_memory_strategy: CustomStrategySpec | None = None

    @model_validator(mode="after")
    def check_exactly_one(self):
        return _exactly_one(self)

    def unwrap(self) -> tuple[str, StrategySpec]:
        for name in type(self).model_fields:
            if (spec := getattr(self, name)) is not None:
                return name, spec
        raise AssertionError("validated to have exactly one strategy")


class ModifyStrategyInput(Base):
    memory_strategy_id: str
    description: Description | None = None
    namespaces: Namespaces | None = None
    configuration: CustomConfiguration | None = None


class DeleteStrategyInput(Base):
    memory_strategy_id: str


class StrategyChanges(Base):
    add_memory_strategies: list[StrategyInput] = []
    modify_memory_strategies: list[ModifyStrategyInput] = []
    delete_memory_strategies: list[DeleteStrategyInput] = []


# --- memories ---------------------------------------------------------------


class CreateMemoryInput(Base):
    name: Name
    description: Description | None = None
    event_expiry_duration: ExpiryDays
    memory_strategies: list[StrategyInput] = []


class UpdateMemoryInput(Base):
    description: Description | None = None
    event_expiry_duration: ExpiryDays | None = None
    memory_strategies: StrategyChanges | None = None


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

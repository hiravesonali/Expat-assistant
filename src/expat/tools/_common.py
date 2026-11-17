"""Shared building blocks for all tools: the citable output base, error-as-data, and the LangChain wrapper.

Why these live in one module:
- Every tool must return `legal_basis`, `source_urls`, `rules_version` and `caveats` (docs/tools.md,
  principle 3 + 4). A common base class makes that a type-level guarantee instead of a convention.
- Bad input must come back as data (`{"error": ..., "needs": [...]}`), not as an exception, so the answer
  agent can ask the user a follow-up question (principle 5). Doing that once here keeps every tool module
  focused on its legal logic.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from expat.tools.rules import RuleMeta


class ToolOutput(BaseModel):
    """Base for every successful tool result: everything the answer needs to cite it as [T#].

    `legal_basis` and `source_urls` are lists (not single strings as sketched in docs/tools.md) because some
    tools combine several norms (Kindergeld + Elterngeld). One shape for all tools keeps the citation
    renderer trivial.
    """

    legal_basis: list[str]
    source_urls: list[str]
    rules_version: str
    caveats: list[str] = Field(default_factory=list)


class ToolError(BaseModel):
    """Structured "I can't compute this yet" result. `needs` names the missing/invalid input fields."""

    error: str
    needs: list[str] = Field(default_factory=list)
    source_url: str | None = None

    @classmethod
    def from_validation_error(cls, exc: ValidationError) -> "ToolError":
        """Turn Pydantic's error list into one sentence + the offending top-level field names."""
        needs: list[str] = []
        messages: list[str] = []
        for err in exc.errors():
            field = str(err["loc"][0]) if err["loc"] else "input"
            if field not in needs:
                needs.append(field)
            messages.append(f"{'.'.join(str(p) for p in err['loc']) or 'input'}: {err['msg']}")
        return cls(error="Invalid or missing input. " + "; ".join(messages), needs=needs)


def outside_window(rule: RuleMeta, day: date, what: str) -> ToolError:
    """Refusal used when a date falls outside a rule's validity window (docs/tools.md, principle 2).

    Answering with stale numbers is worse than not answering: the agent should tell the user to check
    the official source instead.
    """
    return ToolError(
        error=(
            f"The verified rules for {what} cover {rule.window_text()}; {day.isoformat()} is outside that window, "
            "so no reliable result can be computed. Check the official source."
        ),
        needs=[],
        source_url=rule.source_url,
    )


def _validation_error_to_content(exc: ValidationError) -> str:
    """LangChain hook: called when the model's tool arguments fail the args_schema."""
    return ToolError.from_validation_error(exc).model_dump_json()


def make_tool[InT: BaseModel](
    *,
    name: str,
    description: str,
    args_schema: type[InT],
    fn: Callable[[InT], BaseModel],
) -> BaseTool:
    """Wrap a pure `fn(input_model) -> result_model` as a LangChain tool.

    This is the "thin wrapper" from docs/tools.md. `StructuredTool.from_function(args_schema=...)` is the
    LangChain-recommended way to expose a Pydantic-typed tool; we add three things on top:
    - `handle_validation_error` turns schema errors into ToolError JSON (error-as-data, not an exception).
    - `response_format="content_and_artifact"`: the model sees compact JSON (content) while the pipeline
      gets the typed Pydantic object (artifact) for tool cards in the UI, without re-parsing.
    - We re-validate kwargs into the input model, because LangChain passes only the keys the model sent and
      we want defaults applied by Pydantic, in one place.
    """

    def _run(**kwargs: Any) -> tuple[str, BaseModel]:
        try:
            parsed = args_schema.model_validate(kwargs)
        except ValidationError as exc:  # defensive: normally caught by LangChain before we get here
            err = ToolError.from_validation_error(exc)
            return err.model_dump_json(), err
        result = fn(parsed)
        return result.model_dump_json(), result

    return StructuredTool.from_function(
        func=_run,
        name=name,
        description=description,
        args_schema=args_schema,
        response_format="content_and_artifact",
        handle_validation_error=_validation_error_to_content,
    )

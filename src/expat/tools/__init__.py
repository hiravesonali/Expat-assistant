"""Deterministic tools (pure functions + LangChain tool wrappers), see docs/tools.md.

Each module exposes a pure function (`calculate_tenancy_notice(inp) -> Result | ToolError`, unit-tested
without LangChain) and a `*_tool` object for the answer agent. `get_tools()` is the one list the agent binds.

The checklist tool is different: it needs per-request dependencies (profile, retrieval, chat model), so the
pipeline builds it with `make_checklist_tool(...)` and passes it in:

    tools = get_tools(checklist_tool=make_checklist_tool(fetch_sources, llm, profile))
"""

from langchain_core.tools import BaseTool

from expat.tools._common import ToolError, ToolOutput
from expat.tools.checklist import Checklist, ChecklistItem, build_checklist, make_checklist_tool
from expat.tools.deadlines import DeadlineInput, DeadlineResult, calculate_deadline, calculate_deadline_tool
from expat.tools.family_benefits import (
    FamilyBenefitsInput,
    FamilyBenefitsResult,
    estimate_family_benefits,
    estimate_family_benefits_tool,
)
from expat.tools.rules import Rules, load_rules
from expat.tools.schengen import SchengenInput, SchengenResult, schengen_days_calculator, schengen_days_calculator_tool
from expat.tools.tenancy_notice import (
    NoticeInput,
    NoticeResult,
    calculate_tenancy_notice,
    calculate_tenancy_notice_tool,
)


def get_tools(checklist_tool: BaseTool | None = None) -> list[BaseTool]:
    """All tools for the answer agent, in docs/tools.md priority order.

    Returns a new list each call so callers can append request-specific tools without side effects.
    """
    tools: list[BaseTool] = [
        calculate_tenancy_notice_tool,
        calculate_deadline_tool,
        estimate_family_benefits_tool,
    ]
    if checklist_tool is not None:
        tools.append(checklist_tool)
    tools.append(schengen_days_calculator_tool)
    return tools


__all__ = [
    "Checklist",
    "ChecklistItem",
    "DeadlineInput",
    "DeadlineResult",
    "FamilyBenefitsInput",
    "FamilyBenefitsResult",
    "NoticeInput",
    "NoticeResult",
    "Rules",
    "SchengenInput",
    "SchengenResult",
    "ToolError",
    "ToolOutput",
    "build_checklist",
    "calculate_deadline",
    "calculate_tenancy_notice",
    "estimate_family_benefits",
    "get_tools",
    "load_rules",
    "make_checklist_tool",
    "schengen_days_calculator",
]

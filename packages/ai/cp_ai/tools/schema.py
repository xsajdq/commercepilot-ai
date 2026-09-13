import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cp_ai.tools.context import ToolContext
from cp_ai.tools.result import ToolResult


class ToolRiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ToolHandler = Callable[[BaseModel, ToolContext, AsyncSession], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolPermission:
    """What it takes to run a tool - CLAUDE.md #4: "Medium/high-risk
    actions require human approval." `mutates` is tracked separately from
    `risk_level` because it decides whether a successful run gets an
    audit log (#5: "every mutation must create an audit log") - a
    high-risk *read* (e.g. one that surfaces sensitive data) needs
    approval but isn't a mutation to audit; a low-risk write is a
    mutation that still needs a paper trail even though it can run
    immediately.
    """

    risk_level: ToolRiskLevel
    mutates: bool

    @property
    def requires_approval(self) -> bool:
        return self.risk_level is not ToolRiskLevel.LOW


@dataclass(frozen=True)
class ToolSchema:
    """One AI-callable tool.

    `args_model` is the Pydantic model a tool call's arguments are
    validated against before anything else happens - it must never
    declare a `tenant_id` field (enforced by `ToolRegistry.register`),
    since that always comes from `ToolContext` instead. `handler` is
    only ever invoked by `ToolExecutor` once validation, the (Phase 8)
    policy engine, and the risk/approval gate have all cleared - a tool
    author never has to re-check any of that inside `handler` itself.
    """

    name: str
    description: str
    args_model: type[BaseModel]
    permission: ToolPermission
    handler: ToolHandler

    def input_schema(self) -> dict:
        """JSON schema for `args_model` - the shape an `AIProvider`'s
        tool-use API expects to advertise this tool to a model."""
        return self.args_model.model_json_schema()

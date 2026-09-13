from cp_ai.tools.schema import ToolSchema


class DuplicateToolError(Exception):
    pass


class ToolNotFoundError(Exception):
    pass


class UnsafeToolSchemaError(Exception):
    """A tool's `args_model` declares a `tenant_id` field. Refused at
    registration time, not at call time: tenant_id must always come from
    `ToolContext` (the authenticated caller), never from a tool argument
    the AI - possibly echoing attacker-influenced external content per
    CLAUDE.md #18 - could set (#7: never trust tenant_id from client
    input)."""


class ToolRegistry:
    """Where every AI-callable tool is registered. An agent runtime
    never calls a handler directly - it goes through `ToolExecutor`,
    which resolves tools by name through this registry."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSchema] = {}

    def register(self, tool: ToolSchema) -> None:
        if "tenant_id" in tool.args_model.model_fields:
            raise UnsafeToolSchemaError(
                f"Tool {tool.name!r}'s args_model declares a tenant_id field - "
                "tenant_id must come from ToolContext, never from a tool argument."
            )
        if tool.name in self._tools:
            raise DuplicateToolError(f"Tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSchema:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"No tool registered as {name!r}") from None

    def list_tools(self) -> list[ToolSchema]:
        return list(self._tools.values())

    def tool_definitions(self) -> list[dict]:
        """Tool definitions in the name/description/input_schema shape
        an `AIProvider`'s tool-use API expects."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema()}
            for t in self._tools.values()
        ]

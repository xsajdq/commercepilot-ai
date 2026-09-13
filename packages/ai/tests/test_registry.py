import pytest
from pydantic import BaseModel

from cp_ai.tools import (
    DuplicateToolError,
    ToolNotFoundError,
    ToolPermission,
    ToolRegistry,
    ToolRiskLevel,
    ToolSchema,
    UnsafeToolSchemaError,
)


class _NoopArgs(BaseModel):
    value: int = 0


class _TenantLeakArgs(BaseModel):
    tenant_id: str


async def _noop_handler(args, context, db):
    raise AssertionError("handler should never be called by these tests")


def _tool(name: str = "noop", *, args_model=_NoopArgs, risk=ToolRiskLevel.LOW, mutates=False):
    return ToolSchema(
        name=name,
        description="A no-op test tool.",
        args_model=args_model,
        permission=ToolPermission(risk_level=risk, mutates=mutates),
        handler=_noop_handler,
    )


def test_register_and_get() -> None:
    registry = ToolRegistry()
    tool = _tool()
    registry.register(tool)

    assert registry.get("noop") is tool


def test_get_unknown_tool_raises() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("does_not_exist")


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()
    registry.register(_tool())
    with pytest.raises(DuplicateToolError):
        registry.register(_tool())


def test_args_model_declaring_tenant_id_is_refused() -> None:
    registry = ToolRegistry()
    with pytest.raises(UnsafeToolSchemaError):
        registry.register(_tool(args_model=_TenantLeakArgs))


def test_list_tools_returns_registered_schemas() -> None:
    registry = ToolRegistry()
    tool = _tool()
    registry.register(tool)

    assert registry.list_tools() == [tool]


def test_tool_definitions_shape() -> None:
    registry = ToolRegistry()
    registry.register(_tool())

    [definition] = registry.tool_definitions()

    assert definition["name"] == "noop"
    assert definition["description"] == "A no-op test tool."
    assert definition["input_schema"] == _NoopArgs.model_json_schema()

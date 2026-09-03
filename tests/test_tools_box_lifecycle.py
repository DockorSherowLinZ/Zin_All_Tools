"""Tools Box 嵌入式子工具的生命週期驗證。

子工具由 Tools Box 直接實例化，Kit 不會替它們呼叫 on_shutdown。
若啟動時建立了事件訂閱或執行緒卻沒有對應的關閉呼叫，
這些資源會殘留在 Kit 中持續觸發，即使模組已重載。
"""

import ast
import os

import pytest

TOOLS_BOX_EXTENSION = os.path.join(
    "exts", "tools_box", "tools_box", "extension.py"
)

# on_startup 期間會取得外部資源的子工具，關閉時必須明確釋放
SHUTDOWN_REQUIRED = (
    "tool_explode",
    "tool_dashboard",
    "tool_conveyor",
    "tool_physics",
)


def _load_method(name):
    with open(TOOLS_BOX_EXTENSION, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=TOOLS_BOX_EXTENSION)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{TOOLS_BOX_EXTENSION} 找不到 {name}()")


def _attributes_receiving_call(method_node, call_name):
    """找出所有被呼叫 call_name 的 self.<attr>。"""
    found = set()
    for node in ast.walk(method_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != call_name:
            continue
        target = func.value
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            found.add(target.attr)
    return found


@pytest.mark.parametrize("tool_attr", SHUTDOWN_REQUIRED)
def test_started_subtool_is_shut_down(tool_attr):
    """on_startup 呼叫過 on_startup 的子工具，on_shutdown 必須呼叫其 on_shutdown。"""
    startup = _load_method("on_startup")
    started = _attributes_receiving_call(startup, "on_startup")
    if tool_attr not in started:
        pytest.skip(f"{tool_attr} 未在 on_startup 中啟動")

    shutdown = _load_method("on_shutdown")
    stopped = _attributes_receiving_call(shutdown, "on_shutdown")

    assert tool_attr in stopped, (
        f"self.{tool_attr} 在 on_startup 被啟動，但 on_shutdown 沒有呼叫它的 "
        f"on_shutdown()，其訂閱或執行緒會殘留在 Kit 中"
    )

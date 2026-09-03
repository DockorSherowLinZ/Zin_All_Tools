"""非同步任務生命週期驗證。

未保留 handle 的 `asyncio.ensure_future(...)` 無法在 extension 關閉時取消，
coroutine 可能在 UI 已銷毀後才恢復執行並存取失效物件。
"""

import ast
import glob
import os

import pytest

EXTS_ROOT = "exts"

# zin_core.tasks 是註冊表本身的實作，允許直接使用 asyncio；
# model.py 的 metadata 讀取綁定於單一 asset 物件，無 extension 級生命週期可依附。
ALLOWED_RAW_ASYNCIO = {
    os.path.join("exts", "tw.zin.core", "zin_core", "tasks.py"),
    os.path.join("exts", "tw.zin.smart_assets_library", "smart_assets_library", "model.py"),
}


def get_extension_sources():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True))


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_async_tasks_are_tracked(source_path):
    """背景任務必須透過 ZinTaskRegistry 建立，才能於關閉時統一取消。"""
    if os.path.normpath(source_path) in {os.path.normpath(p) for p in ALLOWED_RAW_ASYNCIO}:
        pytest.skip("task registry implementation")

    with open(source_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=source_path)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("ensure_future", "create_task"):
            continue
        target = node.func.value
        if isinstance(target, ast.Name) and target.id == "asyncio":
            offenders.append(f"L{node.lineno}")

    assert not offenders, (
        f"{source_path} 直接建立未追蹤的背景任務"
        f"（請改用 zin_core.tasks.ZinTaskRegistry.spawn）：{offenders}"
    )

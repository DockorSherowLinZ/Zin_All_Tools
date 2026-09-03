"""UI 字串可顯示性驗證。

Kit 的預設 UI 字型不含中日韓字元，這類字串在介面上會全部變成問號。
Docstring 與註解不受影響，只有實際傳給 omni.ui 的字串需要限制。
"""

import ast
import glob
import re

import pytest

EXTS_ROOT = "exts"

CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u3000-\u303f\uff00-\uffef]")


def get_extension_sources():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True))


def _docstring_node_ids(tree):
    """收集 docstring 節點，這些不會顯示在 UI 上。"""
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            ids.add(id(first.value))
    return ids


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_no_cjk_in_ui_strings(source_path):
    """傳給 omni.ui 的字串不得含中日韓字元，否則介面會顯示問號。"""
    with open(source_path, encoding="utf-8") as handle:
        source = handle.read()

    tree = ast.parse(source, filename=source_path)
    docstrings = _docstring_node_ids(tree)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        is_ui_call = isinstance(func, ast.Attribute) and (
            (isinstance(func.value, ast.Name) and func.value.id == "ui")
            or name.startswith("build_")
        )
        if not is_ui_call:
            continue

        literals = list(node.args) + [keyword.value for keyword in node.keywords]
        for literal in literals:
            if (
                isinstance(literal, ast.Constant)
                and isinstance(literal.value, str)
                and id(literal) not in docstrings
                and CJK_PATTERN.search(literal.value)
            ):
                offenders.append(f"L{literal.lineno}: {literal.value[:40]}")

    assert not offenders, (
        f"{source_path} 傳給 UI 的字串含中日韓字元，Kit 字型無法顯示："
        f"{offenders}"
    )

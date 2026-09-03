"""程式碼品質守則。

Omniverse extension 在 Kit 中執行時，開發者只能透過 Console 診斷問題。
因此本檔守護兩項關鍵可觀測性要求：
  1. 使用 carb 分級日誌而非 print
  2. 不以裸 except 或靜默 pass 吞掉例外
"""

import ast
import glob
import os

import pytest

EXTS_ROOT = "exts"


def get_extension_sources():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True))


def _iter_source_trees():
    for path in get_extension_sources():
        with open(path, encoding="utf-8") as handle:
            yield path, ast.parse(handle.read(), filename=path)


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_no_print_calls(source_path):
    """extension 應使用 carb.log_* 而非 print。

    print 無法分級過濾，且非 ASCII 內容在部分 Windows console 編碼下會拋錯。
    """
    with open(source_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=source_path)

    offenders = [
        f"L{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert not offenders, (
        f"{source_path} 使用 print（請改用 carb.log_info/warn/error）：{offenders}"
    )


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_no_bare_except(source_path):
    """不得使用裸 except，否則會連 KeyboardInterrupt / SystemExit 一併吞掉。"""
    with open(source_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=source_path)

    offenders = [
        f"L{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is None
    ]
    assert not offenders, (
        f"{source_path} 使用裸 except（請改為 except Exception）：{offenders}"
    )


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_no_silently_swallowed_exceptions(source_path):
    """except 區塊不得只有 pass。

    若確實需要忽略，請保留一行註解說明原因，讓意圖可被審閱。
    """
    with open(source_path, encoding="utf-8") as handle:
        source = handle.read()
    lines = source.splitlines()
    tree = ast.parse(source, filename=source_path)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) != 1 or not isinstance(node.body[0], ast.Pass):
            continue
        # 允許以註解明確標示「刻意忽略」
        pass_line = node.body[0].lineno
        preceding = lines[node.lineno - 1 : pass_line - 1]
        if any(line.strip().startswith("#") for line in preceding):
            continue
        offenders.append(f"L{node.lineno}")

    assert not offenders, (
        f"{source_path} 靜默吞掉例外（請記錄 carb 日誌或加註說明）：{offenders}"
    )

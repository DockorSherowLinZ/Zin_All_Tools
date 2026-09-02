"""擴充套件結構驗證 — 不需 Omniverse 環境即可執行。

守護 Kit extension 掃描的基本前提：
  1. exts/ 下每個目錄都是合法 extension（具備 config/extension.toml）
  2. 不殘留 __pycache__ 或編譯產物
  3. extension package 內不含 module-level 直接執行的開發腳本
"""

import ast
import glob
import os

import pytest

EXTS_ROOT = "exts"


def get_extension_dirs():
    if not os.path.isdir(EXTS_ROOT):
        return []
    return sorted(
        os.path.join(EXTS_ROOT, name)
        for name in os.listdir(EXTS_ROOT)
        if os.path.isdir(os.path.join(EXTS_ROOT, name))
    )


def get_extension_sources():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True))


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_extension_module_parses(source_path):
    """每個 extension 模組都必須能被正確解析。

    使用 AST 而非 compileall，避免產生 __pycache__ 产物。
    """
    with open(source_path, encoding="utf-8") as handle:
        source = handle.read()
    try:
        ast.parse(source, filename=source_path)
    except SyntaxError as exc:
        pytest.fail(f"{source_path} 語法錯誤：{exc}")


@pytest.mark.parametrize("ext_dir", get_extension_dirs())
def test_extension_has_manifest(ext_dir):
    """exts/ 下的每個目錄都必須是合法 extension。

    無 manifest 的目錄會被 Kit 視為無效項目，且其 python package
    可能透過 sys.path 遮蔽同名的正式模組。
    """
    manifest = os.path.join(ext_dir, "config", "extension.toml")
    assert os.path.isfile(manifest), (
        f"{ext_dir} 缺少 config/extension.toml，"
        f"請刪除此目錄或補上 manifest"
    )


def test_no_pycache_committed():
    """確認沒有 __pycache__ 目錄被納入版控範圍"""
    caches = glob.glob(f"{EXTS_ROOT}/**/__pycache__", recursive=True)
    assert not caches, f"發現 __pycache__ 殘留（請刪除）：{caches}"


def test_no_compiled_python_in_exts():
    """確認 exts/ 下沒有 .pyc 編譯產物"""
    compiled = glob.glob(f"{EXTS_ROOT}/**/*.pyc", recursive=True)
    assert not compiled, f"發現 .pyc 編譯產物（請刪除）：{compiled}"


def test_no_dev_scripts_in_extension_packages():
    """開發用診斷腳本不得放在 extension package 內。

    這類腳本多為 module-level 直接執行，被 import 時會產生副作用。
    """
    forbidden_prefixes = ("inspect_", "diag_", "test_")
    offenders = []
    for path in glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True):
        name = os.path.basename(path)
        if name.startswith(forbidden_prefixes):
            offenders.append(path)
    assert not offenders, (
        f"extension package 內含開發腳本（請移至 tools/dev_scripts/）：{offenders}"
    )

"""擴充套件 manifest 與設定驗證。

守護 Kit Extensions 面板的顯示正確性與可攜性：
  1. extension.toml 必須是合法 TOML（重複鍵會導致解析失敗）
  2. manifest 參照的檔案必須實際存在
  3. 程式碼不得含有機器專屬的絕對路徑
"""

import ast
import glob
import os
import re
import tomllib

import pytest

EXTS_ROOT = "exts"

# manifest 中會指向實體檔案的欄位
FILE_REFERENCE_KEYS = ("readme", "changelog", "preview_image", "icon")

ABSOLUTE_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


def get_all_manifests():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/extension.toml", recursive=True))


def get_extension_sources():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True))


@pytest.mark.parametrize("manifest_path", get_all_manifests())
def test_manifest_is_valid_toml(manifest_path):
    """extension.toml 必須通過嚴格 TOML 解析。

    重複鍵（例如宣告兩次 readme）在 TOML 規範中屬於錯誤。
    """
    with open(manifest_path, "rb") as handle:
        try:
            tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            pytest.fail(f"{manifest_path} 不是合法 TOML：{exc}")


@pytest.mark.parametrize("manifest_path", get_all_manifests())
def test_manifest_file_references_exist(manifest_path):
    """manifest 參照的 readme/changelog/icon/preview 必須存在。

    指向不存在的檔案會讓 Omniverse Extensions 面板顯示破圖或空白說明。
    """
    ext_root = os.path.dirname(os.path.dirname(manifest_path))
    with open(manifest_path, "rb") as handle:
        package = tomllib.load(handle).get("package", {})

    missing = []
    for key in FILE_REFERENCE_KEYS:
        value = package.get(key)
        if not value:
            continue
        if not os.path.isfile(os.path.join(ext_root, value)):
            missing.append(f"{key} = {value}")

    assert not missing, (
        f"{manifest_path} 參照了不存在的檔案：{missing}"
        f"（請補上檔案或移除該欄位）"
    )


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_no_machine_specific_absolute_paths(source_path):
    """extension 程式碼不得寫死本機絕對路徑，應改用 carb.settings。

    只檢查實際的字串字面值，避免誤判註解與文件中的路徑範例。
    """
    with open(source_path, encoding="utf-8") as handle:
        source = handle.read()

    tree = ast.parse(source, filename=source_path)
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    offenders = [
        f"L{node.lineno}: {node.value}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node not in docstrings
        and ABSOLUTE_PATH_PATTERN.match(node.value)
    ]
    assert not offenders, (
        f"{source_path} 含硬編碼絕對路徑（請改用 carb.settings）：{offenders}"
    )

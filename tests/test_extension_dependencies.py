"""跨 extension 相依性驗證。

Kit 以 extension.toml 的 [dependencies] 決定載入順序。
若用 sys.path 手動取得他人模組，載入順序無法保證，
且可能被同名目錄遮蔽。
"""

import ast
import glob
import os
import tomllib

import pytest

EXTS_ROOT = "exts"

# python 模組名 -> 提供該模組的 extension id
MODULE_TO_EXTENSION = {}


def _build_module_index():
    if MODULE_TO_EXTENSION:
        return MODULE_TO_EXTENSION
    for manifest_path in glob.glob(f"{EXTS_ROOT}/**/extension.toml", recursive=True):
        ext_id = os.path.basename(os.path.dirname(os.path.dirname(manifest_path)))
        with open(manifest_path, "rb") as handle:
            data = tomllib.load(handle)
        for entry in data.get("python", {}).get("module", []) or []:
            name = entry.get("name")
            if name:
                MODULE_TO_EXTENSION[name] = ext_id
    return MODULE_TO_EXTENSION


def get_extension_sources():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/*.py", recursive=True))


def get_all_manifests():
    return sorted(glob.glob(f"{EXTS_ROOT}/**/extension.toml", recursive=True))


@pytest.mark.parametrize("source_path", get_extension_sources())
def test_no_sys_path_manipulation(source_path):
    """extension 不得以 sys.path 取得其他 extension 的模組。

    應改為在 extension.toml 宣告依賴，由 Kit 保證載入順序。
    """
    with open(source_path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=source_path)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in ("append", "insert"):
            continue
        target = func.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "path"
            and isinstance(target.value, ast.Name)
            and target.value.id == "sys"
        ):
            offenders.append(f"L{node.lineno}")

    assert not offenders, (
        f"{source_path} 使用 sys.path 操作（請改用 extension.toml 依賴宣告）：{offenders}"
    )


@pytest.mark.parametrize("manifest_path", get_all_manifests())
def test_cross_extension_imports_are_declared(manifest_path):
    """跨 extension 匯入的模組，必須在 manifest 宣告對應依賴。"""
    module_index = _build_module_index()
    ext_root = os.path.dirname(os.path.dirname(manifest_path))
    ext_id = os.path.basename(ext_root)

    with open(manifest_path, "rb") as handle:
        declared = set(tomllib.load(handle).get("dependencies", {}))

    missing = set()
    for source_path in glob.glob(f"{ext_root}/**/*.py", recursive=True):
        with open(source_path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=source_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            else:
                continue
            for root in roots:
                provider = module_index.get(root)
                if provider and provider != ext_id and provider not in declared:
                    missing.add(f"{root} (由 {provider} 提供)")

    assert not missing, (
        f"{manifest_path} 未宣告以下跨 extension 依賴：{sorted(missing)}"
    )

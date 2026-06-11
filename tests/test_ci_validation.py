"""
CI 驗證測試套件 — 不需要 Omniverse 環境即可執行
測試目標：
  1. 所有 extension.toml 版本號不是佔位符
  2. 所有 repository URL 已正確填寫
  3. 沒有備份檔殘留
  4. DEBUG flag 已完全清除
"""

import glob
import os
import pytest


def get_all_tomls():
    """取得所有 extension.toml 路徑"""
    return sorted(glob.glob("exts/**/extension.toml", recursive=True))


# ─────────────────────────────────────────
# extension.toml 版本號驗證
# ─────────────────────────────────────────

@pytest.mark.parametrize("toml_path", get_all_tomls())
def test_version_not_placeholder(toml_path):
    """確認 extension.toml 版本號不是預設佔位符 0.1.0"""
    content = open(toml_path, encoding="utf-8").read()
    assert 'version = "0.1.0"' not in content, (
        f"{toml_path} 的版本號仍是佔位符 0.1.0，請更新為實際版本"
    )


@pytest.mark.parametrize("toml_path", get_all_tomls())
def test_repository_url_filled(toml_path):
    """確認 extension.toml 的 repository URL 不含佔位符"""
    content = open(toml_path, encoding="utf-8").read()
    assert "<YOUR_GITHUB>" not in content, (
        f"{toml_path} 的 repository URL 仍有 <YOUR_GITHUB> 佔位符"
    )
    assert 'repository = ""' not in content, (
        f"{toml_path} 的 repository URL 為空字串"
    )


# ─────────────────────────────────────────
# 備份檔清理驗證
# ─────────────────────────────────────────

def test_no_bak_files():
    """確認沒有 .bak 備份檔殘留"""
    bak_files = glob.glob("exts/**/*.bak", recursive=True)
    assert not bak_files, f"發現 .bak 備份檔（請刪除）：{bak_files}"


def test_no_alone_files():
    """確認沒有 _alone.py 備份檔殘留"""
    alone = [
        f for f in glob.glob("exts/**/*.py", recursive=True)
        if "_alone" in os.path.basename(f)
    ]
    assert not alone, f"發現 _alone.py 備份檔（請刪除）：{alone}"


def test_no_backup_py_files():
    """確認沒有 _backup.py 備份檔殘留"""
    backup = [
        f for f in glob.glob("exts/**/*.py", recursive=True)
        if "_backup" in os.path.basename(f)
    ]
    assert not backup, f"發現 _backup.py 備份檔（請刪除）：{backup}"


# ─────────────────────────────────────────
# DEBUG flag 驗證
# ─────────────────────────────────────────

def test_no_debug_flag_in_tools_box():
    """確認 tools_box/extension.py 中不存在 DEBUG_DISABLE_ALL_TOOLS"""
    target = "exts/tools_box/tools_box/extension.py"
    content = open(target, encoding="utf-8").read()
    assert "DEBUG_DISABLE_ALL_TOOLS" not in content, (
        f"{target} 仍有 DEBUG_DISABLE_ALL_TOOLS flag，請移除"
    )


def test_tools_box_loads_all_tools():
    """確認 tools_box 仍保有所有子工具的載入程式碼"""
    target = "exts/tools_box/tools_box/extension.py"
    content = open(target, encoding="utf-8").read()
    required_tools = [
        "SmartAlignExtension",
        "SmartAssetsBuilderExtension",
        "SmartMeasureExtension",
        "SmartReferenceExtension",
        "SmartAssemblyExtension",
        "SmartPhysicsSetupExtension",
    ]
    for tool in required_tools:
        assert tool in content, (
            f"tools_box extension.py 缺少 {tool}，可能被誤刪"
        )


# ─────────────────────────────────────────
# .gitignore 驗證
# ─────────────────────────────────────────

def test_gitignore_exists():
    """確認 .gitignore 存在"""
    assert os.path.exists(".gitignore"), ".gitignore 不存在，請建立"


def test_gitignore_has_key_rules():
    """確認 .gitignore 包含關鍵排除規則"""
    content = open(".gitignore").read()
    required_rules = ["*.bak", "__pycache__/", "*.pyc"]
    for rule in required_rules:
        assert rule in content, f".gitignore 缺少規則：{rule}"

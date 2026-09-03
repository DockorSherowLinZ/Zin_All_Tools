"""本機測試執行器 — 供無法安裝 pytest 的環境使用。

公司 proxy 需要 NTLM 驗證，pip 無法通過，因此本機無法安裝 pytest。
本腳本以最小的 pytest 相容層執行 tests/ 下的測試，
讓開發者在推送前仍能驗證。GitHub Actions 上跑的是真正的 pytest。

用法：
    .venv/Scripts/python.exe tools/run_tests.py
"""

import glob
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FailedExpectation(AssertionError):
    pass


class _SkippedTest(Exception):
    pass


def _install_pytest_stub():
    class _Mark:
        def parametrize(self, argnames, argvalues, **kwargs):
            def decorator(func):
                func._zin_params = list(argvalues)
                return func

            return decorator

    stub = types.ModuleType("pytest")
    stub.mark = _Mark()
    stub.fail = lambda msg="": (_ for _ in ()).throw(_FailedExpectation(msg))
    stub.skip = lambda msg="": (_ for _ in ()).throw(_SkippedTest(msg))
    sys.modules["pytest"] = stub


def main():
    os.chdir(REPO_ROOT)
    sys.path.insert(0, REPO_ROOT)
    _install_pytest_stub()

    modules = [
        os.path.splitext(os.path.basename(path))[0]
        for path in sorted(glob.glob("tests/test_*.py"))
    ]

    total = passed = skipped = 0
    failures = []

    for module_name in modules:
        module = __import__(f"tests.{module_name}", fromlist=["*"])
        for name in sorted(vars(module)):
            func = vars(module)[name]
            if not (name.startswith("test_") and callable(func)):
                continue
            params = getattr(func, "_zin_params", None)
            invocations = [()] if params is None else [(value,) for value in params]
            for args in invocations:
                total += 1
                try:
                    func(*args)
                    passed += 1
                except _SkippedTest:
                    skipped += 1
                except Exception as exc:  # noqa: BLE001 - 測試執行器需捕捉全部失敗
                    label = f"{module_name}::{name}"
                    if args:
                        label += f"[{args[0]}]"
                    failures.append((label, f"{type(exc).__name__}: {exc}"))

    for label, reason in failures:
        print(f"FAIL {label}\n     {reason}")

    print(
        f"\nmodules={len(modules)} total={total} passed={passed} "
        f"skipped={skipped} failed={len(failures)}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

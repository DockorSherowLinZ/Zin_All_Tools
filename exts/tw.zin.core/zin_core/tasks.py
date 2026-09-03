"""非同步任務生命週期管理。

先前各 extension 直接呼叫 `asyncio.ensure_future(...)` 而不保留 handle，
導致 extension 關閉後 coroutine 仍可能存取已銷毀的 UI 物件。
本模組提供可追蹤、可一次取消的任務註冊表。
"""

import asyncio

import carb


class ZinTaskRegistry:
    """追蹤 extension 建立的 asyncio 任務，並支援統一取消。

    任務完成後會自動從註冊表移除，因此長時間執行不會累積 handle。
    """

    def __init__(self, owner_name="Zin"):
        self._owner_name = owner_name
        self._tasks = set()

    def spawn(self, coro):
        """啟動 coroutine 並納入追蹤，回傳對應的 task。"""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task):
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            carb.log_error(f"[{self._owner_name}] Background task failed: {error}")

    def cancel_all(self):
        """取消所有仍在執行的任務。應於 shutdown 或 UI 隱藏時呼叫。"""
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        self._tasks.clear()

    @property
    def active_count(self):
        return sum(1 for task in self._tasks if not task.done())

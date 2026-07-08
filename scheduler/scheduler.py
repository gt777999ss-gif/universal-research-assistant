from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List

from monitoring.store import enabled_due_monitors


MonitorRunner = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class MonitorScheduler:
    def __init__(self, runner: MonitorRunner, interval_seconds: int = 300) -> None:
        self.runner = runner
        self.interval_seconds = interval_seconds
        self.running = False
        self.last_warnings: List[str] = []

    async def run_due_once(self) -> List[Dict[str, Any]]:
        outputs: List[Dict[str, Any]] = []
        for monitor in enabled_due_monitors():
            try:
                outputs.append(await self.runner(monitor))
            except Exception as exc:
                self.last_warnings.append(f"Monitor {monitor.get('id', 'unknown')} failed: {exc}")
        return outputs

    async def loop_forever(self) -> None:
        self.running = True
        while self.running:
            await self.run_due_once()
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self.running = False

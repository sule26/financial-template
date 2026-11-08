"""Background sync: single-consumer job queue, periodic scan and watchdog (docs/05 "Gatilhos")."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from expense_tracker.services.errors import new_id
from expense_tracker.sync.engine import SyncEngine

log = logging.getLogger("expense_tracker.sync")


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error
    created_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class SyncService:
    engine: SyncEngine
    interval: float
    enable_watcher: bool = True
    debounce: float = 3.0
    jobs: dict[str, Job] = field(default_factory=dict)
    _queue: asyncio.Queue[tuple[Job, Callable[[], Any]]] | None = None
    _tasks: list[asyncio.Task[None]] = field(default_factory=list)
    _observer: Any = None
    _loop: asyncio.AbstractEventLoop | None = None
    _pending_scan: asyncio.TimerHandle | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def submit(self, kind: str, fn: Callable[[], Any]) -> Job:
        job = Job(new_id("job"), kind, created_at=self.engine.clock.now())
        self.jobs[job.id] = job
        if len(self.jobs) > 200:
            for old in list(self.jobs)[:-200]:
                self.jobs.pop(old, None)
        if self._queue is None:
            self._run(job, fn)  # no loop (tests/CLI): run inline
        else:
            self._queue.put_nowait((job, fn))
        return job

    def run_now(self, kind: str, fn: Callable[[], Any]) -> Job:
        """Run synchronously, serialized with the queue (used by API actions)."""
        job = Job(new_id("job"), kind, created_at=self.engine.clock.now())
        self.jobs[job.id] = job
        self._run(job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[], Any]) -> None:
        job.status = "running"
        with self._lock:
            try:
                result = fn()
                job.result = (
                    result.as_dict()
                    if hasattr(result, "as_dict")
                    else (
                        result.model_dump(mode="json") if hasattr(result, "model_dump") else result
                    )
                )
                job.status = "done"
            except Exception as exc:
                # docs/13: never log values; the type is enough, details go to the job
                log.error("sync job %s failed: %s", job.kind, type(exc).__name__)
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
        job.finished_at = self.engine.clock.now()

    def scan(self) -> Job:
        return self.submit("scan", self.engine.scan)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> SyncService:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._tasks.append(asyncio.create_task(self._worker()))
        self._tasks.append(asyncio.create_task(self._periodic()))
        if self.enable_watcher:
            self._start_watcher()
        return self

    async def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(2)
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks.clear()

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            job, fn = await self._queue.get()
            await asyncio.to_thread(self._run, job, fn)
            self._queue.task_done()

    async def _periodic(self) -> None:
        while True:
            self.scan()  # startup scan first (docs/05), then every interval
            await asyncio.sleep(self.interval)

    def _start_watcher(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:  # pragma: no cover
            return
        service = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event: Any) -> None:
                if service._loop is not None:
                    service._loop.call_soon_threadsafe(service._debounced_scan)

        root = self.engine.settings.inbox_dir
        if not root.is_dir():
            return
        observer = Observer()
        observer.schedule(Handler(), str(root), recursive=True)
        observer.daemon = True
        try:
            observer.start()
        except OSError as exc:  # pragma: no cover - e.g. inotify limits
            log.warning("watcher not started: %s", exc)
            return
        self._observer = observer

    def _debounced_scan(self) -> None:
        """Watchdog events only trigger a scan, debounced (docs/05)."""
        if self._loop is None:
            return
        if self._pending_scan is not None:
            self._pending_scan.cancel()
        self._pending_scan = self._loop.call_later(self.debounce, self.scan)

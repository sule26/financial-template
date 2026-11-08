"""Sync triggers and the single-consumer job queue (docs/05 "Gatilhos", "Fila única"; R3.8)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from sync_env import Env, inter, make_env

from expense_tracker.sync.service import Job, SyncService

INV = "faturas/inter/2026-10.pdf"


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


async def _wait(cond, timeout: float = 15.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


# ---------------------------------------------------------------- without a loop


def test_r3_8_manual_scan_without_loop_runs_inline(env: Env) -> None:
    env.put(INV, inter((1, "MERCADO A", "10.00")))
    svc = SyncService(env.engine, interval=3600, enable_watcher=False)
    job = svc.scan()
    assert job.status == "done" and job.kind == "scan"
    assert job.result["new"] == [INV]
    assert svc.jobs[job.id] is job
    assert job.created_at == env.clock.now() and job.finished_at == env.clock.now()
    d = job.as_dict()
    assert d["id"] == job.id and d["status"] == "done" and d["error"] is None
    assert d["created_at"] == env.clock.now().isoformat()


def test_r3_8_job_error_is_captured(env: Env) -> None:
    svc = SyncService(env.engine, interval=3600, enable_watcher=False)

    def boom() -> None:
        raise RuntimeError("falhou")

    job = svc.submit("reprocess", boom)
    assert job.status == "error"
    assert job.error == "RuntimeError: falhou"
    assert job.as_dict()["error"] == "RuntimeError: falhou"


def test_r3_8_job_results_are_serialized(env: Env) -> None:
    env.put(INV, inter((1, "MERCADO A", "10.00")))
    svc = SyncService(env.engine, interval=3600, enable_watcher=False)
    svc.scan()
    job = svc.run_now("reprocess", lambda: env.engine.reprocess_failed())
    assert job.status == "done" and job.result == []
    job = svc.run_now("entry", lambda: env.entry(INV))
    assert job.result["path"] == INV and job.result["status"] == "pending_review"


def test_r3_8_only_last_200_jobs_are_kept(env: Env) -> None:
    svc = SyncService(env.engine, interval=3600, enable_watcher=False)
    jobs = [svc.submit("noop", lambda: None) for _ in range(205)]
    assert len(svc.jobs) == 200
    assert jobs[0].id not in svc.jobs and jobs[-1].id in svc.jobs


def test_job_as_dict_without_timestamps() -> None:
    d = Job("job_1", "scan").as_dict()
    assert d == {
        "id": "job_1",
        "kind": "scan",
        "status": "queued",
        "created_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }


def test_r3_8_debounce_without_loop_is_noop(env: Env) -> None:
    svc = SyncService(env.engine, interval=3600, enable_watcher=False)
    svc._debounced_scan()
    assert svc._pending_scan is None and svc.jobs == {}


# ---------------------------------------------------------------- with a loop


async def test_r3_8_start_runs_startup_scan_and_stop_cancels(env: Env) -> None:
    env.put(INV, inter((1, "MERCADO A", "10.00")))
    svc = SyncService(env.engine, interval=3600, enable_watcher=False)
    await svc.start()
    try:
        await _wait(lambda: any(j.status == "done" for j in svc.jobs.values()))
        (job,) = svc.jobs.values()
        assert job.kind == "scan" and job.result["new"] == [INV]
        assert env.entry(INV).status == "pending_review"
        # with the loop running, submit() queues instead of running inline
        queued = svc.submit("noop", lambda: 42)
        await _wait(lambda: queued.status == "done")
        assert queued.result == 42
    finally:
        await svc.stop()
    assert svc._tasks == []


async def test_r3_8_periodic_scan_repeats(env: Env) -> None:
    svc = SyncService(env.engine, interval=0.05, enable_watcher=False)
    await svc.start()
    try:
        await _wait(lambda: sum(j.status == "done" for j in svc.jobs.values()) >= 3)
    finally:
        await svc.stop()


async def test_r3_8_watch_events_are_debounced_into_one_scan(env: Env) -> None:
    svc = SyncService(env.engine, interval=3600, enable_watcher=False, debounce=0.05)
    await svc.start()
    try:
        await _wait(lambda: len(svc.jobs) == 1 and next(iter(svc.jobs.values())).status == "done")
        env.put(INV, inter((1, "MERCADO A", "10.00")))
        for _ in range(5):
            svc._debounced_scan()
        assert svc._pending_scan is not None
        await _wait(
            lambda: len(svc.jobs) == 2 and all(j.status == "done" for j in svc.jobs.values())
        )
        await asyncio.sleep(0.15)
        assert len(svc.jobs) == 2  # five events, one scan
        assert env.entry(INV).active
    finally:
        await svc.stop()


async def test_r3_8_watchdog_event_triggers_scan(env: Env) -> None:
    svc = SyncService(env.engine, interval=3600, enable_watcher=True, debounce=0.05)
    await svc.start()
    try:
        assert svc._observer is not None
        await _wait(lambda: len(svc.jobs) == 1 and next(iter(svc.jobs.values())).status == "done")
        env.put(INV, inter((1, "MERCADO A", "10.00")))
        await _wait(lambda: INV in env.manifest())
    finally:
        await svc.stop()


async def test_r3_8_watcher_skipped_when_inbox_missing(env: Env) -> None:
    import shutil

    shutil.rmtree(env.inbox)
    svc = SyncService(env.engine, interval=3600, enable_watcher=True)
    await svc.start()
    try:
        assert svc._observer is None
    finally:
        await svc.stop()

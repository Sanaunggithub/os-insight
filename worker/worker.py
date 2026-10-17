import logging
import math
import multiprocessing
import os
import signal
import threading
import time
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from metrics import MetricsCollector, _cpu_capacity_cores


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("os-insight-worker")
POLL_INTERVAL_S = 1
SAMPLE_INTERVAL_S = 2
MEMORY_RESERVE_BYTES = 48 * 1024 * 1024
HEARTBEAT_PATH = "/tmp/worker-heartbeat"
shutdown_event = threading.Event()


def _touch_heartbeat() -> None:
    with open(HEARTBEAT_PATH, "w") as heartbeat:
        heartbeat.write("ok\n")


def _database_conninfo() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    return make_conninfo(
        dbname=os.getenv("POSTGRES_DB", "os_insight"),
        user=os.getenv("POSTGRES_USER", "os_insight"),
        password=os.getenv("POSTGRES_PASSWORD", "change-me"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


def _handle_shutdown(signum: int, _frame: object) -> None:
    logger.info("Received signal %s; stopping after the active job", signum)
    shutdown_event.set()


def _sample_metrics(pool: ConnectionPool, collector: MetricsCollector) -> None:
    while not shutdown_event.is_set():
        _touch_heartbeat()
        try:
            sample = collector.collect()
            with pool.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO samples (
                        service, ts, cpu_percent, mem_used_bytes,
                        mem_limit_bytes, pids, threads
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        sample["service"],
                        sample["ts"],
                        sample["cpu_percent"],
                        sample["mem_used_bytes"],
                        sample["mem_limit_bytes"],
                        sample["pids"],
                        sample["threads"],
                    ),
                )
        except (OSError, RuntimeError, psycopg.Error, PoolTimeout):
            logger.exception("Could not collect or store the worker metrics sample")
        shutdown_event.wait(SAMPLE_INTERVAL_S)


def _claim_job(pool: ConnectionPool) -> dict | None:
    with pool.connection() as connection:
        with connection.transaction():
            job = connection.execute(
                """
                SELECT id, kind, intensity, duration_s, oom_demo
                FROM stress_jobs
                WHERE status = 'pending'
                ORDER BY created_at, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            ).fetchone()
            if job is None:
                return None
            connection.execute(
                "UPDATE stress_jobs SET status = 'running' WHERE id = %s",
                (job["id"],),
            )
    return job


def _cpu_burn(stop_event: Any, intensity: float) -> None:
    # Busy-loop work gives the OS scheduler CPU-bound processes to schedule.
    duty_cycle = min(max(intensity, 0.0), 100.0) / 100
    cycle_seconds = 0.1
    while not stop_event.is_set():
        started = time.monotonic()
        busy_seconds = cycle_seconds * duty_cycle
        while time.monotonic() - started < busy_seconds:
            pass
        remaining = cycle_seconds - (time.monotonic() - started)
        if remaining > 0:
            stop_event.wait(remaining)


def _run_cpu_job(job: dict) -> None:
    intensity = float(job["intensity"])
    # Spawn one worker per quota-visible CPU, rounded up; cgroups schedule and
    # throttle these independent processes under the container's CPU limit.
    process_count = math.ceil(_cpu_capacity_cores()) if intensity > 0 else 0
    process_context = multiprocessing.get_context("spawn")
    stop_event = process_context.Event()
    processes = [
        process_context.Process(
            target=_cpu_burn,
            args=(stop_event, intensity),
            name=f"cpu-stress-{job['id']}-{index + 1}",
        )
        for index in range(process_count)
    ]
    try:
        for process in processes:
            if shutdown_event.is_set():
                raise InterruptedError("Worker is shutting down")
            process.start()
        if shutdown_event.wait(int(job["duration_s"])):
            raise InterruptedError("Worker is shutting down")
    finally:
        stop_event.set()
        for process in processes:
            if process.pid is not None:
                process.join(timeout=3)
                if process.is_alive():
                    process.terminate()
                    process.join()
    if shutdown_event.is_set():
        raise InterruptedError("Worker is shutting down")
    failed = [
        process.name
        for process in processes
        if process.exitcode not in (0, None)
    ]
    if failed:
        raise RuntimeError(f"CPU stress process(es) failed: {', '.join(failed)}")


def _run_memory_job(job: dict, collector: MetricsCollector) -> None:
    sample = collector.collect()
    limit = sample["mem_limit_bytes"]
    requested = int(limit * float(job["intensity"]) / 100) if limit else 0

    if not limit:
        raise RuntimeError("Memory stress requires a finite cgroup memory limit")
    # Reject unsafe requests rather than silently reducing them; the explicit
    # demo flag is the opt-in for allocations above this cgroup safety bound.
    if requested > limit * 0.8 and not job["oom_demo"]:
        raise ValueError("Memory request exceeds 80% of the cgroup memory limit")

    allocated: list[bytearray] = []
    remaining = requested
    try:
        while remaining > 0:
            if shutdown_event.is_set():
                raise InterruptedError("Worker is shutting down")
            chunk_size = min(remaining, 1024 * 1024)
            # Touch each page so the OS commits the allocation to this process.
            chunk = bytearray(chunk_size)
            for offset in range(0, chunk_size, 4096):
                chunk[offset] = 1
            allocated.append(chunk)
            remaining -= chunk_size
        # Holding the chunks demonstrates resident memory pressure constrained
        # by the cgroup memory controller until the job duration elapses.
        if shutdown_event.wait(int(job["duration_s"])):
            raise InterruptedError("Worker is shutting down")
    finally:
        allocated.clear()


def _finish_job(pool: ConnectionPool, job_id: int, error: str | None) -> None:
    status = "failed" if error else "done"
    with pool.connection() as connection:
        connection.execute(
            """
            UPDATE stress_jobs
            SET status = %s, finished_at = %s, error_message = %s
            WHERE id = %s
            """,
            (status, datetime.now(UTC), error, job_id),
        )


def _mark_interrupted_jobs_failed(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """
            UPDATE stress_jobs
            SET status = 'failed',
                error_message = %s,
                finished_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
            """,
            ("worker restarted (possible OOM kill)",),
        )


def _run_job(pool: ConnectionPool, collector: MetricsCollector, job: dict) -> None:
    logger.info("Running %s stress job %s", job["kind"], job["id"])
    try:
        if job["kind"] == "cpu":
            _run_cpu_job(job)
        elif job["kind"] == "memory":
            _run_memory_job(job, collector)
        else:
            raise ValueError(f"Unsupported stress job kind: {job['kind']}")
    except InterruptedError as exc:
        try:
            _finish_job(pool, job["id"], str(exc))
        except (psycopg.Error, PoolTimeout):
            logger.exception("Could not mark interrupted job %s as failed", job["id"])
        return
    except Exception as exc:
        logger.exception("Stress job %s failed", job["id"])
        message = str(exc)[:2000] or exc.__class__.__name__
        try:
            _finish_job(pool, job["id"], message)
        except (psycopg.Error, PoolTimeout):
            logger.exception("Could not mark failed job %s in the database", job["id"])
        return

    try:
        _finish_job(pool, job["id"], None)
    except (psycopg.Error, PoolTimeout):
        logger.exception("Could not mark completed job %s in the database", job["id"])


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    pool = ConnectionPool(
        conninfo=_database_conninfo(),
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"row_factory": dict_row},
    )
    pool.open(wait=True, timeout=10)
    try:
        _mark_interrupted_jobs_failed(pool)
    except Exception:
        pool.close()
        raise
    collector = MetricsCollector("worker")
    sampler = threading.Thread(
        target=_sample_metrics,
        args=(pool, collector),
        name="metrics-sampler",
        daemon=True,
    )
    sampler.start()
    try:
        while not shutdown_event.is_set():
            _touch_heartbeat()
            try:
                job = _claim_job(pool)
            except (psycopg.Error, PoolTimeout):
                logger.exception("Could not fetch a pending stress job")
                shutdown_event.wait(POLL_INTERVAL_S)
                continue
            if job is None:
                shutdown_event.wait(POLL_INTERVAL_S)
                continue
            _run_job(pool, collector, job)
    finally:
        shutdown_event.set()
        sampler.join(timeout=SAMPLE_INTERVAL_S + 1)
        pool.close()


if __name__ == "__main__":
    main()

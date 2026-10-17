import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from metrics import MetricsCollector, get_os_info


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
SAMPLE_INTERVAL_S = 2
SERVICE_NAME = os.getenv("SERVICE_NAME", "api")


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


def _pool(request: Request) -> ConnectionPool:
    return request.app.state.db_pool


async def _sample_metrics(app: FastAPI, collector: MetricsCollector) -> None:
    while True:
        try:
            sample = collector.collect()
            with app.state.db_pool.connection() as connection:
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
            logger.exception("Could not collect or store the API metrics sample")
        await asyncio.sleep(SAMPLE_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ConnectionPool(
        conninfo=_database_conninfo(),
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"row_factory": dict_row},
    )
    try:
        pool.open(wait=True, timeout=10)
    except (psycopg.Error, PoolTimeout):
        pool.close()
        raise

    app.state.db_pool = pool
    collector = MetricsCollector(SERVICE_NAME)
    app.state.metrics_collector = collector
    sampler = asyncio.create_task(_sample_metrics(app, collector))
    try:
        yield
    finally:
        # Uvicorn handles SIGTERM by shutting down the app; cancel its sampler
        # before closing the pool so no background write races with shutdown.
        sampler.cancel()
        with suppress(asyncio.CancelledError):
            await sampler
        pool.close()


app = FastAPI(title="OS Insight API", lifespan=lifespan)


class StressJobCreate(BaseModel):
    kind: Literal["cpu", "memory"]
    intensity: float = Field(ge=0, le=100)
    duration_s: int = Field(ge=1, le=3600)
    oom_demo: bool = False


@app.get("/health")
def health(request: Request) -> dict[str, str]:
    try:
        with _pool(request).connection() as connection:
            connection.execute("SELECT 1")
    except (psycopg.Error, PoolTimeout) as exc:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}


@app.get("/metrics/live")
def live_metrics(request: Request) -> dict:
    try:
        return request.app.state.metrics_collector.collect()
    except RuntimeError as exc:
        logger.exception("Could not collect live metrics")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/metrics/history")
def metrics_history(
    request: Request,
    service: Annotated[str, Query(min_length=1, max_length=128)] = SERVICE_NAME,
    minutes: Annotated[int, Query(ge=1, le=10080)] = 60,
) -> list[dict]:
    try:
        with _pool(request).connection() as connection:
            rows = connection.execute(
                """
                SELECT id, service, ts, cpu_percent, mem_used_bytes,
                       mem_limit_bytes, pids, threads
                FROM samples
                WHERE service = %s
                  AND ts >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
                ORDER BY ts ASC
                """,
                (service, minutes),
            ).fetchall()
        return rows
    except (psycopg.Error, PoolTimeout) as exc:
        logger.exception("Could not read metric history")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.post("/stress", status_code=201)
def create_stress_job(job: StressJobCreate, request: Request) -> dict:
    try:
        with _pool(request).connection() as connection:
            row = connection.execute(
                """
                INSERT INTO stress_jobs (kind, intensity, duration_s, oom_demo)
                VALUES (%s, %s, %s, %s)
                RETURNING id, kind, intensity, duration_s, status, created_at,
                          finished_at, oom_demo, error_message
                """,
                (job.kind, job.intensity, job.duration_s, job.oom_demo),
            ).fetchone()
        return row
    except (psycopg.Error, PoolTimeout) as exc:
        logger.exception("Could not create stress job")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.get("/stress")
def list_stress_jobs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    try:
        with _pool(request).connection() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, intensity, duration_s, status, created_at,
                       finished_at, oom_demo, error_message
                FROM stress_jobs
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()
        return rows
    except (psycopg.Error, PoolTimeout) as exc:
        logger.exception("Could not list stress jobs")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.get("/os-info")
def os_info() -> dict:
    try:
        return get_os_info()
    except RuntimeError as exc:
        logger.exception("Could not read operating-system information")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

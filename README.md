# OS Insight

OS Insight is a container resource observatory. The FastAPI service reports
container metrics and writes history to PostgreSQL. The worker polls PostgreSQL
for stress jobs, runs bounded CPU or memory workloads, and records its own
metrics.

## Build and run

```sh
cp .env.example .env
docker compose up --build -d
```

The API is available at `http://localhost:8001` by default; PostgreSQL
initializes its tables from `db/init.sql` when its data volume is first created.
The worker waits for PostgreSQL to be healthy, then checks for jobs once per
second and samples its metrics every two seconds. Its container is limited to
0.5 CPU and 256 MiB of memory. To stop the services, run `docker compose down`;
database data remains in the named volume.

## API endpoints

- `GET /health` checks API and database availability.
- `GET /metrics/live` reads current process and cgroup metrics.
- `GET /metrics/history?service=api&minutes=60` reads stored samples.
- `POST /stress` creates a job, for example `{"kind":"cpu","intensity":50,"duration_s":30}`.
  Intensity is capped at 100 and duration at 3600 seconds.
- `GET /stress` lists jobs.
- `GET /os-info` reports hostname, PID 1, cgroup version, and limits.

Memory jobs allocate up to the requested percentage of the worker's memory
limit while reserving space for the service. Set `oom_demo` to `true` only when
intentionally demonstrating an out-of-memory kill; this can restart the worker.
The worker uses only the `samples` and `stress_jobs` tables defined in
`db/init.sql` and does not create or modify database schema.

The `.env.example` password is for local development only. Change it before
using the database in a shared or deployed environment.

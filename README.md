# OS Insight

OS Insight is a container resource observatory. This scaffold runs the FastAPI
service and PostgreSQL database; the `web` and `worker` directories are reserved
for application services that will be added later.

## Build and run

```sh
cp .env.example .env
docker compose up --build -d
```

The API is available at `http://localhost:8000`; PostgreSQL initializes its
tables from `db/init.sql` when its data volume is first created. To stop the
services, run `docker compose down`; database data remains in the named volume.

## API endpoints

- `GET /health` checks API and database availability.
- `GET /metrics/live` reads current process and cgroup metrics.
- `GET /metrics/history?service=api&minutes=60` reads stored samples.
- `POST /stress` creates a job, for example `{"kind":"cpu","intensity":50,"duration_s":30}`.
  Intensity is capped at 100 and duration at 3600 seconds.
- `GET /stress` lists jobs.
- `GET /os-info` reports hostname, PID 1, cgroup version, and limits.

The `.env.example` password is for local development only. Change it before
using the database in a shared or deployed environment.

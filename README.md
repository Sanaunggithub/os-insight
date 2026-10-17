# OS Insight

## 1. Project overview

OS Insight is a multi-tier web application for observing operating-system resource usage inside Docker containers. Its dashboard shows live CPU, memory, process, and thread measurements for the API and worker, along with recent CPU history and job status. Users can submit bounded CPU and memory stress jobs and observe how container resource limits affect them. The application uses PostgreSQL to store metric samples and job records.

## 2. Architecture

```text
                         Browser
                            |
             WEB_HOST_PORT (default 3000)
                            v
                    +---------------+
                    | web :3000     |
                    | Next.js UI    |
                    +-------+-------+
                            | server-side proxy
                            | API_BASE_URL=http://api:8000
                            v
             API_HOST_PORT (default 8001)
                    +---------------+
                    | api :8000     |
                    | FastAPI       |
                    +---+-------+---+
                        |       |
           HTTP/SQL     |       | SQL / job polling
                        v       v
                   +--------+  +---------------+
                   | db     |  | worker        |
                   |        |  | no host port  |
                   +---+----+  +---------------+
                       |
                       v
                 postgres_data
                 named volume

       All four containers join os_insight_net (bridge network).
       Only web and api publish host ports.
       Neither db nor worker publishes a host port.
```

The web container reaches the API by its Compose service name, `api`, rather than a host-published port. The API and worker connect to the database at the `db` service name. PostgreSQL's data directory is stored in the named `postgres_data` volume.

## 3. Tech stack

- **Container orchestration:** Docker Engine and Docker Compose v2
- **Dashboard:** Next.js, React, TypeScript, and Chart.js
- **API:** Python, FastAPI, Uvicorn, and Psycopg
- **Job worker:** Python, multiprocessing, and Psycopg
- **Database:** PostgreSQL 16
- **Resource reporting:** Linux `/proc` and cgroup metrics

## 4. Repository structure

```text
.
├── .dockerignore                 # Excludes local/generated files from the worker build context
├── .env.example                  # Safe local defaults for Compose variables
├── .gitignore                    # Excludes local environment files and GitHub settings
├── README.md                     # Setup, usage, demos, and OS concept guide
├── docker-compose.yml            # Four-service development deployment
├── api/
│   ├── .dockerignore             # Excludes local Python and environment files from API image
│   ├── Dockerfile                # Builds the FastAPI container
│   ├── main.py                   # API endpoints and metric sampling
│   ├── metrics.py                # Reads process and cgroup resource information
│   └── requirements.txt          # API Python dependencies
├── db/
│   └── init.sql                  # Creates metrics and stress-job tables on first DB start
├── docs/
│   └── AI_USAGE.md               # AI assistance disclosure
├── web/
│   ├── .dockerignore             # Excludes local web dependencies and generated files
│   ├── .gitignore                # Excludes local Next.js and TypeScript output
│   ├── Dockerfile                # Builds the Next.js production container
│   ├── package.json              # Web scripts and dependencies
│   ├── package-lock.json         # Locked web dependency tree used by npm ci
│   ├── next-env.d.ts             # Next.js TypeScript declarations
│   ├── tsconfig.json             # TypeScript and Next.js compiler settings
│   └── src/
│       ├── app/
│       │   ├── backend/[...path]/route.ts # Proxies dashboard API requests server-side
│       │   ├── globals.css       # Dashboard styles
│       │   ├── layout.tsx        # Root page layout and metadata
│       │   └── page.tsx          # Live dashboard and stress-job form
│       ├── components/
│       │   └── CpuHistoryChart.tsx # CPU history chart
│       └── lib/
│           ├── api.ts            # Dashboard API client
│           └── types.ts          # Dashboard data types
└── worker/
    ├── Dockerfile                # Builds the job worker container
    ├── requirements.txt          # Worker Python dependencies
    └── worker.py                 # Polls jobs and runs CPU/memory workloads
```

## 5. Prerequisites

- Docker Engine
- Docker Compose v2, available as the `docker compose` command
- Git to clone the repository
- Free host ports **3000** and **8001**, or alternative host ports set in `.env`

No host-installed Python, Node.js, or PostgreSQL is needed. Docker builds the application images and runs the database.

## 6. Install

Clone the repository and enter its directory:

```sh
git clone https://github.com/Sanaunggithub/os-insight.git
cd os-insight
cp .env.example .env
```

Compose reads `.env` to configure the local deployment. The example file includes:

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_DB` | `os_insight` | PostgreSQL database name used by the database, API, and worker |
| `POSTGRES_USER` | `os_insight` | PostgreSQL username used by the database, API, and worker |
| `POSTGRES_PASSWORD` | `change-me` | Local-development database password; choose a private value for any shared deployment |
| `API_HOST_PORT` | `8001` | Host port mapped to the API container's port `8000` |
| `WEB_HOST_PORT` | `3000` | Host port mapped to the web container's port `3000` |
| `API_BASE_URL` | `http://api:8000` | URL the web server uses to reach the API over the Compose network |

If host port 3000 or 8001 is already in use, edit `WEB_HOST_PORT` or `API_HOST_PORT` in `.env` to an available host port. Keep the container ports unchanged; for example, setting `WEB_HOST_PORT=3001` makes the dashboard available at `http://localhost:3001`. The web container should continue to use `API_BASE_URL=http://api:8000`; it uses Compose's internal service address, not the host port.

## 7. Build

Build the API, worker, and web images:

```sh
docker compose build
```

## 8. Run

Start the database and application:

```sh
docker compose up -d
docker compose ps
```

Wait for the `db`, `api`, `worker`, and `web` services to show **healthy** in the `STATUS` column. The API and worker wait for a healthy database, and web waits for a healthy API. The first start may take longer while PostgreSQL initializes and the services start.

## 9. Use it

Open the dashboard at **http://localhost:3000** with the default settings. If you changed `WEB_HOST_PORT`, use that host port instead. The dashboard refreshes resource data and job status every two seconds. To launch a job, choose **CPU** or **Memory**, enter an intensity from 0 to 100 and a duration from 1 to 3600 seconds, then select **Create stress job**.

The API is available directly on **http://localhost:8001** by default, or the configured `API_HOST_PORT`. Its interactive documentation is at `/docs`. Useful endpoints are:

| Method and path | Purpose |
|---|---|
| `GET /docs` | Interactive API documentation |
| `GET /health` | Checks API and database availability |
| `GET /metrics/live` | Reads current API process and cgroup metrics |
| `GET /os-info` | Reports OS, PID 1, cgroup version, and configured limits |
| `POST /stress` | Creates a CPU or memory job |
| `GET /stress` | Lists recent stress jobs |
| `GET /metrics/history?service=api&minutes=60` | Reads API metric history |

For example, with the default API host port:

```sh
curl http://localhost:8001/health
curl http://localhost:8001/metrics/live
curl http://localhost:8001/os-info
curl -X POST http://localhost:8001/stress \
  -H 'Content-Type: application/json' \
  -d '{"kind":"cpu","intensity":50,"duration_s":30}'
curl -X POST http://localhost:8001/stress \
  -H 'Content-Type: application/json' \
  -d '{"kind":"memory","intensity":50,"duration_s":30}'
curl http://localhost:8001/stress
```

Use the API host port from `.env` in place of `8001` if you changed it. A successful job-creation request returns the new job record; the worker updates its status as it runs.

## 10. Demos

### CPU quota

The worker has a Compose CPU limit of **0.5 CPU**. A 100%-intensity CPU job requests full workload from its worker process, but the container's cgroup CFS quota limits total worker CPU consumption to about half of one CPU core. In one terminal, watch the worker's resource use:

```sh
docker stats "$(docker compose ps -q worker)"
```

In another terminal, start a 60-second CPU job:

```sh
curl -X POST http://localhost:8001/stress \
  -H 'Content-Type: application/json' \
  -d '{"kind":"cpu","intensity":100,"duration_s":60}'
```

### Memory guard

The worker rejects a memory request above 80% of its cgroup memory limit unless `oom_demo` is enabled. The following request is accepted by the API but is recorded as a failed job by the worker with a memory-guard error:

```sh
curl -X POST http://localhost:8001/stress \
  -H 'Content-Type: application/json' \
  -d '{"kind":"memory","intensity":90,"duration_s":30}'
curl http://localhost:8001/stress
```

### OOM-killer demonstration

**This intentionally risks killing and restarting the worker container.** Keep a terminal open to capture Docker events before submitting the job:

```sh
docker events --filter container="$(docker compose ps -q worker)"
```

In another terminal, opt into a 100%-of-limit allocation:

```sh
curl -X POST http://localhost:8001/stress \
  -H 'Content-Type: application/json' \
  -d '{"kind":"memory","intensity":100,"duration_s":30,"oom_demo":true}'
```

The worker attempts to touch the requested memory. The cgroup memory limit can cause the kernel OOM killer to terminate it; Docker events should show the worker's `oom`/`die` and subsequent `start` events, with exit code **137** for the killed process. Because the worker has `restart: unless-stopped`, Docker restarts it. After it returns, `docker compose ps` can confirm its status; the restarted worker marks any interrupted running job as failed.

## 11. Stop and clean up

Stop and remove the containers and project network while keeping the database volume:

```sh
docker compose down
```

To also remove the named PostgreSQL volume and permanently delete the stored database records:

```sh
docker compose down -v
```

`db/init.sql` creates the tables only when PostgreSQL initializes a **fresh** data volume. It does not rerun on an existing volume. If you need the schema initialized again, `docker compose down -v` removes the old volume; the next `docker compose up -d` creates a new one and runs the script. This also deletes all saved metrics and jobs.

## 12. Troubleshooting

- **A host port is already in use:** Change `WEB_HOST_PORT` or `API_HOST_PORT` in `.env` to a free host port, then run `docker compose up -d` again. The container-side ports stay at 3000 for web and 8000 for API.
- **Database tables are missing or the initialization script did not run:** `db/init.sql` only runs for a new `postgres_data` volume. To reinitialize, run `docker compose down -v` and then `docker compose up -d`; this deletes the existing database data.
- **A container is unhealthy or exits:** Inspect service logs with `docker compose logs db api worker web`, then check startup and health status with `docker compose ps`. The API and worker depend on database health, and web depends on API health.
- **The web page loads but API-backed data is unavailable:** Keep `API_BASE_URL` set to `http://api:8000` for the default Compose network. This is an internal service URL; it is not the API's host-published port.

## 13. Operating system concepts

| Feature | Operating system concept |
|---|---|
| Each service runs in its own container; API and web processes run as PID 1 in their containers | Process isolation and PID namespaces |
| The worker starts child processes for CPU stress jobs | Processes and process creation |
| The API and worker have background metric-sampling threads | Threads and concurrent execution |
| The worker's `cpus: 0.5` limit controls CPU time shared by its workload | CPU scheduling and the cgroup CFS quota |
| The worker's `mem_limit: 256m` limit and opt-in OOM demo constrain memory | Memory limits, cgroups, and the kernel OOM killer |
| Containers isolate process IDs and resource accounting | Namespaces and cgroups |
| PostgreSQL records survive container replacement in `postgres_data` | Persistent volumes versus a disposable container layer |
| Services communicate over the Compose bridge using service names such as `api` and `db` | Bridge networking and service-name DNS |
| Containers receive termination signals and shut down their application processes | Signals and graceful shutdown |
| The dashboard/API use HTTP, while the API and worker read and write PostgreSQL records | Inter-process communication via HTTP and a database |

## 14. Use of AI

AI assistance was used to help review the project and prepare its documentation; the resulting descriptions were checked against the repository configuration and source. See [docs/AI_USAGE.md](./docs/AI_USAGE.md) for the disclosure.

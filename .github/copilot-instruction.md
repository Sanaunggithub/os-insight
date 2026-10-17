You are helping me build a university Operating Systems course project:
"Multi-Tier Web Application Deployment Using Docker". It is graded strictly.

HARD REQUIREMENTS (do not violate):
- Individual project; small application run with Docker (docker compose).
- Must include: application source code, a Dockerfile, a docker-compose.yml,
  and a README.md explaining how to install, build, and run the system.
- The system must show different parts (web app and database) separated and
  running as containers.
- The code must be simple and readable enough that I can explain every file
  on video: overview, app structure, source structure, the Dockerfile,
  the docker-compose.yml, build/run steps, a live demo, how it relates to
  operating system concepts, and problems I hit and how I solved them.

PROJECT: "OS Insight" - a container resource observatory.
Services:
 - web: Next.js (TypeScript) dashboard with Chart.js, port 3000
 - api: FastAPI, port 8000. Reads /proc and /sys/fs/cgroup (support cgroup v2
   and fall back to v1) and exposes CPU %, memory used/limit, process count,
   thread count, uptime, and cgroup limits. Stores samples in PostgreSQL.
 - db: PostgreSQL 16, named volume for persistence, init SQL script
 - worker: Python service that polls the db for stress jobs and runs CPU
   load (multiprocessing) and memory allocation, and reports its own metrics.
 Each of api and worker has its own Dockerfile; web has one too.
 Compose must define: custom bridge network, named volume, healthchecks,
 depends_on with condition: service_healthy, restart policies, and
 cpus / mem_limit for worker and api. Config via .env (provide .env.example).

RULES:
- Do NOT mount /var/run/docker.sock. No privileged containers.
- Keep the app small. No extra frameworks or services beyond the above.
- Add a short comment on every non-obvious line in Dockerfiles and compose
  explaining WHY, since I must explain them in the video.
- Use parameterized SQL only. Handle SIGTERM gracefully in api and worker.
- Every file you create: tell me its purpose in 1-2 sentences.
Acknowledge these rules, then wait for my next prompt.
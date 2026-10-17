# Use a slim Python 3.12 image to keep the worker container small and version-pinned.
FROM python:3.12.11-slim-bookworm

# Send logs straight to container output so job progress is visible.
ENV PYTHONUNBUFFERED=1

# Keep the worker code and installed packages in a predictable directory.
WORKDIR /app

# Copy the worker dependency manifest first so code changes can reuse installed packages.
COPY worker/requirements.txt ./

# Install only declared dependencies and avoid retaining pip's download cache.
RUN pip install --no-cache-dir -r requirements.txt

# Create an explicit unprivileged account for running stress jobs.
RUN groupadd --system app && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

# Copy worker source with ownership so the runtime account can read it.
COPY --chown=app:app worker/worker.py ./

# Reuse the API cgroup reader so both services report metrics consistently.
COPY --chown=app:app api/metrics.py ./

# Drop root; procfs and cgroup metrics remain readable inside the container.
USER app

# Run the worker directly as PID 1 so it receives SIGTERM without an init wrapper.
CMD ["python", "worker.py"]

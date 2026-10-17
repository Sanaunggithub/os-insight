# Use a slim Python 3.12 image to keep the API container small and version-pinned.
FROM python:3.12.11-slim-bookworm

# Keep Python logs flowing directly to container output for easy inspection.
ENV PYTHONUNBUFFERED=1

# Put the API application and installed packages in a predictable directory.
WORKDIR /app

# Copy the dependency manifest first so source edits do not invalidate this layer.
COPY requirements.txt ./

# Install only declared dependencies and avoid retaining pip's download cache.
RUN pip install --no-cache-dir -r requirements.txt

# Create an explicit unprivileged account for running the API process.
RUN groupadd --system app && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

# Copy application code with ownership so the runtime user can read it.
COPY --chown=app:app main.py metrics.py ./

# Drop root before the API starts; Linux exposes procfs and cgroup files to this user.
USER app

# Document the port used by the API server.
EXPOSE 8000

# Check API health using Python's standard library already present in the image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]

# Run Uvicorn directly as PID 1 so it receives SIGTERM without a shell wrapper.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

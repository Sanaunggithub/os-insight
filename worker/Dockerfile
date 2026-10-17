FROM python:3.12-slim

WORKDIR /app

COPY worker/requirements.txt .
# Install database dependencies before source so code changes can reuse this layer.
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/worker.py ./
# Reuse the API's cgroup reader to keep metric interpretation consistent.
COPY api/metrics.py ./

CMD ["python", "worker.py"]

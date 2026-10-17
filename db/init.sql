CREATE TABLE samples (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    cpu_percent DOUBLE PRECISION NOT NULL CHECK (cpu_percent BETWEEN 0 AND 100),
    mem_used_bytes BIGINT NOT NULL CHECK (mem_used_bytes >= 0),
    mem_limit_bytes BIGINT NOT NULL CHECK (mem_limit_bytes >= 0),
    pids INTEGER NOT NULL CHECK (pids >= 0),
    threads INTEGER NOT NULL CHECK (threads >= 0)
);

CREATE INDEX samples_service_ts_idx ON samples (service, ts DESC);

CREATE TABLE stress_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('cpu', 'memory')),
    intensity DOUBLE PRECISION NOT NULL CHECK (intensity >= 0),
    duration_s INTEGER NOT NULL CHECK (duration_s > 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    oom_demo BOOLEAN NOT NULL DEFAULT false,
    error_message TEXT
);

CREATE INDEX stress_jobs_status_created_at_idx
    ON stress_jobs (status, created_at);

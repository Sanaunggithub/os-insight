"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CpuHistoryChart } from "@/components/CpuHistoryChart";
import {
  createStressJob,
  getLiveMetrics,
  getMetricHistory,
  getOsInfo,
  getStressJobs,
} from "@/lib/api";
import type { MetricSample, OsInfo, StressJob } from "@/lib/types";

const REFRESH_INTERVAL_MS = 2_000;

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unitIndex = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  return `${(bytes / 1024 ** unitIndex).toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="metric-card">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {detail && <span className="metric-detail">{detail}</span>}
    </div>
  );
}

function ServicePanel({
  title,
  sample,
  unavailable,
}: {
  title: string;
  sample: MetricSample | null;
  unavailable: boolean;
}) {
  return (
    <section className="service-panel">
      <div className="service-heading">
        <div>
          <p className="eyebrow">CONTAINER</p>
          <h3>{title}</h3>
        </div>
        <span className={`live-indicator ${sample ? "" : "inactive"}`}>
          <span />
          {sample ? "Live" : unavailable ? "Unavailable" : "Waiting"}
        </span>
      </div>
      <div className="metric-grid">
        <MetricCard
          label="CPU"
          value={sample ? `${sample.cpu_percent.toFixed(1)}%` : "--"}
        />
        <MetricCard
          label="Memory"
          value={sample ? formatBytes(sample.mem_used_bytes) : "--"}
          detail={
            sample
              ? sample.mem_limit_bytes > 0
                ? `of ${formatBytes(sample.mem_limit_bytes)}`
                : "limit unavailable"
              : undefined
          }
        />
        <MetricCard
          label="Processes"
          value={sample ? sample.pids.toLocaleString() : "--"}
        />
        <MetricCard
          label="Threads"
          value={sample ? sample.threads.toLocaleString() : "--"}
        />
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: StressJob["status"] }) {
  return <span className={`status-badge status-${status}`}>{status}</span>;
}

export default function DashboardPage() {
  const [apiLive, setApiLive] = useState<MetricSample | null>(null);
  const [apiHistory, setApiHistory] = useState<MetricSample[]>([]);
  const [workerHistory, setWorkerHistory] = useState<MetricSample[]>([]);
  const [jobs, setJobs] = useState<StressJob[]>([]);
  const [osInfo, setOsInfo] = useState<OsInfo | null>(null);
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [kind, setKind] = useState<"cpu" | "memory">("cpu");
  const [intensity, setIntensity] = useState(50);
  const [duration, setDuration] = useState(30);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const latestWorkerSample = workerHistory.at(-1) ?? null;
  const workerLive =
    latestWorkerSample &&
    Date.now() - new Date(latestWorkerSample.ts).getTime() <=
      REFRESH_INTERVAL_MS * 3
      ? latestWorkerSample
      : null;

  const refresh = useCallback(async () => {
    const [liveResult, apiHistoryResult, workerHistoryResult, jobsResult] =
      await Promise.allSettled([
        getLiveMetrics(),
        getMetricHistory("api"),
        getMetricHistory("worker"),
        getStressJobs(),
      ]);

    const errors: string[] = [];
    if (liveResult.status === "fulfilled") setApiLive(liveResult.value);
    else errors.push("live metrics");
    if (apiHistoryResult.status === "fulfilled")
      setApiHistory(apiHistoryResult.value);
    else errors.push("API history");
    if (workerHistoryResult.status === "fulfilled")
      setWorkerHistory(workerHistoryResult.value);
    else errors.push("worker history");
    if (jobsResult.status === "fulfilled") setJobs(jobsResult.value);
    else errors.push("stress jobs");

    setLoadError(
      errors.length
        ? `Could not refresh ${errors.join(", ")}. Check that the API and database are running.`
        : "",
    );
    setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      await refresh();
      if (active) timer = setTimeout(tick, REFRESH_INTERVAL_MS);
    };
    void tick();
    void getOsInfo()
      .then((info) => {
        if (active) setOsInfo(info);
      })
      .catch(() => {
        if (active) setLoadError("Could not load operating-system information.");
      });
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [refresh]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError("");
    try {
      await createStressJob({
        kind,
        intensity,
        duration_s: duration,
      });
      await refresh();
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Could not create stress job.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="OS Insight home">
          <span className="brand-mark">OI</span>
          <span>OS Insight</span>
        </a>
        <div className="topbar-meta">
          <span className="system-label">CONTAINER RESOURCE OBSERVATORY</span>
          <span className="refresh-label">
            <span className="refresh-dot" />
            Refreshing every 2 seconds
          </span>
        </div>
      </header>

      <div className="dashboard">
        <section className="page-heading">
          <div>
            <p className="eyebrow">SYSTEM OVERVIEW</p>
            <h1>Container dashboard</h1>
            <p className="page-description">
              Observe resource usage and run controlled stress jobs.
            </p>
          </div>
          <div className="updated-at">
            <span className="eyebrow">LAST UPDATED</span>
            <strong>
              {lastUpdated
                ? lastUpdated.toLocaleTimeString()
                : "Connecting..."}
            </strong>
          </div>
        </section>

        {loadError && (
          <div className="notice error-notice" role="status">
            {loadError}
          </div>
        )}

        <section className="section-block" aria-labelledby="live-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">LIVE TELEMETRY</p>
              <h2 id="live-heading">Resource usage</h2>
            </div>
            <span className="section-caption">Current container samples</span>
          </div>
          <div className="service-list">
            <ServicePanel title="API" sample={apiLive} unavailable={!apiLive && !!loadError} />
            <ServicePanel
              title="Worker"
              sample={workerLive}
              unavailable={!workerLive && !!loadError}
            />
          </div>
        </section>

        <div className="content-grid">
          <section className="card chart-card" aria-labelledby="history-heading">
            <div className="card-heading">
              <div>
                <p className="eyebrow">LAST 60 MINUTES</p>
                <h2 id="history-heading">CPU history</h2>
              </div>
              <span className="chart-unit">Percent</span>
            </div>
            <div className="chart-wrap">
              <CpuHistoryChart
                apiSamples={apiHistory}
                workerSamples={workerHistory}
              />
            </div>
          </section>

          <section className="card stress-card" aria-labelledby="stress-heading">
            <div className="card-heading">
              <div>
                <p className="eyebrow">CONTROLLED LOAD</p>
                <h2 id="stress-heading">Launch a stress job</h2>
              </div>
            </div>
            <form className="stress-form" onSubmit={handleSubmit}>
              <label>
                Workload
                <select
                  value={kind}
                  onChange={(event) =>
                    setKind(event.target.value as "cpu" | "memory")
                  }
                >
                  <option value="cpu">CPU</option>
                  <option value="memory">Memory</option>
                </select>
              </label>
              <label>
                Intensity <span className="field-unit">0–100%</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={intensity}
                  onChange={(event) => setIntensity(Number(event.target.value))}
                  required
                />
              </label>
              <label>
                Duration <span className="field-unit">seconds · max 3600</span>
                <input
                  type="number"
                  min="1"
                  max="3600"
                  step="1"
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                  required
                />
              </label>
              {submitError && (
                <div className="form-error" role="alert">
                  {submitError}
                </div>
              )}
              <button className="primary-button" type="submit" disabled={submitting}>
                {submitting ? "Submitting..." : "Create stress job"}
                {!submitting && <span aria-hidden="true">→</span>}
              </button>
            </form>
          </section>
        </div>

        <section className="card jobs-card" aria-labelledby="jobs-heading">
          <div className="card-heading jobs-heading">
            <div>
              <p className="eyebrow">RECENT ACTIVITY</p>
              <h2 id="jobs-heading">Stress jobs</h2>
            </div>
            <span className="section-caption">{jobs.length} recent jobs</span>
          </div>
          {jobs.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Workload</th>
                    <th>Intensity</th>
                    <th>Duration</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td className="job-id">#{job.id}</td>
                      <td>{job.kind}</td>
                      <td>{job.intensity}%</td>
                      <td>{job.duration_s}s</td>
                      <td>
                        <StatusBadge status={job.status} />
                        {job.error_message && (
                          <span
                            className="job-error"
                            title={job.error_message}
                          >
                            {job.error_message}
                          </span>
                        )}
                      </td>
                      <td className="timestamp-cell">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              No stress jobs yet. Create one to observe resource changes.
            </div>
          )}
        </section>

        <section className="concepts-panel" aria-labelledby="concepts-heading">
          <div className="concepts-intro">
            <p className="eyebrow">UNDER THE HOOD</p>
            <h2 id="concepts-heading">OS concepts</h2>
            <p>
              Container metrics come from Linux procfs and cgroup controllers.
            </p>
          </div>
          {osInfo ? (
            <div className="concept-grid">
              <div className="concept-item">
                <span>Hostname</span>
                <strong>{osInfo.hostname}</strong>
              </div>
              <div className="concept-item">
                <span>PID 1 process</span>
                <strong>{osInfo.pid1_process_name}</strong>
              </div>
              <div className="concept-item">
                <span>Cgroup version</span>
                <strong>v{osInfo.cgroup_version}</strong>
              </div>
              <div className="concept-item">
                <span>CPU capacity</span>
                <strong>{osInfo.limits.cpu_capacity_cores.toFixed(2)} cores</strong>
              </div>
              <div className="concept-item">
                <span>Memory limit</span>
                <strong>
                  {osInfo.limits.memory_limit_bytes
                    ? formatBytes(osInfo.limits.memory_limit_bytes)
                    : "No limit"}
                </strong>
              </div>
              <div className="concept-item">
                <span>Process limit</span>
                <strong>{osInfo.limits.pids_limit ?? "No limit"}</strong>
              </div>
            </div>
          ) : (
            <div className="concept-loading">Loading OS information...</div>
          )}
        </section>

        <footer className="footer">
          <span>OS Insight</span>
          <span>Resource data updates every 2 seconds</span>
        </footer>
      </div>
    </main>
  );
}

export type MetricSample = {
  id?: number;
  service: string;
  ts: string;
  cpu_percent: number;
  mem_used_bytes: number;
  mem_limit_bytes: number;
  pids: number;
  threads: number;
};

export type StressJob = {
  id: number;
  kind: "cpu" | "memory";
  intensity: number;
  duration_s: number;
  status: "pending" | "running" | "done" | "failed";
  created_at: string;
  finished_at: string | null;
  oom_demo: boolean;
  error_message: string | null;
};

export type OsInfo = {
  hostname: string;
  pid1_process_name: string;
  cgroup_version: number;
  limits: {
    cpu_capacity_cores: number;
    memory_limit_bytes: number;
    pids_limit: number | null;
  };
};

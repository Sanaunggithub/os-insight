"use client";

import {
  Chart,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  type ChartDataset,
} from "chart.js";
import { useEffect, useRef } from "react";
import type { MetricSample } from "@/lib/types";

Chart.register(
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
);

type Point = { x: number; y: number };
type Dataset = ChartDataset<"line", Point[]>;

type CpuHistoryChartProps = {
  apiSamples: MetricSample[];
  workerSamples: MetricSample[];
};

function toPoints(samples: MetricSample[]): Point[] {
  return samples.map((sample) => ({
    x: new Date(sample.ts).getTime(),
    y: sample.cpu_percent,
  }));
}

export function CpuHistoryChart({
  apiSamples,
  workerSamples,
}: CpuHistoryChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart<"line", Point[], number> | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    chartRef.current = new Chart<"line", Point[], number>(canvas, {
      type: "line",
      data: { datasets: [] },
      options: {
        animation: false,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "nearest" },
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true } },
          tooltip: {
            callbacks: {
              title: (items) =>
                items[0]?.parsed.x != null
                  ? new Date(items[0].parsed.x).toLocaleString()
                  : "",
              label: (item) =>
                `${item.dataset.label}: ${(item.parsed.y ?? 0).toFixed(1)}%`,
            },
          },
        },
        scales: {
          x: {
            type: "linear",
            grid: { display: false },
            ticks: {
              maxTicksLimit: 6,
              callback: (value) =>
                new Date(Number(value)).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
            },
          },
          y: {
            min: 0,
            max: 100,
            title: { display: true, text: "CPU utilization (%)" },
            grid: { color: "#e8edf1" },
          },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.data.datasets = [
      {
        label: "API",
        data: toPoints(apiSamples),
        borderColor: "#147d70",
        backgroundColor: "#147d70",
        pointRadius: 1,
        borderWidth: 2,
        tension: 0.25,
      },
      {
        label: "Worker",
        data: toPoints(workerSamples),
        borderColor: "#d18b36",
        backgroundColor: "#d18b36",
        pointRadius: 1,
        borderWidth: 2,
        tension: 0.25,
      },
    ];
    chart.update("none");
  }, [apiSamples, workerSamples]);

  return <canvas ref={canvasRef} aria-label="CPU history for API and worker" />;
}

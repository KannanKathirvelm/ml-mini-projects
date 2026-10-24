import {
  CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement, PointElement, Tooltip, type ChartOptions,
} from 'chart.js';
import React, { useMemo } from 'react';
import { Line } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Legend, Tooltip, Filler);

export interface Series { label: string; data: (number | null)[]; color: string; dashed?: boolean; fill?: boolean; width?: number }

const isDark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches;

export const LineChart: React.FC<{ labels: string[]; series: Series[]; height?: number; yLabel?: string }> = ({ labels, series, height = 240, yLabel }) => {
  const dark = isDark();
  const grid = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  const text = dark ? '#cbd5e1' : '#475569';
  const data = useMemo(() => ({
    labels,
    datasets: series.map((s) => ({
      label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color + '22', borderWidth: s.width ?? 2,
      borderDash: s.dashed ? [5, 4] : undefined, pointRadius: 0, pointHitRadius: 8, tension: 0.15, fill: s.fill ?? false, spanGaps: true,
    })),
  }), [labels, series]);
  const options: ChartOptions<'line'> = {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { color: text, boxWidth: 12, font: { size: 11 } } }, tooltip: { enabled: true } },
    scales: {
      x: { ticks: { color: text, maxTicksLimit: 5, maxRotation: 0, font: { size: 10 } }, grid: { color: grid } },
      y: { ticks: { color: text, font: { size: 10 } }, grid: { color: grid }, title: yLabel ? { display: true, text: yLabel, color: text } : undefined },
    },
  };
  return <div style={{ height }}><Line data={data} options={options} /></div>;
};

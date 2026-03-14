"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface UsageChartPoint {
  date: string;
  sessions: number;
  messages: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

type UsageMetric = "sessions" | "messages" | "total_tokens";

const METRIC_CONFIG: Record<
  UsageMetric,
  { label: string; stroke: string; fill: string; formatter: (value: number) => string }
> = {
  sessions: {
    label: "Sessions",
    stroke: "#0ea5e9",
    fill: "#38bdf8",
    formatter: (value) => `${value}`,
  },
  messages: {
    label: "Messages",
    stroke: "#22c55e",
    fill: "#4ade80",
    formatter: (value) => `${value}`,
  },
  total_tokens: {
    label: "Tokens",
    stroke: "#06b6d4",
    fill: "#67e8f9",
    formatter: formatCompactNumber,
  },
};

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatFullNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

export function UsageChart({
  data,
  metric,
}: {
  data: UsageChartPoint[];
  metric: UsageMetric;
}) {
  const chartData = useMemo(
    () =>
      data.map((point) => ({
        ...point,
        shortDate: new Date(point.date).toLocaleDateString([], {
          month: "short",
          day: "numeric",
        }),
      })),
    [data],
  );

  if (!data.length) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs font-medium uppercase tracking-[0.24em] text-zinc-500">
        No usage data found
      </div>
    );
  }

  const config = METRIC_CONFIG[metric];

  return (
    <div className="h-full w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 12, right: 16, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="usageFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={config.fill} stopOpacity={0.28} />
              <stop offset="100%" stopColor={config.fill} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="rgba(161,161,170,0.12)" />
          <XAxis
            dataKey="shortDate"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            dy={10}
            minTickGap={24}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickFormatter={config.formatter}
            width={56}
          />
          <Tooltip
            cursor={{ stroke: "rgba(6, 182, 212, 0.25)", strokeWidth: 1 }}
            contentStyle={{
              backgroundColor: "rgba(9, 9, 11, 0.94)",
              borderColor: "rgba(63, 63, 70, 0.6)",
              borderRadius: "16px",
              boxShadow: "0 18px 48px rgba(0, 0, 0, 0.25)",
            }}
            formatter={(value, name) => {
              const numericValue =
                typeof value === "number"
                  ? value
                  : Number.parseFloat(String(value ?? 0));
              return [formatFullNumber(numericValue), String(name)];
            }}
            labelFormatter={(_, payload) => {
              const point = payload?.[0]?.payload as UsageChartPoint | undefined;
              return point
                ? new Date(point.date).toLocaleDateString([], {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })
                : "";
            }}
          />
          <Area
            type="monotone"
            dataKey={metric}
            name={config.label}
            stroke={config.stroke}
            strokeWidth={2.5}
            fill="url(#usageFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

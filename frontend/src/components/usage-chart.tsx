"use client";

import { useMemo } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface UsageData {
  date: string;
  sessions: number;
  messages: number;
}

export function UsageChart({ data }: { data: UsageData[] }) {
  const chartData = useMemo(() => {
    return data.map((d) => ({
      ...d,
      shortDate: new Date(d.date).toLocaleDateString([], { month: "short", day: "numeric" }),
    }));
  }, [data]);

  if (!data || data.length === 0) {
    return (
      <div className="h-full w-full flex items-center justify-center text-zinc-500 font-mono text-xs uppercase">
        No usage data found
      </div>
    );
  }

  return (
    <div className="h-full w-full -ml-4">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="colorSessions" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis 
            dataKey="shortDate" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: "#52525b", fontSize: 10 }}
            dy={10}
            minTickGap={30}
          />
          <YAxis 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: "#52525b", fontSize: 10 }}
            dx={-10}
            allowDecimals={false}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a", borderRadius: "8px" }}
            itemStyle={{ color: "#22d3ee" }}
            labelStyle={{ color: "#a1a1aa", fontSize: "12px", marginBottom: "4px" }}
          />
          <Area 
            type="monotone" 
            dataKey="sessions" 
            stroke="#22d3ee" 
            strokeWidth={2}
            fillOpacity={1} 
            fill="url(#colorSessions)" 
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

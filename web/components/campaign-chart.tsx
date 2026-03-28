"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCurrency, formatDate, formatNumber } from "@/lib/format";
import type { TimeSeriesPoint } from "@/lib/types";

interface CampaignChartProps {
  data: TimeSeriesPoint[];
}

export function CampaignChart({ data }: CampaignChartProps) {
  return (
    <div className="h-[340px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(148,163,184,0.14)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(value) => formatDate(value)}
            tick={{ fill: "#94A3B8", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="left"
            tickFormatter={(value) => formatCurrency(Number(value))}
            tick={{ fill: "#94A3B8", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={78}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(value) => formatCurrency(Number(value))}
            tick={{ fill: "#94A3B8", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={78}
          />
          <Tooltip
            contentStyle={{
              background: "rgba(2, 6, 23, 0.96)",
              border: "1px solid rgba(148, 163, 184, 0.18)",
              borderRadius: "18px",
              color: "#fff",
            }}
            formatter={(value, name) => {
              const numericValue = Number(Array.isArray(value) ? value[0] : value ?? 0);
              const label = String(name);
              if (label === "Revenue") {
                return [formatCurrency(numericValue), label];
              }
              if (label === "Conversions") {
                return [formatNumber(numericValue), label];
              }
              return [formatCurrency(numericValue), label];
            }}
            labelFormatter={(label) => formatDate(label)}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="compute_spend"
            name="Compute Spend"
            stroke="#60A5FA"
            strokeWidth={3}
            dot={false}
            activeDot={{ r: 5 }}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="revenue"
            name="Revenue"
            stroke="#34D399"
            strokeWidth={3}
            dot={false}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

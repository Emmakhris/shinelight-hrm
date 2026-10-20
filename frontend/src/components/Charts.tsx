import { Box, Typography } from "@mui/material";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Empty } from "./Feedback";

// Validated categorical palette (dataviz reference instance, light mode), assigned in fixed order.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const AXIS = { fontSize: 12, fill: "#52514e" };
const GRID = "#e8eaee";

interface Datum { label: string; value: number }

/** Horizontal bars for category magnitude (e.g. headcount by department). */
export function BarList({ data, height, valueLabel = "Employees" }: { data: Datum[]; height?: number; valueLabel?: string }) {
  if (!data?.length) return <Empty title="No data" />;
  const h = height || Math.max(160, data.length * 30 + 30);
  return (
    <Box sx={{ width: "100%", height: h }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }} barCategoryGap={6}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="label" tick={AXIS} width={140} axisLine={false} tickLine={false} />
          <Tooltip cursor={{ fill: "rgba(15,61,94,0.05)" }} formatter={(v) => [v, valueLabel]} />
          <Bar dataKey="value" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}

/** Vertical columns for ordered categories (age bands, years). */
export function Columns({ data, valueLabel = "Employees", height = 220 }: { data: Datum[]; valueLabel?: string; height?: number }) {
  if (!data?.length) return <Empty title="No data" />;
  return (
    <Box sx={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip cursor={{ fill: "rgba(15,61,94,0.05)" }} formatter={(v) => [v, valueLabel]} />
          <Bar dataKey="value" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={36} />
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}

/** Multi-series trend lines on one shared axis (same unit only — never a dual axis). */
export function Trend({ data, series, height = 240 }: {
  data: Record<string, string | number>[]; series: { key: string; label: string }[]; height?: number;
}) {
  if (!data?.length) return <Empty title="No data" />;
  return (
    <Box sx={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ left: -16, right: 12, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="month" tick={AXIS} axisLine={false} tickLine={false} interval="preserveStartEnd" />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip />
          {series.length > 1 && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s, i) => (
            <Line key={s.key} dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 5 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
}

export function ChartTitle({ children }: { children: string }) {
  return <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>{children}</Typography>;
}
